from __future__ import annotations

import asyncio
import json
import os
import re
from textwrap import dedent
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from .analytics import analyze_debate, format_analytics_report, session_chart_data
from .config import settings
from .costing import (
    CostTracker,
    EXCHANGE_RATES_PER_USD,
    estimate_messages_tokens,
    estimate_tokens,
    message_input_text,
    normalize_currency,
)
from .database import Database, utc_now
from .model_registry import (
    MOCK_MODEL,
    SupportedModel,
    get_available_model,
    mark_model_unavailable,
)
from .runtime_diary import runtime_diary


os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")

try:
    import litellm
    from litellm import acompletion

    litellm.suppress_debug_info = True
except ImportError:  # pragma: no cover - handled at runtime for clearer setup errors.
    litellm = None
    acompletion = None


TEAM_ROLE_DEFINITIONS = (
    {
        "archetype": "lead_advocate",
        "label": "Advocate",
        "min_debaters": 1,
        "job": "Build the team's central case, keep the argument coherent, and defend the main thesis.",
        "default_intent": "build the main case",
    },
    {
        "archetype": "rebuttal_critic",
        "label": "Rebuttal Critic",
        "min_debaters": 2,
        "job": "Attack the opposing team's strongest point and protect your team from direct criticism.",
        "default_intent": "rebut an opposing point",
    },
    {
        "archetype": "evidence_researcher",
        "label": "Evidence Researcher",
        "min_debaters": 3,
        "job": "Add evidence, examples, missing context, and careful uncertainty notes for your team.",
        "default_intent": "add evidence",
    },
    {
        "archetype": "cross_examiner",
        "label": "Cross-Examiner",
        "min_debaters": 4,
        "job": "Ask pressure questions, expose contradictions, and force the other team to answer clearly.",
        "default_intent": "cross-examine",
    },
)
USER_MESSAGE_MAX_CHARS = 5500
QUESTION_END_RE = re.compile(r"[?？]\s*$")
CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
MODEL_CONTEXT_LIMITS = {
    # NVIDIA NIM hosted models
    "nemotron-70b": 128_000,
    "llama-3.1-70b": 128_000,
    "llama-3.1-8b": 128_000,
    "mixtral-8x7b": 32_768,
    "mistral-7b": 32_768,
    "llama-3.2-90b-vision": 128_000,
    "mock-debate-model": 32_768,
}
TEAM_DEFINITIONS = (
    {
        "team": "pro",
        "team_label": "Pro",
        "stance_label": "supporting side",
        "stance": "argue for the topic or proposal",
    },
    {
        "team": "con",
        "team_label": "Con",
        "stance_label": "opposing side",
        "stance": "argue against the topic or proposal",
    },
)
JUDGE_ASSISTANT_DEFINITION = {
    "role": "judge_assistant",
    "archetype": "judge_assistant",
    "speaker": "Judge Assistant",
    "team": "neutral",
    "team_label": "Neutral",
    "stance_label": "neutral audit",
    "job": "Audit the debate for missed points, unanswered claims, evidence gaps, statistics, and scoring risks. Do not choose the final winner.",
}
JUDGE_DEFINITION = {
    "role": "judge",
    "archetype": "judge",
    "speaker": "Judge",
    "team": "neutral",
    "team_label": "Neutral",
    "stance_label": "final judgment",
    "job": "Use the debate and the Judge Assistant audit to make the final decision.",
}


class DebateError(Exception):
    pass


class CompletionStreamError(Exception):
    def __init__(self, original: Exception, had_output: bool):
        super().__init__(str(original))
        self.original = original
        self.had_output = had_output


class EmptyCompletionError(DebateError):
    pass


class ClientDisconnectedError(DebateError):
    pass


class DebateManager:
    def __init__(self, db: Database):
        self.db = db
        self._active_debates: set[str] = set()
        self._active_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_debates)

    def practice_state(self, session_id: str) -> dict[str, Any]:
        session_settings = self._settings_snapshot(session_id)
        debate = self.db.get_active_practice_debate(session_id)
        return self._practice_state_payload(debate, session_settings)

    async def run_interaction(
        self,
        websocket: WebSocket,
        session_id: str,
        content: str,
        selected_model_name: str,
        practice_side: str | None = None,
    ) -> None:
        if len(content) > USER_MESSAGE_MAX_CHARS:
            raise DebateError(
                f"Please shorten your message to {USER_MESSAGE_MAX_CHARS} characters or less."
            )
        cleaned_content = " ".join(content.strip().split())
        if not cleaned_content:
            raise DebateError("Please enter a message.")

        async with self._lock:
            if session_id in self._active_sessions:
                raise DebateError("This chat is already working. Other chats are still available.")
            self._active_sessions.add(session_id)

        try:
            cost_tracker = CostTracker()
            session_settings = self._settings_snapshot(session_id)
            session_record = self.db.get_session(session_id) or {}
            effective_model_name = selected_model_name.strip() or str(
                session_settings.get("overall_model", "")
            ).strip()
            selected_model = self._resolve_selected_model(effective_model_name)
            runtime_diary.record(
                "backend terminal",
                "interaction received",
                f"Session {session_id[:8]} using {selected_model.name}. Message preview: {self._clip_for_prompt(cleaned_content, 180)}",
                session_id=session_id,
            )
            safety = await self._safety_lock_assessment(
                cleaned_content, selected_model, cost_tracker, session_id=session_id
            )
            if safety.get("action") == "assist":
                runtime_diary.record(
                    "backend terminal",
                    "safety lock routed to Council Assistant",
                    str(safety.get("reason") or "Extreme unsafe request detected."),
                    session_id=session_id,
                )
                await self.run_safety_response(
                    websocket, session_id, cleaned_content, selected_model, safety, cost_tracker
                )
                return
            if session_record.get("mode") == "ai_vs_human":
                try:
                    await self.run_practice_interaction(
                        websocket=websocket,
                        session_id=session_id,
                        content=cleaned_content,
                        selected_model=selected_model,
                        cost_tracker=cost_tracker,
                        requested_side=practice_side,
                    )
                except Exception:
                    active_practice = self.db.get_active_practice_debate(session_id)
                    if active_practice:
                        self.db.fail_debate(active_practice["id"], "Practice turn failed.")
                        async with self._lock:
                            self._active_debates.discard(active_practice["id"])
                    raise
                return
            if self._council_assistant_always_on(session_settings):
                intent = "chat"
            else:
                intent = await self._classify_intent(
                    cleaned_content,
                    selected_model,
                    session_settings,
                    cost_tracker,
                    session_id=session_id,
                )
            runtime_diary.record(
                "backend terminal",
                "intent routed",
                f"Session {session_id[:8]} routed to {intent}.",
                session_id=session_id,
            )
            if intent == "debate":
                await self.run_debate(
                    websocket, session_id, cleaned_content, effective_model_name, cost_tracker
                )
            else:
                await self.run_chat(websocket, session_id, cleaned_content, selected_model, cost_tracker)
        finally:
            async with self._lock:
                self._active_sessions.discard(session_id)

    async def run_debate(
        self,
        websocket: WebSocket,
        session_id: str,
        topic: str,
        selected_model_name: str,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        cost_tracker = cost_tracker or CostTracker()
        cleaned_topic = " ".join(topic.strip().split())
        if not cleaned_topic:
            raise DebateError("Please enter a debate topic.")

        opening_settings = self._settings_snapshot(session_id)
        effective_model_name = selected_model_name.strip() or str(
            opening_settings.get("overall_model", "")
        ).strip()
        selected_model = self._resolve_selected_model(effective_model_name)
        async with self._lock:
            if len(self._active_debates) >= settings.max_active_debates:
                raise DebateError(
                    f"Only {settings.max_active_debates} debates can run at the same time. Try again when one finishes."
                )
            debate = self.db.create_debate(session_id, cleaned_topic)
            debate_id = debate["id"]
            self._active_debates.add(debate_id)
        runtime_diary.record(
            "backend terminal",
            "debate started",
            f"Debate {debate_id[:8]} started with {selected_model.name}. Topic: {self._clip_for_prompt(cleaned_topic, 180)}",
            session_id=session_id,
        )

        user_message = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="user",
            speaker="You",
            model="user",
            content=cleaned_topic,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": user_message["id"], "message": user_message}
        )
        await self._send_json(
            websocket,
            {
                "type": "debate_started",
                "debate": debate,
                "topic": cleaned_topic,
                "positions": self.debate_positions(cleaned_topic),
                "selected_model": selected_model.public_dict(configured=True),
                "assignments": self._assignment_payload(opening_settings, selected_model),
                "judge": {
                    "speaker": "Judge",
                    "model": self._resolve_agent_model(opening_settings, "judge", selected_model).name,
                    "provider": self._resolve_agent_model(opening_settings, "judge", selected_model).provider_label,
                },
                "active_debates": self.active_count,
            }
        )
        await self._send_json(
            websocket,
            {
                "type": "team_preparation_started",
                "debate_id": debate_id,
                "message": "Pro and Con teams are preparing private notebooks.",
            },
        )
        await self._prepare_team_notebooks(
            session_id=session_id,
            debate_id=debate_id,
            topic=cleaned_topic,
            session_settings=opening_settings,
            selected_model=selected_model,
            cost_tracker=cost_tracker,
        )
        await self._send_json(
            websocket,
            {
                "type": "team_preparation_completed",
                "debate_id": debate_id,
                "message": "Team notebooks are ready. Public debate is starting.",
            },
        )

        flow = self._debate_flow(opening_settings)
        transcript: list[dict[str, Any]] = []
        latest_analysis = self._with_phase_metadata(
            analyze_debate(cleaned_topic, transcript),
            flow=flow,
            current_phase=None,
            topic=cleaned_topic,
        )
        try:
            for phase in flow:
                turn_settings = self._settings_snapshot(session_id)
                agent = phase["agent"]
                turn_model = self._resolve_agent_model(
                    turn_settings, agent["archetype"], selected_model
                )
                generation_settings = self._agent_generation_settings(
                    turn_settings, agent["archetype"]
                )
                intelligence_context = self._intelligence_context(
                    session_id=session_id,
                    debate_id=debate_id,
                    agent=agent,
                    session_settings=turn_settings,
                )
                content = await self._stream_agent_turn(
                    websocket=websocket,
                    session_id=session_id,
                    debate_id=debate_id,
                    topic=cleaned_topic,
                    agent=agent,
                    model=turn_model,
                    phase=phase,
                    transcript=transcript,
                    session_settings=turn_settings,
                    generation_settings=generation_settings,
                    cost_tracker=cost_tracker,
                    intelligence_context=intelligence_context,
                )
                transcript.append(
                    {
                        "speaker": agent["speaker"],
                        "role": agent["role"],
                        "team": agent["team"],
                        "archetype": agent["archetype"],
                        "round": phase["index"],
                        "model": turn_model.name,
                        "intent": phase["intent"],
                        "target": phase["target"],
                        "phase_key": phase["key"],
                        "phase_title": phase["title"],
                        "phase_index": phase["index"],
                        "phase_total": phase["total"],
                        "phase_kind": phase["kind"],
                        "content": content,
                    }
                )
                self._capture_turn_intelligence(
                    session_id=session_id,
                    debate_id=debate_id,
                    agent=agent,
                    phase=phase,
                    content=content,
                )
                latest_analysis = self._with_phase_metadata(
                    analyze_debate(cleaned_topic, transcript),
                    flow=flow,
                    current_phase=phase,
                    topic=cleaned_topic,
                )
                latest_analysis["session_charts"] = session_chart_data(
                    self.db.list_debates(session_id),
                    self.db.list_messages(session_id),
                    debate_id,
                )
                await self._send_json(
                    websocket,
                    {
                        "type": "analysis_updated",
                        "round": latest_analysis["round"],
                        "analysis": latest_analysis,
                    }
                )

            judge_assistant_report = ""
            if self._judge_assistant_enabled(self._settings_snapshot(session_id)):
                assistant_settings = self._settings_snapshot(session_id)
                assistant_model = self._resolve_agent_model(
                    assistant_settings, "judge_assistant", selected_model
                )
                judge_assistant_report = await self._stream_judge_assistant_turn(
                    websocket=websocket,
                    session_id=session_id,
                    debate_id=debate_id,
                    topic=cleaned_topic,
                    model=assistant_model,
                    transcript=transcript,
                    analysis=latest_analysis,
                    session_settings=assistant_settings,
                    generation_settings=self._agent_generation_settings(
                        assistant_settings, "judge_assistant"
                    ),
                    cost_tracker=cost_tracker,
                    intelligence_context=self._intelligence_context(
                        session_id=session_id,
                        debate_id=debate_id,
                        agent=None,
                        session_settings=assistant_settings,
                    ),
                )

            judge_settings = self._settings_snapshot(session_id)
            judge_summary = await self._stream_final_judgment(
                websocket=websocket,
                session_id=session_id,
                debate_id=debate_id,
                topic=cleaned_topic,
                selected_model=selected_model,
                transcript=transcript,
                analysis=latest_analysis,
                session_settings=judge_settings,
                judge_assistant_report=judge_assistant_report,
                cost_tracker=cost_tracker,
                intelligence_context=self._intelligence_context(
                    session_id=session_id,
                    debate_id=debate_id,
                    agent=None,
                    session_settings=judge_settings,
                ),
            )
            self._finalize_debate_intelligence(
                session_id=session_id,
                debate_id=debate_id,
                topic=cleaned_topic,
                transcript=transcript,
                analysis=latest_analysis,
                judge_summary=judge_summary,
                session_settings=judge_settings,
            )
            cost_summary = cost_tracker.summary(judge_settings.get("cost_currency", "USD"))
            self.db.complete_debate(debate_id, judge_summary)
            runtime_diary.record(
                "backend terminal",
                "debate completed",
                f"Debate {debate_id[:8]} completed. Judge summary saved.",
                session_id=session_id,
            )
            async with self._lock:
                self._active_debates.discard(debate_id)
                active_after_completion = len(self._active_debates)
            await self._send_json(
                websocket,
                {
                    "type": "debate_completed",
                    "debate_id": debate_id,
                    "judge_summary": judge_summary,
                    "active_debates": active_after_completion,
                    "cost_summary": cost_summary,
                }
            )
        except ClientDisconnectedError as exc:
            self.db.fail_debate(debate_id, str(exc))
            runtime_diary.record(
                "backend terminal",
                "debate client disconnected",
                f"Debate {debate_id[:8]} stopped because the browser disconnected.",
                session_id=session_id,
            )
            raise
        except Exception as exc:
            self.db.fail_debate(debate_id, str(exc))
            runtime_diary.record(
                "backend terminal",
                "debate failed",
                f"Debate {debate_id[:8]} failed: {exc}",
                session_id=session_id,
            )
            raise
        finally:
            async with self._lock:
                self._active_debates.discard(debate_id)

    async def run_chat(
        self,
        websocket: WebSocket,
        session_id: str,
        content: str,
        selected_model: SupportedModel,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        cost_tracker = cost_tracker or CostTracker()
        session_settings = self._settings_snapshot(session_id)
        chat_record = self.db.create_debate(session_id, content, mode="chat")
        debate_id = chat_record["id"]
        runtime_diary.record(
            "backend terminal",
            "Council Assistant chat started",
            f"Chat {debate_id[:8]} started with {selected_model.name}.",
            session_id=session_id,
        )
        user_message = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="user",
            speaker="You",
            model="user",
            content=content,
        )
        await self._send_json(
            websocket,
            {
                "type": "interaction_started",
                "mode": "chat",
                "debate": chat_record,
                "selected_model": selected_model.public_dict(configured=True),
            }
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": user_message["id"], "message": user_message}
        )

        chat_model = self._resolve_agent_model(session_settings, "council_assistant", selected_model)
        chat_generation_settings = self._agent_generation_settings(
            session_settings, "council_assistant"
        )
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": "assistant",
                    "speaker": "Council Assistant",
                    "model": chat_model.name,
                    "content": "",
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": "chat",
            }
        )
        messages = self._chat_messages(
            session_id,
            content,
            session_settings,
            chat_generation_settings,
            chat_model,
        )
        try:
            response = await self._stream_completion(
                websocket,
                stream_id,
                chat_model,
                messages,
                session_settings=chat_generation_settings,
                cost_tracker=cost_tracker,
                cost_operation="Council Assistant",
            )
        except ClientDisconnectedError:
            self.db.fail_debate(debate_id, "Browser disconnected before the response finished.")
            runtime_diary.record(
                "backend terminal",
                "Council Assistant client disconnected",
                f"Chat {debate_id[:8]} stopped because the browser disconnected.",
                session_id=session_id,
            )
            raise
        except Exception as exc:
            cost_summary = cost_tracker.summary(session_settings.get("cost_currency", "USD"))
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role="assistant",
                speaker="Council Assistant",
                model=chat_model.name,
                exc=exc,
                cost_summary=cost_summary,
            )
            self.db.fail_debate(debate_id, str(exc))
            runtime_diary.record(
                "backend terminal",
                "Council Assistant chat failed",
                f"Chat {debate_id[:8]} failed: {exc}",
                session_id=session_id,
            )
            await self._send_json(
                websocket,
                {"type": "interaction_completed", "mode": "chat", "debate_id": debate_id, "cost_summary": cost_summary}
            )
            return
        cost_summary = cost_tracker.summary(session_settings.get("cost_currency", "USD"))
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="assistant",
            speaker="Council Assistant",
            model=chat_model.name,
            content=response,
            cost_summary=cost_summary,
        )
        self.db.complete_debate(debate_id, response)
        runtime_diary.record(
            "backend terminal",
            "Council Assistant chat completed",
            f"Chat {debate_id[:8]} completed.",
            session_id=session_id,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved}
        )
        await self._send_json(
            websocket,
            {"type": "interaction_completed", "mode": "chat", "debate_id": debate_id, "cost_summary": cost_summary}
        )

    async def run_practice_interaction(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        content: str,
        selected_model: SupportedModel,
        cost_tracker: CostTracker | None = None,
        requested_side: str | None = None,
    ) -> None:
        cost_tracker = cost_tracker or CostTracker()
        session_settings = self._settings_snapshot(session_id)
        practice_settings = self._practice_settings(session_settings)
        active_debate = self.db.get_active_practice_debate(session_id)
        profile = self.db.get_user_debate_profile()
        side_choice = self._practice_side_choice(
            requested_side or practice_settings.get("human_side", "Auto"),
            profile,
        )
        human_side = side_choice["human_side"]
        ai_side = "con" if human_side == "pro" else "pro"
        if active_debate:
            debate = active_debate
            async with self._lock:
                self._active_debates.add(debate["id"])
            metadata = debate.get("metadata") if isinstance(debate.get("metadata"), dict) else {}
            human_side = str(metadata.get("human_side") or human_side)
            ai_side = str(metadata.get("ai_side") or ("con" if human_side == "pro" else "pro"))
            topic = str(debate.get("topic") or content)
        else:
            topic = content
            async with self._lock:
                if len(self._active_debates) >= settings.max_active_debates:
                    raise DebateError(
                        f"Only {settings.max_active_debates} debates can run at the same time. Try again when one finishes."
                    )
                debate = self.db.create_debate(
                    session_id,
                    topic,
                    mode="practice",
                    metadata={
                        "human_side": human_side,
                        "ai_side": ai_side,
                        "side_source": side_choice["source"],
                        "side_reason": side_choice["reason"],
                        "practice_flow": practice_settings["practice_flow"],
                        "structured_rounds": practice_settings["structured_rounds"],
                        "human_turns": 0,
                    },
                )
                self._active_debates.add(debate["id"])
            await self._send_json(
                websocket,
                {
                    "type": "practice_started",
                    "debate": debate,
                    "state": self._practice_state_payload(debate, session_settings),
                    "selected_model": selected_model.public_dict(configured=True),
                },
            )
        debate_id = debate["id"]
        metadata = debate.get("metadata") if isinstance(debate.get("metadata"), dict) else {}
        human_turns = int(metadata.get("human_turns") or 0) + 1
        practice_flow = str(metadata.get("practice_flow") or practice_settings["practice_flow"])
        structured_rounds = int(metadata.get("structured_rounds") or practice_settings["structured_rounds"])
        is_structured = practice_flow == "Structured"
        is_last_round = is_structured and human_turns >= structured_rounds
        user_phase = self._practice_phase(
            title="Your Closing Appeal" if is_last_round else f"Your Practice Turn {human_turns}",
            index=human_turns * 2 - 1,
            total=structured_rounds * 2 if is_structured else 0,
            kind="practice_human",
        )
        user_message = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="practice_user",
            speaker="You",
            model="user",
            content=content,
            phase=user_phase,
        )
        updated_debate = self.db.update_debate_metadata(
            debate_id,
            {
                "human_turns": human_turns,
                "practice_flow": practice_flow,
                "structured_rounds": structured_rounds,
                "human_side": human_side,
                "ai_side": ai_side,
            },
        ) or debate
        await self._send_json(
            websocket,
            {
                "type": "practice_state_updated",
                "state": self._practice_state_payload(updated_debate, session_settings),
            },
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": user_message["id"], "message": user_message},
        )
        await self._send_json(
            websocket,
            {
                "type": "interaction_started",
                "mode": "practice",
                "debate": updated_debate,
                "selected_model": selected_model.public_dict(configured=True),
            },
        )
        practice_model = self._resolve_agent_model(session_settings, "practice_debater", selected_model)
        generation_settings = self._agent_generation_settings(session_settings, "practice_debater")
        transcript = self._practice_transcript(session_id, debate_id, human_side, ai_side)
        phase = self._practice_phase(
            title="Practice Debater Closing Appeal" if is_last_round else f"Practice Debater Turn {human_turns}",
            index=human_turns * 2,
            total=structured_rounds * 2 if is_structured else 0,
            kind="practice_ai",
        )
        content_response = await self._stream_practice_debater_turn(
            websocket=websocket,
            session_id=session_id,
            debate_id=debate_id,
            topic=topic,
            human_side=human_side,
            ai_side=ai_side,
            model=practice_model,
            phase=phase,
            transcript=transcript,
            session_settings=session_settings,
            generation_settings=generation_settings,
            cost_tracker=cost_tracker,
            is_last_round=is_last_round,
        )
        transcript.append(
            {
                "speaker": "Practice Debater",
                "role": "practice_debater",
                "team": ai_side,
                "archetype": "practice_debater",
                "round": human_turns,
                "model": practice_model.name,
                "intent": "practice against the user",
                "target": "the user's latest argument",
                "phase_key": phase["key"],
                "phase_title": phase["title"],
                "phase_index": phase["index"],
                "phase_total": phase["total"],
                "phase_kind": phase["kind"],
                "content": content_response,
            }
        )
        latest_analysis = self.phase_metadata_from_messages(
            analyze_debate(topic, transcript),
            self.db.list_messages(session_id),
            topic,
        )
        latest_analysis["session_charts"] = session_chart_data(
            self.db.list_debates(session_id),
            self.db.list_messages(session_id),
            debate_id,
        )
        await self._send_json(
            websocket,
            {"type": "analysis_updated", "round": latest_analysis["round"], "analysis": latest_analysis},
        )
        if is_last_round:
            await self._finalize_practice_debate(
                websocket=websocket,
                session_id=session_id,
                debate_id=debate_id,
                topic=topic,
                selected_model=selected_model,
                cost_tracker=cost_tracker,
            )
            return
        cost_summary = cost_tracker.summary(session_settings.get("cost_currency", "USD"))
        await self._send_json(
            websocket,
            {
                "type": "interaction_completed",
                "mode": "practice",
                "debate_id": debate_id,
                "cost_summary": cost_summary,
            },
        )

    async def end_practice_debate(
        self,
        websocket: WebSocket,
        session_id: str,
        selected_model_name: str,
    ) -> None:
        async with self._lock:
            if session_id in self._active_sessions:
                raise DebateError("This chat is already working. Other chats are still available.")
            self._active_sessions.add(session_id)
        debate: dict[str, Any] | None = None
        try:
            session_settings = self._settings_snapshot(session_id)
            effective_model_name = selected_model_name.strip() or str(
                session_settings.get("overall_model", "")
            ).strip()
            selected_model = self._resolve_selected_model(effective_model_name)
            cost_tracker = CostTracker()
            debate = self.db.get_active_practice_debate(session_id)
            if not debate:
                raise DebateError("No active practice debate is running in this chat.")
            async with self._lock:
                self._active_debates.add(debate["id"])
            await self._finalize_practice_debate(
                websocket=websocket,
                session_id=session_id,
                debate_id=debate["id"],
                topic=str(debate.get("topic") or ""),
                selected_model=selected_model,
                cost_tracker=cost_tracker,
            )
        except Exception:
            if debate:
                self.db.fail_debate(debate["id"], "Practice debate ending failed.")
                async with self._lock:
                    self._active_debates.discard(debate["id"])
            raise
        finally:
            async with self._lock:
                self._active_sessions.discard(session_id)

    async def _finalize_practice_debate(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        selected_model: SupportedModel,
        cost_tracker: CostTracker,
    ) -> None:
        session_settings = self._settings_snapshot(session_id)
        debate = self.db.get_active_practice_debate(session_id) or self.db.get_debate(
            session_id, debate_id, include_hidden=True
        )
        if not debate:
            raise DebateError("Practice debate not found.")
        metadata = debate.get("metadata") if isinstance(debate.get("metadata"), dict) else {}
        human_side = str(metadata.get("human_side") or "pro")
        ai_side = str(metadata.get("ai_side") or ("con" if human_side == "pro" else "pro"))
        transcript = self._practice_transcript(session_id, debate_id, human_side, ai_side)
        if not any(turn.get("role") == "practice_user" for turn in transcript):
            raise DebateError("Add at least one practice response before ending the debate.")
        analysis = self.phase_metadata_from_messages(
            analyze_debate(topic, transcript),
            self.db.list_messages(session_id),
            topic,
        )
        await self._send_json(
            websocket,
            {
                "type": "practice_state_updated",
                "state": {
                    **self._practice_state_payload(debate, session_settings),
                    "ending": True,
                },
            },
        )
        judge_assistant_report = ""
        if self._judge_assistant_enabled(session_settings):
            assistant_model = self._resolve_agent_model(
                session_settings, "judge_assistant", selected_model
            )
            judge_assistant_report = await self._stream_judge_assistant_turn(
                websocket=websocket,
                session_id=session_id,
                debate_id=debate_id,
                topic=topic,
                model=assistant_model,
                transcript=transcript,
                analysis=analysis,
                session_settings=session_settings,
                generation_settings=self._agent_generation_settings(
                    session_settings, "judge_assistant"
                ),
                cost_tracker=cost_tracker,
                intelligence_context=self._practice_profile_context(session_settings),
            )
            transcript = self._practice_transcript(session_id, debate_id, human_side, ai_side)
        judge_summary = await self._stream_final_judgment(
            websocket=websocket,
            session_id=session_id,
            debate_id=debate_id,
            topic=topic,
            selected_model=selected_model,
            transcript=transcript,
            analysis=analysis,
            session_settings=session_settings,
            judge_assistant_report=judge_assistant_report,
            cost_tracker=cost_tracker,
            intelligence_context=self._practice_profile_context(session_settings),
        )
        transcript = self._practice_transcript(session_id, debate_id, human_side, ai_side)
        trainer_model = self._resolve_agent_model(session_settings, "debate_trainer", selected_model)
        trainer_report = await self._stream_debate_trainer_turn(
            websocket=websocket,
            session_id=session_id,
            debate_id=debate_id,
            topic=topic,
            human_side=human_side,
            ai_side=ai_side,
            model=trainer_model,
            transcript=transcript,
            analysis=analysis,
            judge_summary=judge_summary,
            session_settings=session_settings,
            generation_settings=self._agent_generation_settings(session_settings, "debate_trainer"),
            cost_tracker=cost_tracker,
        )
        final_analysis = self.phase_metadata_from_messages(
            analyze_debate(topic, self._practice_transcript(session_id, debate_id, human_side, ai_side)),
            self.db.list_messages(session_id),
            topic,
        )
        final_analysis["session_charts"] = session_chart_data(
            self.db.list_debates(session_id),
            self.db.list_messages(session_id),
            debate_id,
        )
        self._finalize_debate_intelligence(
            session_id=session_id,
            debate_id=debate_id,
            topic=topic,
            transcript=transcript,
            analysis=final_analysis,
            judge_summary=judge_summary,
            session_settings=session_settings,
        )
        profile = self._update_user_profile_from_practice(
            debate_id=debate_id,
            human_side=human_side,
            judge_summary=judge_summary,
            trainer_report=trainer_report,
        )
        cost_summary = self._debate_total_cost_summary(
            session_id,
            debate_id,
            cost_tracker,
            session_settings.get("cost_currency", "USD"),
        )
        self.db.complete_debate(debate_id, judge_summary)
        async with self._lock:
            self._active_debates.discard(debate_id)
            active_after_completion = len(self._active_debates)
        await self._send_json(
            websocket,
            {
                "type": "practice_completed",
                "debate_id": debate_id,
                "profile": profile,
                "cost_summary": cost_summary,
            },
        )
        await self._send_json(
            websocket,
            {
                "type": "debate_completed",
                "debate_id": debate_id,
                "judge_summary": judge_summary,
                "active_debates": active_after_completion,
                "cost_summary": cost_summary,
            },
        )

    async def run_safety_response(
        self,
        websocket: WebSocket,
        session_id: str,
        content: str,
        selected_model: SupportedModel,
        safety: dict[str, Any],
        cost_tracker: CostTracker,
    ) -> None:
        session_settings = self._settings_snapshot(session_id)
        chat_record = self.db.create_debate(session_id, content, mode="chat")
        debate_id = chat_record["id"]
        runtime_diary.record(
            "backend terminal",
            "safety response started",
            f"Chat {debate_id[:8]} is answering through the Council Assistant safety lock.",
            session_id=session_id,
        )
        user_message = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="user",
            speaker="You",
            model="user",
            content=content,
        )
        response = self._safety_lock_message(safety)
        cost_summary = cost_tracker.summary(session_settings.get("cost_currency", "USD"))
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="assistant",
            speaker="Council Assistant",
            model=selected_model.name,
            content=response,
            cost_summary=cost_summary,
        )
        self.db.complete_debate(debate_id, response)
        await self._send_json(
            websocket,
            {
                "type": "interaction_started",
                "mode": "chat",
                "debate": chat_record,
                "selected_model": selected_model.public_dict(configured=True),
            },
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": user_message["id"], "message": user_message},
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": saved["id"], "message": saved},
        )
        await self._send_json(
            websocket,
            {
                "type": "interaction_completed",
                "mode": "chat",
                "debate_id": debate_id,
                "cost_summary": cost_summary,
            },
        )

    def _resolve_selected_model(self, selected_model_name: str) -> SupportedModel:
        cleaned_model_name = selected_model_name.strip()
        if settings.mock_llm and cleaned_model_name == MOCK_MODEL.name:
            return MOCK_MODEL
        if not cleaned_model_name:
            raise DebateError("Choose one unlocked model before starting the debate.")

        model = get_available_model(cleaned_model_name)
        if not model:
            raise DebateError(
                f"{cleaned_model_name} is not available. Add that provider API key to .env first."
            )
        return model

    def _settings_snapshot(self, session_id: str) -> dict[str, Any]:
        return self.db.get_session_settings(session_id) or {}

    def _active_debate_agents(self, session_settings: dict[str, Any]) -> list[dict[str, Any]]:
        debaters_per_team = max(1, min(4, int(session_settings.get("debaters_per_team", 2))))
        active_role_defs = [
            role_definition
            for role_definition in TEAM_ROLE_DEFINITIONS
            if role_definition["min_debaters"] <= debaters_per_team
        ]
        agents: list[dict[str, Any]] = []
        for team in TEAM_DEFINITIONS:
            for role_definition in active_role_defs:
                agents.append(
                    {
                        "role": f"{team['team']}_{role_definition['archetype']}",
                        "archetype": role_definition["archetype"],
                        "speaker": f"{team['team_label']} {role_definition['label']}",
                        "team": team["team"],
                        "team_label": team["team_label"],
                        "stance_label": team["stance_label"],
                        "stance": team["stance"],
                        "job": role_definition["job"],
                        "default_intent": role_definition["default_intent"],
                    }
                )
        return agents

    def _debate_flow(self, session_settings: dict[str, Any]) -> list[dict[str, Any]]:
        debaters_per_team = max(1, min(4, int(session_settings.get("debaters_per_team", 2))))
        debate_rounds = max(1, min(6, int(session_settings.get("debate_rounds", 6))))
        cap = max(1, min(4, int(session_settings.get("discussion_messages_per_team", 3))))
        agents = self._active_debate_agents(session_settings)
        lookup = {agent["role"]: agent for agent in agents}
        phases: list[dict[str, Any]] = []

        def role(team: str, archetype: str) -> str:
            return f"{team}_{archetype}"

        def add(
            key: str,
            title: str,
            role_id: str,
            kind: str,
            intent: str,
            instruction: str,
            target: str = "the debate topic",
        ) -> None:
            agent = lookup.get(role_id)
            if not agent:
                return
            phases.append(
                {
                    "key": key,
                    "title": title,
                    "agent": agent,
                    "kind": kind,
                    "intent": intent,
                    "instruction": instruction,
                    "target": target,
                }
            )

        def discussion(title: str, opening_team: str, key_prefix: str) -> None:
            other_team = "con" if opening_team == "pro" else "pro"
            order = [opening_team, other_team] * cap
            counts = {"pro": 0, "con": 0}
            for team in order:
                if counts[team] >= cap:
                    continue
                counts[team] += 1
                team_label = "Pro" if team == "pro" else "Con"
                add(
                    f"{key_prefix}_{team}_{counts[team]}",
                    f"{title}: {team_label} Advocate Message {counts[team]}",
                    role(team, "lead_advocate"),
                    "discussion",
                    f"speak for the {team_label} team in advocate-led discussion",
                    "Speak as the Advocate for your whole team. Use your team's prior research, criticism, and cross-examination points where relevant. Respond to specific argument content, not turn numbers. Do not say 'my opponent says'.",
                    "the latest unresolved clash",
                )

        def one_debater_open_discussion() -> None:
            counts = {"pro": 0, "con": 0}
            openers = ["pro" if index % 2 == 0 else "con" for index in range(debate_rounds)]
            pattern: list[str] = []
            for opener in openers:
                other_team = "con" if opener == "pro" else "pro"
                pattern.extend([opener, other_team])
            if not pattern:
                pattern = ["pro", "con"]
            while min(counts.values()) < cap:
                made_progress = False
                for step_index, team in enumerate(pattern):
                    if counts[team] >= cap:
                        continue
                    counts[team] += 1
                    made_progress = True
                    team_label = "Pro" if team == "pro" else "Con"
                    mini_round = f"Mini-round {step_index // 2 + 1}"
                    add(
                        f"open_discussion_{team}_{counts[team]}",
                        f"Open Discussion ({mini_round}): {team_label} Advocate Message {counts[team]}",
                        role(team, "lead_advocate"),
                        "discussion",
                        f"speak for the {team_label} side in open discussion",
                        "Speak naturally in open discussion. Answer, defend, attack, clarify, or add a point as needed. Address specific claims by content, not by turn number. Do not say 'my opponent says'.",
                        "the strongest unresolved point",
                    )
                if not made_progress:
                    break

        add(
            "pro_constructive",
            "Pro Advocate Constructive Speech",
            role("pro", "lead_advocate"),
            "constructive",
            "present the Pro case",
            "Build the Pro case with clear claims, warrants, and stakes.",
        )

        if debaters_per_team == 1:
            add(
                "con_constructive",
                "Con Advocate Constructive Speech",
                role("con", "lead_advocate"),
                "constructive",
                "present the Con case",
                "Build the Con case with clear counterclaims, warrants, and stakes.",
                "the Pro constructive case",
            )
            add(
                "con_cross_exam_pro",
                "Con Advocate Cross-examines Pro",
                role("con", "lead_advocate"),
                "cross_exam",
                "cross-examine the Pro case",
                "Give one short setup sentence, then ask 2-4 pointed questions. Do not answer your own questions or deliver a full rebuttal.",
                "the Pro constructive case",
            )
            add(
                "pro_answers_rebuttal",
                "Pro Advocate Answers + Rebuttal",
                role("pro", "lead_advocate"),
                "answer_rebuttal",
                "answer cross-examination and rebut Con",
                "Answer the strongest cross-examination questions, then attack or repair positions where useful.",
                "the Con constructive and cross-exam questions",
            )
            add(
                "pro_cross_exam_con",
                "Pro Advocate Cross-examines Con",
                role("pro", "lead_advocate"),
                "cross_exam",
                "cross-examine the Con case",
                "Give one short setup sentence, then ask 2-4 pointed questions. Do not answer your own questions or deliver a full rebuttal.",
                "the Con constructive case",
            )
            add(
                "con_answers_rebuttal",
                "Con Advocate Answers + Rebuttal",
                role("con", "lead_advocate"),
                "answer_rebuttal",
                "answer cross-examination and rebut Pro",
                "Answer the strongest cross-examination questions, then attack or repair positions where useful.",
                "the Pro rebuttal and cross-exam questions",
            )
            one_debater_open_discussion()
        else:
            if debaters_per_team == 2:
                add(
                    "con_critic_cross_exam_pro_advocate",
                    "Con Critic Cross-examines Pro Advocate",
                    role("con", "rebuttal_critic"),
                    "cross_exam",
                    "cross-examine the Pro Advocate",
                    "Give one short setup sentence, then ask 2-4 pointed questions. Do not deliver your rebuttal yet.",
                    "the Pro Advocate's constructive",
                )
                add(
                    "con_constructive",
                    "Con Advocate Constructive Speech",
                    role("con", "lead_advocate"),
                    "constructive",
                    "present the Con case",
                    "Build the Con case with clear counterclaims, warrants, and stakes.",
                    "the Pro constructive case and Con Critic's cross-exam pressure",
                )
                add(
                    "pro_critic_cross_exam_con_advocate",
                    "Pro Critic Cross-examines Con Advocate",
                    role("pro", "rebuttal_critic"),
                    "cross_exam",
                    "cross-examine the Con Advocate",
                    "Give one short setup sentence, then ask 2-4 pointed questions. Do not deliver your rebuttal yet.",
                    "the Con Advocate's constructive",
                )
            else:
                add(
                    "con_constructive",
                    "Con Advocate Constructive Speech",
                    role("con", "lead_advocate"),
                    "constructive",
                    "present the Con case",
                    "Build the Con case with clear counterclaims, warrants, and stakes.",
                    "the Pro constructive case",
                )

                if debaters_per_team >= 4:
                    add(
                        "con_examiner_cross_exam_pro_advocate",
                        "Con Examiner Cross-examines Pro Advocate",
                        role("con", "cross_examiner"),
                        "cross_exam",
                        "cross-examine the Pro Advocate",
                        "Use Socratic pressure. Give one short setup sentence, then ask 2-4 pointed questions only.",
                        "the Pro Advocate's opening constructive",
                    )
                    add(
                        "pro_examiner_cross_exam_con_advocate",
                        "Pro Examiner Cross-examines Con Advocate",
                        role("pro", "cross_examiner"),
                        "cross_exam",
                        "cross-examine the Con Advocate",
                        "Use Socratic pressure. Give one short setup sentence, then ask 2-4 pointed questions only.",
                        "the Con Advocate's opening constructive",
                    )

            if debaters_per_team >= 3:
                add(
                    "pro_researcher_evidence",
                    "Pro Researcher Evidence Presentation",
                    role("pro", "evidence_researcher"),
                    "evidence",
                    "add Pro evidence and examples",
                    "Add evidence, examples, uncertainty notes, and verification needs. Do not invent citations when web search is unavailable.",
                    "the Pro case and Con pressure points",
                )
                add(
                    "con_researcher_evidence",
                    "Con Researcher Evidence Presentation",
                    role("con", "evidence_researcher"),
                    "evidence",
                    "add Con evidence and counter-evidence",
                    "Add evidence, examples, uncertainty notes, and verification needs. Do not invent citations when web search is unavailable.",
                    "the Con case and Pro pressure points",
                )

            if debaters_per_team >= 4:
                add(
                    "con_examiner_cross_exam_pro_researcher",
                    "Con Examiner Cross-examines Pro Researcher",
                    role("con", "cross_examiner"),
                    "cross_exam",
                    "cross-examine the Pro Researcher",
                    "Ask 2-4 questions that test evidence quality, assumptions, and missing verification. Do not rebut fully yet.",
                    "the Pro Researcher's evidence",
                )
                add(
                    "pro_examiner_cross_exam_con_researcher",
                    "Pro Examiner Cross-examines Con Researcher",
                    role("pro", "cross_examiner"),
                    "cross_exam",
                    "cross-examine the Con Researcher",
                    "Ask 2-4 questions that test evidence quality, assumptions, and missing verification. Do not rebut fully yet.",
                    "the Con Researcher's evidence",
                )

            discussion("Discussion Time 1", "pro", "discussion_1")
            rebuttal_order = [("pro", "Con"), ("con", "Pro")] if debaters_per_team == 2 else [("con", "Pro"), ("pro", "Con")]
            for team, target_team in rebuttal_order:
                team_label = "Pro" if team == "pro" else "Con"
                add(
                    f"{team}_critic_rebuttal",
                    f"{team_label} Critic Rebuttal",
                    role(team, "rebuttal_critic"),
                    "rebuttal",
                    f"attack the {target_team} case",
                    f"Synthesize the biggest weaknesses in the {target_team} case, including cross-exam and evidence problems.",
                    f"the full {target_team} case so far",
                )
            for discussion_index in range(2, debate_rounds + 1):
                opening_team = "con" if discussion_index % 2 == 0 else "pro"
                discussion(
                    f"Discussion Time {discussion_index}",
                    opening_team,
                    f"discussion_{discussion_index}",
                )

        add(
            "pro_closing",
            "Pro Advocate Closing Summary",
            role("pro", "lead_advocate"),
            "closing",
            "deliver the Pro closing summary",
            "Rebuild the Pro case, answer the most damaging objections, and give a concise final appeal.",
            "the whole debate",
        )
        add(
            "con_closing",
            "Con Advocate Closing Summary",
            role("con", "lead_advocate"),
            "closing",
            "deliver the Con closing summary",
            "Rebuild the Con case, answer the most damaging objections, and give a concise final appeal.",
            "the whole debate",
        )

        total = len(phases)
        for index, phase in enumerate(phases, start=1):
            phase["index"] = index
            phase["total"] = total
        return phases

    def _with_phase_metadata(
        self,
        analysis: dict[str, Any],
        *,
        flow: list[dict[str, Any]],
        current_phase: dict[str, Any] | None,
        topic: str,
    ) -> dict[str, Any]:
        positions = self.debate_positions(topic)
        phase_sequence = [
            {
                "key": phase["key"],
                "title": phase["title"],
                "kind": phase["kind"],
                "index": phase["index"],
                "total": phase["total"],
                "speaker": phase["agent"]["speaker"],
                "team": phase["agent"]["team"],
            }
            for phase in flow
        ]
        analysis["phase"] = {
            "current": {
                "key": current_phase["key"],
                "title": current_phase["title"],
                "kind": current_phase["kind"],
                "index": current_phase["index"],
                "total": current_phase["total"],
                "speaker": current_phase["agent"]["speaker"],
                "team": current_phase["agent"]["team"],
            }
            if current_phase
            else None,
            "completed": current_phase["index"] if current_phase else 0,
            "total": len(flow),
            "flow_name": "Professional Debate Flow",
            "sequence": phase_sequence,
            "pro_position": positions["pro"],
            "con_position": positions["con"],
        }
        return analysis

    def phase_metadata_from_messages(
        self, analysis: dict[str, Any], messages: list[dict[str, Any]], topic: str
    ) -> dict[str, Any]:
        positions = self.debate_positions(topic)
        phase_rows = [message for message in messages if message.get("phase_key")]
        sequence_by_key: dict[str, dict[str, Any]] = {}
        for message in phase_rows:
            key = str(message.get("phase_key") or "")
            if not key or key in sequence_by_key:
                continue
            sequence_by_key[key] = {
                "key": key,
                "title": message.get("phase_title") or key.replace("_", " ").title(),
                "kind": message.get("phase_kind") or "turn",
                "index": int(message.get("phase_index") or len(sequence_by_key) + 1),
                "total": int(message.get("phase_total") or 0),
                "speaker": message.get("speaker") or "",
                "team": "pro"
                if str(message.get("role") or "").startswith("pro_")
                else "con"
                if str(message.get("role") or "").startswith("con_")
                else "neutral",
            }
        sequence = sorted(sequence_by_key.values(), key=lambda item: item["index"])
        current = sequence[-1] if sequence else None
        total = max([item["total"] for item in sequence] or [len(sequence)])
        analysis["phase"] = {
            "current": current,
            "completed": current["index"] if current else 0,
            "total": total,
            "flow_name": "Professional Debate Flow",
            "sequence": sequence,
            "pro_position": positions["pro"],
            "con_position": positions["con"],
        }
        return analysis

    def debate_positions(self, topic: str) -> dict[str, str]:
        core = self._position_topic_core(topic)
        modal_match = re.match(r"(?i)^(should|must|can|could|would|will)\s+(.+)$", core)
        if modal_match:
            remainder = modal_match.group(2).strip()
            option_split = self._split_or_topic(remainder)
            if option_split:
                shared_prefix, pro_option, con_option = option_split
                pro_basis = f"{shared_prefix}{pro_option}".strip() if shared_prefix else pro_option
                con_basis = f"{shared_prefix}{con_option}".strip() if shared_prefix else con_option
                pro_clause = self._tidy_position_clause(pro_basis)
                con_clause = self._tidy_position_clause(con_basis)
                return {
                    "pro": f"Pro argues that {pro_clause}.",
                    "con": f"Con argues that {con_clause}, not {pro_clause}.",
                }
        option_split = self._split_or_topic(core)
        if option_split:
            shared_prefix, pro_option, con_option = option_split
            pro_basis = f"{shared_prefix}{pro_option}".strip() if shared_prefix else pro_option
            con_basis = f"{shared_prefix}{con_option}".strip() if shared_prefix else con_option
            pro_clause = self._tidy_position_clause(pro_basis)
            con_clause = self._tidy_position_clause(con_basis)
            not_clause = self._tidy_position_clause(pro_basis)
            return {
                "pro": (
                    f"Pro argues that {pro_clause}."
                    if shared_prefix
                    else f"Pro argues for {pro_clause}."
                ),
                "con": (
                    f"Con argues that {con_clause}, not {not_clause}."
                    if shared_prefix
                    else f"Con argues for {con_clause}, not {not_clause}."
                ),
            }

        should_match = re.match(r"(?i)^should\s+(.+)$", core)
        if should_match:
            remainder = should_match.group(1).strip().rstrip("?.")
            words = remainder.split()
            if len(words) >= 2:
                subject_width = 2 if words[0].lower() in {"the", "a", "an"} and len(words) >= 3 else 1
                subject = " ".join(words[:subject_width])
                action = " ".join(words[subject_width:])
                return {
                    "pro": f"Pro argues that {subject} should {action}.",
                    "con": f"Con argues that {subject} should not {action}.",
                }

        readable = core.rstrip("?.")
        if CJK_CHAR_RE.search(readable):
            return {
                "pro": f"Pro supports this topic statement: {readable}.",
                "con": f"Con challenges this topic statement: {readable}.",
            }
        return {
            "pro": f"Pro argues that this position is correct: {readable}.",
            "con": f"Con argues that this position is wrong or too weak: {readable}.",
        }

    def _position_topic_core(self, topic: str) -> str:
        core = " ".join(str(topic).strip().split()).strip(" ?.!。！？：:")
        patterns = (
            r"(?i)^please\s+",
            r"(?i)^(debate|discuss|argue|analyze)\s*:?\s*(about\s+)?",
            r"(?i)^(whether|if)\s+",
        )
        changed = True
        while changed:
            changed = False
            for pattern in patterns:
                next_core = re.sub(pattern, "", core).strip()
                if next_core != core:
                    core = next_core
                    changed = True
        return core or str(topic).strip()

    def _split_or_topic(self, core: str) -> tuple[str, str, str] | None:
        parts = re.split(
            r"\s+(?:or|versus|vs\.?)\s+|(?:还是|或者|或)",
            core,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(parts) != 2:
            return None
        left, right = parts[0].strip(), parts[1].strip().rstrip("?.。！？")
        if not left or not right:
            return None
        lower_left = left.lower()
        best_index = -1
        best_prep = ""
        for prep in (" in ", " at ", " during ", " for ", " with ", " without ", " before ", " after ", " on "):
            index = lower_left.rfind(prep)
            if index > best_index:
                best_index = index
                best_prep = prep
        if best_index == -1:
            for marker in (" should ", " should not ", " can ", " could ", " would ", " will "):
                index = lower_left.rfind(marker)
                if index > best_index:
                    best_index = index
                    best_prep = marker
        if best_index == -1:
            return "", left, right
        shared_prefix = left[: best_index + len(best_prep)]
        pro_option = left[best_index + len(best_prep) :].strip()
        if not pro_option:
            return None
        return shared_prefix, pro_option, right

    def _tidy_position_clause(self, text: str) -> str:
        cleaned = " ".join(str(text).strip().split()).strip(" .,;:!?-")
        cleaned = re.sub(
            r"(?i)\b(in|during)\s+(morning|afternoon|evening)\b",
            lambda match: f"{match.group(1)} the {match.group(2)}",
            cleaned,
        )
        cleaned = re.sub(
            r"(?i)^\s*(morning|afternoon|evening)\s*$",
            lambda match: f"the {match.group(1)}",
            cleaned,
        )
        return cleaned

    def _assignment_payload(
        self, session_settings: dict[str, Any], default_model: SupportedModel
    ) -> list[dict[str, str]]:
        agents = self._active_debate_agents(session_settings)
        if self._judge_assistant_enabled(session_settings):
            agents.append(JUDGE_ASSISTANT_DEFINITION)
        agents.append(JUDGE_DEFINITION)
        payload = []
        for agent in agents:
            model = self._resolve_agent_model(session_settings, agent["archetype"], default_model)
            payload.append(
                {
                    "role": agent["role"],
                    "speaker": agent["speaker"],
                    "model": model.name,
                    "provider": model.provider_label,
                }
            )
        return payload

    def _judge_assistant_enabled(self, session_settings: dict[str, Any]) -> bool:
        return bool(session_settings.get("judge_assistant_enabled", True))

    def _resolve_agent_model(
        self, session_settings: dict[str, Any], archetype: str, default_model: SupportedModel
    ) -> SupportedModel:
        raw_agent_settings = session_settings.get("agent_settings") or {}
        agent_settings = raw_agent_settings.get(archetype, {}) if isinstance(raw_agent_settings, dict) else {}
        model_name = str(agent_settings.get("model", "")).strip()
        if not model_name:
            model_name = str(session_settings.get("overall_model", "")).strip()
        if not model_name:
            return default_model
        if settings.mock_llm and model_name == MOCK_MODEL.name:
            return MOCK_MODEL
        return get_available_model(model_name) or default_model

    def _agent_generation_settings(
        self, session_settings: dict[str, Any], archetype: str
    ) -> dict[str, Any]:
        raw_agent_settings = session_settings.get("agent_settings") or {}
        agent_settings = raw_agent_settings.get(archetype, {}) if isinstance(raw_agent_settings, dict) else {}
        return {
            **session_settings,
            "temperature": float(agent_settings.get("temperature", session_settings.get("temperature", 0.55))),
            "max_tokens": int(agent_settings.get("max_tokens", session_settings.get("max_tokens", 2048))),
            "response_length": str(agent_settings.get("response_length", session_settings.get("response_length", "Normal"))),
            "agent_web_search": bool(agent_settings.get("web_search", False)),
        }

    def _practice_settings(self, session_settings: dict[str, Any]) -> dict[str, Any]:
        raw = session_settings.get("practice_settings")
        defaults = {
            "human_side": "Auto",
            "practice_flow": "Free",
            "structured_rounds": 6,
            "use_user_profile": True,
            "trainer_style": "Coach",
            "training_focus": "Full Debate",
            "opponent_difficulty": "Adaptive",
        }
        if not isinstance(raw, dict):
            raw = {}
        return {**defaults, **raw}

    def _practice_side_choice(self, requested: str | None, profile: dict[str, Any]) -> dict[str, str]:
        cleaned = str(requested or "Auto").strip().lower()
        if cleaned in {"pro", "con"}:
            return {
                "human_side": cleaned,
                "source": "user",
                "reason": f"You chose {cleaned.upper()} for this practice debate.",
            }
        side_history = profile.get("side_history") if isinstance(profile, dict) else {}
        pro_count = int((side_history or {}).get("pro", 0) or 0)
        con_count = int((side_history or {}).get("con", 0) or 0)
        if pro_count < con_count:
            side = "pro"
            reason = "Auto chose Pro because you have practiced that side less."
        elif con_count < pro_count:
            side = "con"
            reason = "Auto chose Con because you have practiced that side less."
        else:
            side = "pro"
            reason = "Auto chose Pro because your profile does not show a weaker or less-practiced side yet."
        return {"human_side": side, "source": "auto", "reason": reason}

    def _practice_state_payload(
        self, debate: dict[str, Any] | None, session_settings: dict[str, Any]
    ) -> dict[str, Any]:
        if not debate:
            return {"active": False}
        metadata = debate.get("metadata") if isinstance(debate.get("metadata"), dict) else {}
        practice_settings = self._practice_settings(session_settings)
        flow = str(metadata.get("practice_flow") or practice_settings["practice_flow"])
        structured_rounds = int(metadata.get("structured_rounds") or practice_settings["structured_rounds"])
        human_turns = int(metadata.get("human_turns") or 0)
        rounds_left = max(0, structured_rounds - human_turns) if flow == "Structured" else None
        return {
            "active": debate.get("status") == "running",
            "debate_id": debate.get("id"),
            "topic": debate.get("topic") or "",
            "human_side": metadata.get("human_side") or practice_settings.get("human_side", "Auto"),
            "ai_side": metadata.get("ai_side") or "",
            "side_source": metadata.get("side_source") or "",
            "side_reason": metadata.get("side_reason") or "",
            "practice_flow": flow,
            "structured_rounds": structured_rounds,
            "human_turns": human_turns,
            "rounds_left": rounds_left,
        }

    def _debate_total_cost_summary(
        self,
        session_id: str,
        debate_id: str,
        cost_tracker: CostTracker,
        currency: str,
    ) -> dict[str, Any]:
        summaries = [
            message.get("cost_summary")
            for message in self.db.list_messages_for_debate(
                session_id, debate_id, include_hidden=True
            )
            if isinstance(message.get("cost_summary"), dict)
        ]
        if not summaries:
            return cost_tracker.summary(currency)
        normalized_currency = normalize_currency(str(currency))
        rate = EXCHANGE_RATES_PER_USD[normalized_currency]
        models: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        pricing_complete = True
        for summary in summaries:
            pricing_complete = pricing_complete and bool(summary.get("pricing_complete", True))
            for warning in summary.get("warnings") or []:
                if isinstance(warning, str) and warning not in warnings:
                    warnings.append(warning)
            for item in summary.get("models") or []:
                if not isinstance(item, dict):
                    continue
                model_name = str(item.get("model") or "unknown")
                current = models.setdefault(
                    model_name,
                    {
                        "model": model_name,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "calls": 0,
                        "cost_usd": 0.0,
                        "input_usd_per_1m": item.get("input_usd_per_1m", 0.0),
                        "output_usd_per_1m": item.get("output_usd_per_1m", 0.0),
                        "pricing_source": item.get("pricing_source", ""),
                        "pricing_live": bool(item.get("pricing_live", False)),
                        "pricing_available": bool(item.get("pricing_available", True)),
                    },
                )
                current["input_tokens"] += int(item.get("input_tokens") or 0)
                current["output_tokens"] += int(item.get("output_tokens") or 0)
                current["calls"] += int(item.get("calls") or 0)
                current["cost_usd"] += float(item.get("cost_usd") or 0.0)
                if not item.get("pricing_available", True):
                    current["pricing_available"] = False
                    pricing_complete = False
        model_items = []
        for item in models.values():
            converted = float(item["cost_usd"]) * rate
            model_items.append(
                {
                    **item,
                    "cost": round(converted, 8),
                    "cost_usd": round(float(item["cost_usd"]), 8),
                }
            )
        model_items.sort(key=lambda item: item["cost_usd"], reverse=True)
        total_usd = sum(float(item["cost_usd"]) for item in model_items)
        return {
            "currency": normalized_currency,
            "total": round(total_usd * rate, 8),
            "total_usd": round(total_usd, 8),
            "input_tokens": sum(int(item["input_tokens"]) for item in model_items),
            "output_tokens": sum(int(item["output_tokens"]) for item in model_items),
            "calls": sum(int(item["calls"]) for item in model_items),
            "models": model_items,
            "estimated": True,
            "pricing_complete": pricing_complete,
            "warnings": warnings,
            "rate_source": "Aggregated from saved message cost summaries.",
        }

    def _practice_phase(self, *, title: str, index: int, total: int, kind: str) -> dict[str, Any]:
        key = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or kind
        return {
            "key": f"practice_{key}_{max(1, index)}",
            "title": title,
            "index": max(1, index),
            "total": max(0, total),
            "kind": kind,
        }

    def _practice_transcript(
        self,
        session_id: str,
        debate_id: str,
        human_side: str,
        ai_side: str,
    ) -> list[dict[str, Any]]:
        transcript = []
        current_round = 0
        for message in self.db.list_messages_for_debate(session_id, debate_id, include_hidden=True):
            role = str(message.get("role") or "")
            if role == "practice_user":
                team = human_side
                archetype = "human_debater"
                current_round += 1
                round_number = current_round
            elif role == "practice_debater":
                team = ai_side
                archetype = "practice_debater"
                round_number = current_round or 1
            elif role in {"judge", "judge_assistant", "debate_trainer"}:
                team = "neutral"
                archetype = role
                round_number = current_round or int(message.get("phase_index") or 0)
            else:
                team = "neutral"
                archetype = role
                round_number = current_round or int(message.get("phase_index") or 0)
            transcript.append(
                {
                    "speaker": message.get("speaker") or role,
                    "role": role,
                    "team": team,
                    "archetype": archetype,
                    "round": round_number,
                    "model": message.get("model") or "",
                    "intent": "practice debate turn",
                    "target": "the practice debate",
                    "phase_key": message.get("phase_key"),
                    "phase_title": message.get("phase_title"),
                    "phase_index": message.get("phase_index"),
                    "phase_total": message.get("phase_total"),
                    "phase_kind": message.get("phase_kind"),
                    "content": message.get("content") or "",
                }
            )
        return transcript

    async def _stream_practice_debater_turn(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        human_side: str,
        ai_side: str,
        model: SupportedModel,
        phase: dict[str, Any],
        transcript: list[dict[str, Any]],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        cost_tracker: CostTracker | None,
        is_last_round: bool,
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": "practice_debater",
                    "speaker": "Practice Debater",
                    "model": model.name,
                    "content": "",
                    "phase_key": phase["key"],
                    "phase_title": phase["title"],
                    "phase_index": phase["index"],
                    "phase_total": phase["total"],
                    "phase_kind": phase["kind"],
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": phase["index"],
            },
        )
        messages = self._practice_debater_messages(
            session_id=session_id,
            topic=topic,
            human_side=human_side,
            ai_side=ai_side,
            transcript=transcript,
            session_settings=session_settings,
            generation_settings=generation_settings,
            model=model,
            is_last_round=is_last_round,
        )
        cost_start = len(cost_tracker.entries) if cost_tracker else 0
        try:
            content = await self._stream_completion(
                websocket,
                stream_id,
                model,
                messages,
                session_settings=generation_settings,
                cost_tracker=cost_tracker,
                cost_operation="Practice Debater",
            )
        except ClientDisconnectedError:
            raise
        except Exception as exc:
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role="practice_debater",
                speaker="Practice Debater",
                model=model.name,
                exc=exc,
                phase=phase,
            )
            raise
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="practice_debater",
            speaker="Practice Debater",
            model=model.name,
            content=content,
            cost_summary=cost_tracker.summary_since(
                cost_start, session_settings.get("cost_currency", "USD")
            )
            if cost_tracker
            else None,
            phase=phase,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved},
        )
        return content

    async def _stream_debate_trainer_turn(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        human_side: str,
        ai_side: str,
        model: SupportedModel,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        judge_summary: str,
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        cost_tracker: CostTracker | None,
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": "debate_trainer",
                    "speaker": "Debate Trainer",
                    "model": model.name,
                    "content": "",
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": "summary",
            },
        )
        messages = self._debate_trainer_messages(
            session_id=session_id,
            topic=topic,
            human_side=human_side,
            ai_side=ai_side,
            transcript=transcript,
            analysis=analysis,
            judge_summary=judge_summary,
            session_settings=session_settings,
            generation_settings=generation_settings,
            model=model,
        )
        cost_start = len(cost_tracker.entries) if cost_tracker else 0
        try:
            content = await self._stream_completion(
                websocket,
                stream_id,
                model,
                messages,
                session_settings=generation_settings,
                cost_tracker=cost_tracker,
                cost_operation="Debate Trainer",
            )
        except ClientDisconnectedError:
            raise
        except Exception as exc:
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role="debate_trainer",
                speaker="Debate Trainer",
                model=model.name,
                exc=exc,
                cost_summary=cost_tracker.summary_since(
                    cost_start, session_settings.get("cost_currency", "USD")
                )
                if cost_tracker
                else None,
            )
            raise
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="debate_trainer",
            speaker="Debate Trainer",
            model=model.name,
            content=content,
            cost_summary=cost_tracker.summary_since(
                cost_start, session_settings.get("cost_currency", "USD")
            )
            if cost_tracker
            else None,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved},
        )
        return content


    def _council_assistant_always_on(self, session_settings: dict[str, Any]) -> bool:
        raw_agent_settings = session_settings.get("agent_settings") or {}
        council_settings = (
            raw_agent_settings.get("council_assistant", {})
            if isinstance(raw_agent_settings, dict)
            else {}
        )
        return bool(council_settings.get("always_on", False))

    def _clip_for_prompt(self, text: str, limit: int) -> str:
        normalized = " ".join(str(text).strip().split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    def _model_context_limit(self, model_name: str) -> int:
        return MODEL_CONTEXT_LIMITS.get(model_name, 32_768)

    def _trim_prompt_block(self, text: str, token_budget: int, *, char_cap: int = 12_000) -> str:
        normalized = " ".join(str(text).strip().split())
        if not normalized:
            return ""
        clipped = normalized[:char_cap]
        while clipped and estimate_tokens(clipped) > token_budget:
            shrink_to = max(240, int(len(clipped) * 0.82))
            if shrink_to >= len(clipped):
                break
            clipped = clipped[:shrink_to].rstrip()
        if clipped != normalized:
            clipped = clipped.rstrip(" .,;:") + " ..."
        return clipped

    def _topic_relevance_score(
        self,
        text: str,
        *,
        topic: str,
        positions: dict[str, str] | None = None,
    ) -> float:
        focus = "\n".join(
            part for part in [topic, *(positions or {}).values()] if str(part).strip()
        )
        return self._intelligence_similarity(text, focus)

    def _topic_anchor_text(
        self,
        topic: str,
        *,
        transcript: list[dict[str, Any]] | None = None,
    ) -> str:
        positions = self.debate_positions(topic)
        recent_turns = list(transcript or [])[-4:]
        recent_scores = [
            self._topic_relevance_score(
                str(turn.get("content", "")),
                topic=topic,
                positions=positions,
            )
            for turn in recent_turns
            if str(turn.get("content", "")).strip()
        ]
        average_recent = sum(recent_scores) / len(recent_scores) if recent_scores else 1.0
        if recent_scores and average_recent < 0.08:
            drift_note = (
                "Drift check: the latest turns started leaning into side issues. "
                "Refocus on the original question and the Pro/Con starting positions below."
            )
        else:
            drift_note = "Drift check: stay anchored to the original question below, even if recent turns opened a tangent."
        return dedent(
            f"""
            ORIGINAL TOPIC: {topic}
            PRO STARTING POSITION: {positions["pro"]}
            CON STARTING POSITION: {positions["con"]}
            {drift_note}
            """
        ).strip()

    def _transcript_for_model(
        self,
        transcript: list[dict[str, Any]],
        *,
        model_name: str,
        reserve_tokens: int,
        hard_turn_cap: int,
        context_window: int | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        if not transcript:
            return []
        if context_window is not None:
            if context_window <= 0:
                return []
            hard_turn_cap = min(hard_turn_cap, max(1, context_window * 8))
        prompt_budget = max(700, self._model_context_limit(model_name) - max(400, reserve_tokens))
        per_turn_char_limit = 900 if prompt_budget <= 10_000 else 1_400
        candidate_turns = transcript[-hard_turn_cap:]
        trimmed_candidates: list[dict[str, Any]] = []
        for order, turn in enumerate(candidate_turns):
            content = self._trim_prompt_block(
                str(turn.get("content", "")),
                max(120, prompt_budget // 3),
                char_cap=per_turn_char_limit,
            )
            trimmed_candidates.append({**turn, "content": content, "_order": order})

        if not topic:
            selected: list[dict[str, Any]] = []
            used_tokens = 0
            for turn in reversed(trimmed_candidates):
                projected = used_tokens + estimate_tokens(str(turn.get("content", ""))) + 18
                if selected and projected > prompt_budget:
                    break
                selected.append(turn)
                used_tokens = projected
            return [{k: v for k, v in turn.items() if k != "_order"} for turn in reversed(selected)]

        positions = self.debate_positions(topic)
        recent_keep = min(len(trimmed_candidates), max(4, min(8, (context_window or 2) * 2)))
        recent_turns = trimmed_candidates[-recent_keep:]
        selected_by_order = {int(turn["_order"]): turn for turn in recent_turns}
        older_turns = trimmed_candidates[:-recent_keep]
        ranked_older = sorted(
            older_turns,
            key=lambda turn: (
                self._topic_relevance_score(
                    str(turn.get("content", "")),
                    topic=topic,
                    positions=positions,
                ),
                float(turn["_order"]),
            ),
            reverse=True,
        )
        used_tokens = sum(estimate_tokens(str(turn.get("content", ""))) + 18 for turn in selected_by_order.values())
        for turn in ranked_older:
            relevance = self._topic_relevance_score(
                str(turn.get("content", "")),
                topic=topic,
                positions=positions,
            )
            if relevance <= 0:
                continue
            projected = used_tokens + estimate_tokens(str(turn.get("content", ""))) + 18
            if selected_by_order and projected > prompt_budget:
                continue
            selected_by_order[int(turn["_order"])] = turn
            used_tokens = projected
        ordered = [
            {k: v for k, v in turn.items() if k != "_order"}
            for _, turn in sorted(selected_by_order.items(), key=lambda item: item[0])
        ]
        return ordered

    def _chat_history_for_model(
        self,
        history: list[dict[str, Any]],
        *,
        model_name: str,
        reserve_tokens: int,
    ) -> list[dict[str, Any]]:
        if not history:
            return []
        prompt_budget = max(600, self._model_context_limit(model_name) - max(400, reserve_tokens))
        selected: list[dict[str, Any]] = []
        used_tokens = 0
        for message in reversed(history[-24:]):
            content = self._trim_prompt_block(str(message.get("content", "")), max(120, prompt_budget // 4), char_cap=1200)
            projected = used_tokens + estimate_tokens(content) + 20
            if selected and projected > prompt_budget:
                break
            selected.append({**message, "content": content})
            used_tokens = projected
        return list(reversed(selected))

    def _fit_messages_to_model(
        self,
        messages: list[dict[str, str]],
        *,
        model_name: str,
        reserve_tokens: int,
    ) -> list[dict[str, str]]:
        fitted = [{**message} for message in messages]
        prompt_budget = max(800, self._model_context_limit(model_name) - max(400, reserve_tokens))
        mutable_indexes = [index for index, message in enumerate(fitted) if message.get("role") != "system"]
        while mutable_indexes and estimate_messages_tokens(fitted) > prompt_budget:
            largest_index = max(
                mutable_indexes,
                key=lambda index: estimate_tokens(str(fitted[index].get("content", ""))),
            )
            current = str(fitted[largest_index].get("content", ""))
            trimmed = self._trim_prompt_block(
                current,
                max(160, int(estimate_tokens(current) * 0.72)),
                char_cap=max(320, int(len(current) * 0.76)),
            )
            if trimmed == current:
                mutable_indexes.remove(largest_index)
                continue
            fitted[largest_index]["content"] = trimmed
        return fitted

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None


    def _council_settings_snapshot(self) -> dict[str, Any]:
        return self.db.get_council_settings()

    def _team_agents(self, session_settings: dict[str, Any], team_id: str) -> list[dict[str, Any]]:
        return [agent for agent in self._active_debate_agents(session_settings) if agent["team"] == team_id]

    async def _prepare_team_notebooks(
        self,
        *,
        session_id: str,
        debate_id: str,
        topic: str,
        session_settings: dict[str, Any],
        selected_model: SupportedModel,
        cost_tracker: CostTracker | None,
    ) -> None:
        council_settings = self._council_settings_snapshot()
        depth = str(council_settings.get("debate_intelligence_depth", "Normal"))
        max_tokens = {"Light": 0, "Normal": 220, "Deep": 360}.get(depth, 220)
        for team in TEAM_DEFINITIONS:
            team_id = team["team"]
            running_notes: list[str] = []
            agents = self._team_agents(session_settings, team_id)
            for agent in agents:
                experience = self._experience_context(session_id, agent["role"], session_settings)
                if depth == "Light":
                    content = self._fallback_notebook(topic, team, agent, running_notes, experience)
                    model_name = "system"
                else:
                    model = self._resolve_agent_model(session_settings, agent["archetype"], selected_model)
                    generation_settings = {
                        **self._agent_generation_settings(session_settings, agent["archetype"]),
                        "max_tokens": min(
                            max_tokens,
                            int(self._agent_generation_settings(session_settings, agent["archetype"]).get("max_tokens", max_tokens)),
                        ),
                    }
                    messages = self._private_notebook_messages(
                        topic=topic,
                        team=team,
                        agent=agent,
                        running_notes=running_notes,
                        experience=experience,
                        depth=depth,
                    )
                    try:
                        content = await self._private_completion(
                            model=model,
                            messages=messages,
                            generation_settings=generation_settings,
                            cost_tracker=cost_tracker,
                            operation=f"Private notebook - {agent['speaker']}",
                        )
                    except Exception as exc:
                        runtime_diary.record(
                            "backend terminal",
                            "private notebook fallback",
                            f"{agent['speaker']} notebook fell back to deterministic summary: {exc}",
                            session_id=session_id,
                        )
                        content = self._fallback_notebook(topic, team, agent, running_notes, experience)
                    model_name = model.name
                running_notes.append(f"{agent['speaker']}: {self._clip_for_prompt(content, 360)}")
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="team_notebook",
                    team=team_id,
                    role=agent["role"],
                    agent_id=agent["role"],
                    title=f"{agent['speaker']} private notebook",
                    content=content,
                    status="Ready",
                    confidence=1.0,
                    payload={
                        "speaker": agent["speaker"],
                        "model": model_name,
                        "depth": depth,
                        "visible_to_user": True,
                        "private_from_opponent": True,
                    },
                    basis=[{"type": "private_preparation", "topic": topic}],
                )

    def _private_notebook_messages(
        self,
        *,
        topic: str,
        team: dict[str, str],
        agent: dict[str, Any],
        running_notes: list[str],
        experience: str,
        depth: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are {agent['speaker']} preparing a private team notebook for the user-visible Team Room.
                    This is not hidden chain-of-thought. Produce only structured artifacts that can be shown to the user.
                    Team: {team['team_label']} ({team['stance']}).
                    Job: {agent['job']}
                    Never invent past experience. If no experience exists, say no experience is recorded yet.
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Topic: {topic}
                    Preparation depth: {depth}

                    Experience available:
                    {experience or "No reliable experience recorded yet."}

                    Existing team notes:
                    {chr(10).join(running_notes) if running_notes else "No previous team notes yet."}

                    Write concise structured notes with these labels:
                    - Current role objective
                    - Useful past experience, if any
                    - Planned contribution
                    - Weakness or risk to watch
                    - What the public Advocate should remember
                    """
                ).strip(),
            },
        ]

    async def _private_completion(
        self,
        *,
        model: SupportedModel,
        messages: list[dict[str, str]],
        generation_settings: dict[str, Any],
        cost_tracker: CostTracker | None,
        operation: str,
    ) -> str:
        if settings.mock_llm:
            content = sanitize_model_text(
                f"Current role objective: prepare reliable structured notes. Planned contribution: {messages[-1]['content'][:180]}"
            )
            if cost_tracker is not None:
                cost_tracker.record_call(
                    model_name=model.name,
                    input_text=message_input_text(messages),
                    output_text=content,
                    operation=operation,
                )
            return content
        route = model.route
        if acompletion is None or route is None:
            raise DebateError(f"Private notebook model unavailable for {model.name}.")
        candidate_models = (route.litellm_model, *route.fallback_models)
        last_exc: Exception | None = None
        response = None
        for candidate_model in candidate_models:
            try:
                _kwargs: dict = dict(
                    model=candidate_model,
                    messages=messages,
                    api_key=route.api_key,
                    stream=False,
                    temperature=min(0.4, float(generation_settings.get("temperature", 0.4))),
                    max_tokens=int(generation_settings.get("max_tokens", 220)),
                    timeout=min(settings.request_timeout_seconds, 45),
                )
                if route.api_base:
                    _kwargs["api_base"] = route.api_base
                response = await acompletion(**_kwargs)
                break
            except Exception as exc:
                last_exc = exc
                continue
        if response is None:
            if last_exc is None:
                raise DebateError(f"{model.name} failed while preparing private notes: no response received")
            self._maybe_disable_model_route(model, last_exc)
            raise DebateError(
                f"{model.name} failed while preparing private notes: {self._provider_error_message(last_exc)}"
            ) from last_exc
        text = sanitize_model_text(self._completion_text(response).strip())
        if cost_tracker is not None:
            cost_tracker.record_call(
                model_name=model.name,
                input_text=message_input_text(messages),
                output_text=text,
                operation=operation,
            )
        if not text:
            raise EmptyCompletionError(f"{model.name} returned an empty private notebook.")
        return text

    def _fallback_notebook(
        self,
        topic: str,
        team: dict[str, str],
        agent: dict[str, Any],
        running_notes: list[str],
        experience: str,
    ) -> str:
        return dedent(
            f"""
            Current role objective: {agent['job']}
            Useful past experience: {experience or 'No reliable experience recorded yet.'}
            Planned contribution: Help the {team['team_label']} team argue its assigned side on {topic}.
            Weakness or risk to watch: Do not invent evidence, overclaim, or ignore high-pressure challenges.
            What the public Advocate should remember: Use this role's contribution only when it directly helps the current phase.
            """
        ).strip()

    def _experience_context(
        self, session_id: str, agent_id: str, session_settings: dict[str, Any]) -> str:
        if not session_settings.get("use_experience", True):
            return "Experience use is off for this chat."
        council_settings = self._council_settings_snapshot()
        if not council_settings.get("use_agent_identity_profiles", True):
            return "Agent identity profiles are off in Council Settings."
        records = self.db.list_agent_experience(
            agent_id=agent_id,
            session_id=session_id,
            include_universal=bool(council_settings.get("universal_experience", True)),
            limit=6,
        )
        if not records:
            return "No reliable experience recorded yet."
        return "\n".join(
            f"- {record['lesson']} (confidence: {record['confidence']}; basis records: {len(record.get('basis') or [])})"
            for record in records
        )

    def _intelligence_context(
        self,
        *,
        session_id: str,
        debate_id: str,
        agent: dict[str, Any] | None,
        session_settings: dict[str, Any],
    ) -> str:
        records = self.db.list_intelligence_records(session_id, debate_id)
        if not records:
            experience = self._experience_context(session_id, agent["role"], session_settings) if agent else ""
            return experience or "No structured debate intelligence recorded yet."
        team = agent.get("team") if agent else None
        relevant = []
        for record in records[-24:]:
            if record["record_type"] == "team_notebook" and team and record.get("team") not in {team, ""}:
                continue
            relevant.append(record)
        lines = []
        if agent:
            lines.append("Relevant experience:")
            lines.append(self._experience_context(session_id, agent["role"], session_settings))
        lines.append("Structured records:")
        for record in relevant[-16:]:
            label = record["record_type"].replace("_", " ").title()
            team_label = f" [{record['team'].upper()}]" if record.get("team") else ""
            status = f" ({record['status']})" if record.get("status") else ""
            lines.append(f"- {label}{team_label}{status}: {self._clip_for_prompt(record['title'] + ': ' + record['content'], 260)}")
        return "\n".join(lines)

    def _split_candidate_sentences(self, content: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", sanitize_model_text(content)).strip()
        if not cleaned:
            return []
        parts = re.findall(r"[^.!?。！？]+[.!?。！？]?", cleaned)
        return [part.strip() for part in parts if 35 <= len(part.strip()) <= 260]

    def _intelligence_tokens(self, text: str) -> set[str]:
        latin = set(re.findall(r"[a-zA-Z][a-zA-Z0-9']*", text.lower()))
        cjk = set(CJK_CHAR_RE.findall(text))
        return {token for token in [*latin, *cjk] if token}

    def _intelligence_similarity(self, left: str, right: str) -> float:
        left_tokens = self._intelligence_tokens(left)
        right_tokens = self._intelligence_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _intelligence_confidence(self, sentence: str, *, kind: str, urls: list[str] | None = None) -> float:
        urls = urls or []
        lowered = sentence.lower()
        score = 0.42
        if kind == "claim":
            if any(marker in lowered for marker in ("because", "therefore", "shows", "proves", "means", "should", "must")):
                score += 0.12
            if any(marker in sentence for marker in ("应该", "必须", "说明", "证明", "意味着")):
                score += 0.12
        elif kind == "challenge":
            if QUESTION_END_RE.search(sentence):
                score += 0.15
            if any(marker in lowered for marker in ("contradict", "unanswered", "unsupported", "fails", "weak", "burden")):
                score += 0.08
        elif kind == "evidence":
            score += 0.08
            if urls:
                score += 0.2
        if len(sentence) > 120:
            score += 0.05
        if len(self._intelligence_tokens(sentence)) >= 10:
            score += 0.05
        return max(0.2, min(0.92, round(score, 2)))

    def _resolve_pending_challenges(
        self,
        *,
        session_id: str,
        debate_id: str,
        responding_team: str,
        agent: dict[str, Any],
        phase: dict[str, Any],
        content: str,
    ) -> None:
        response_tokens = self._intelligence_tokens(content)
        if not response_tokens:
            return
        records = self.db.list_intelligence_records(session_id, debate_id)
        pending = [
            record
            for record in records
            if record.get("record_type") == "challenge"
            and str(record.get("status") or "").lower() == "unanswered"
            and str((record.get("payload") or {}).get("target_team") or "") == responding_team
        ]
        answer_cues = (
            "because",
            "the answer is",
            "to answer",
            "that point fails",
            "that concern fails",
            "you asked",
            "yes,",
            "no,",
            "first,",
        )
        for record in pending[-6:]:
            challenge_text = str(record.get("content") or "")
            similarity = self._intelligence_similarity(challenge_text, content)
            direct_response = any(cue in content.lower() for cue in answer_cues)
            status = None
            if similarity >= 0.22 or (similarity >= 0.14 and direct_response):
                status = "Answered"
            elif similarity >= 0.1 or (direct_response and similarity >= 0.04):
                status = "Partially answered"
            if not status:
                continue
            payload = dict(record.get("payload") or {})
            payload.update(
                {
                    "resolved_by": agent["role"],
                    "resolved_phase_key": phase["key"],
                    "resolved_phase_title": phase["title"],
                    "resolution_similarity": round(similarity, 3),
                }
            )
            basis = list(record.get("basis") or [])
            basis.append(
                {
                    "type": "response_match",
                    "speaker": agent["speaker"],
                    "phase_key": phase["key"],
                }
            )
            confidence = max(float(record.get("confidence") or 0), 0.72 if status == "Answered" else 0.58)
            self.db.update_intelligence_record(
                str(record["id"]),
                status=status,
                confidence=confidence,
                payload=payload,
                basis=basis,
            )

    def _finalize_pending_challenges(self, session_id: str, debate_id: str, transcript: list[dict[str, Any]]) -> None:
        records = self.db.list_intelligence_records(session_id, debate_id)
        last_turn_index: dict[str, int] = {}
        for index, turn in enumerate(transcript):
            team = str(turn.get("team") or "")
            if team:
                last_turn_index[team] = index
        for record in records:
            if record.get("record_type") != "challenge":
                continue
            if str(record.get("status") or "").lower() != "unanswered":
                continue
            target_team = str((record.get("payload") or {}).get("target_team") or "")
            challenge_index = -1
            challenge_basis = list(record.get("basis") or [])
            for item in challenge_basis:
                if not isinstance(item, dict):
                    continue
                phase_key = str(item.get("phase_key") or "")
                speaker = str(item.get("speaker") or "")
                if not phase_key:
                    continue
                for index, turn in enumerate(transcript):
                    if (
                        str(turn.get("phase_key") or "") == phase_key
                        and (not speaker or str(turn.get("speaker") or "") == speaker)
                    ):
                        challenge_index = index
                        break
                if challenge_index >= 0:
                    break
            if target_team and target_team in last_turn_index:
                if challenge_index >= 0 and last_turn_index[target_team] > challenge_index:
                    final_status = "Ignored"
                else:
                    final_status = "Unanswered"
            else:
                final_status = "Unanswered"
            payload = dict(record.get("payload") or {})
            payload["finalized_at_close"] = True
            self.db.update_intelligence_record(
                str(record["id"]),
                status=final_status,
                confidence=max(float(record.get("confidence") or 0), 0.52),
                payload=payload,
            )

    def _capture_turn_intelligence(
        self,
        *,
        session_id: str,
        debate_id: str,
        agent: dict[str, Any],
        phase: dict[str, Any],
        content: str,
    ) -> None:
        sentences = self._split_candidate_sentences(content)
        basis = [{"speaker": agent["speaker"], "phase_key": phase["key"], "phase_title": phase["title"]}]
        role = agent["role"]
        team = agent["team"]
        self._resolve_pending_challenges(
            session_id=session_id,
            debate_id=debate_id,
            responding_team=team,
            agent=agent,
            phase=phase,
            content=content,
        )
        claim_terms = re.compile(r"\b(should|must|because|therefore|means|proves|shows|better|worse|risk|benefit|cost|fair|unfair)\b|应该|必须|因为|说明|证明|更好|更差|风险|好处|成本", re.I)
        challenge_terms = re.compile(r"\b(unanswered|unsupported|fails?|cannot|does not|has not|contradicts?|weak|problem|burden)\b", re.I)
        claim_count = 0
        challenge_count = 0
        for sentence in sentences:
            if QUESTION_END_RE.search(sentence) and challenge_count < 2:
                challenge_count += 1
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="challenge",
                    team=team,
                    role=role,
                    agent_id=role,
                    title=f"Challenge from {agent['speaker']}",
                    content=sentence,
                    status="Unanswered",
                    confidence=self._intelligence_confidence(sentence, kind="challenge"),
                    payload={
                        "target_team": "con" if team == "pro" else "pro",
                        "impact": "medium",
                        "phase_kind": phase.get("kind"),
                        "keywords": sorted(self._intelligence_tokens(sentence))[:14],
                    },
                    basis=basis,
                )
                continue
            if challenge_terms.search(sentence) and challenge_count < 2:
                challenge_count += 1
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="challenge",
                    team=team,
                    role=role,
                    agent_id=role,
                    title=f"Objection from {agent['speaker']}",
                    content=sentence,
                    status="Unanswered",
                    confidence=self._intelligence_confidence(sentence, kind="challenge"),
                    payload={
                        "target_team": "con" if team == "pro" else "pro",
                        "impact": "medium",
                        "phase_kind": phase.get("kind"),
                        "keywords": sorted(self._intelligence_tokens(sentence))[:14],
                    },
                    basis=basis,
                )
                continue
            if claim_terms.search(sentence) and claim_count < 2:
                claim_count += 1
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="claim",
                    team=team,
                    role=role,
                    agent_id=role,
                    title=f"Claim from {agent['speaker']}",
                    content=sentence,
                    status="Introduced",
                    confidence=self._intelligence_confidence(sentence, kind="claim"),
                    payload={
                        "phase_kind": phase.get("kind"),
                        "keywords": sorted(self._intelligence_tokens(sentence))[:14],
                    },
                    basis=basis,
                )
        urls = re.findall(r"https?://[^\s)\]]+", content)
        if urls or agent.get("archetype") == "evidence_researcher":
            source_type = "live_url" if urls else "model_knowledge"
            evidence_text = urls[0] if urls else (sentences[0] if sentences else self._clip_for_prompt(content, 240))
            self.db.add_intelligence_record(
                session_id=session_id,
                debate_id=debate_id,
                record_type="evidence",
                team=team,
                role=role,
                agent_id=role,
                title=f"Evidence note from {agent['speaker']}",
                content=evidence_text,
                status="Verified URL" if urls else "Model knowledge, not live verified",
                confidence=self._intelligence_confidence(evidence_text, kind="evidence", urls=urls),
                payload={"source_type": source_type, "url": urls[0] if urls else "", "verified": bool(urls)},
                basis=basis,
            )
            if not urls and agent.get("archetype") == "evidence_researcher":
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="value_record",
                    team=team,
                    role=role,
                    agent_id=role,
                    title="Evidence honesty note",
                    content="Researcher evidence was recorded as model knowledge because no live source URL was present.",
                    status="Notice",
                    confidence=1.0,
                    payload={"value": "evidence_honesty"},
                    basis=basis,
                )

    def _finalize_debate_intelligence(
        self,
        *,
        session_id: str,
        debate_id: str,
        topic: str,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        judge_summary: str,
        session_settings: dict[str, Any],
    ) -> None:
        self._finalize_pending_challenges(session_id, debate_id, transcript)
        records = self.db.list_intelligence_records(session_id, debate_id)
        claims = [record for record in records if record["record_type"] == "claim"]
        challenges = [record for record in records if record["record_type"] == "challenge"]
        evidence = [record for record in records if record["record_type"] == "evidence"]
        winner = self._detect_winner(judge_summary)
        scorecard = {
            "winner": winner,
            "claim_count": len(claims),
            "challenge_count": len(challenges),
            "evidence_count": len(evidence),
            "unanswered_challenges": sum(
                1 for item in challenges if str(item.get("status") or "").lower() in {"unanswered", "ignored"}
            ),
            "judge_mode": session_settings.get("judge_mode", "Hybrid"),
            "evidence_strictness": session_settings.get("evidence_strictness", "Normal"),
        }
        self.db.add_intelligence_record(
            session_id=session_id,
            debate_id=debate_id,
            record_type="judge_scorecard",
            title="Judge scorecard inputs",
            content=(
                f"Winner detected: {winner}. Claims: {len(claims)}. Challenges: {len(challenges)}. "
                f"Evidence records: {len(evidence)}. Unanswered challenge records: {scorecard['unanswered_challenges']}."
            ),
            status="Completed",
            confidence=0.75 if winner != "unclear" else 0.45,
            payload=scorecard,
            basis=[{"type": "judge_summary", "debate_id": debate_id}],
        )
        self.db.add_intelligence_record(
            session_id=session_id,
            debate_id=debate_id,
            record_type="post_debate_review",
            title="Post-debate review summary",
            content=self._post_debate_review_text(topic, scorecard, judge_summary),
            status="Ready for user feedback",
            confidence=0.7,
            payload={"feedback_pending": True, **scorecard},
            basis=[{"type": "judge_summary", "debate_id": debate_id}],
        )
        if self._council_settings_snapshot().get("use_value_consequence_system", True):
            if scorecard["unanswered_challenges"] > 0:
                self.db.add_intelligence_record(
                    session_id=session_id,
                    debate_id=debate_id,
                    record_type="value_record",
                    title="Debate quality consequence",
                    content=f"{scorecard['unanswered_challenges']} challenge record(s) remained marked unanswered; future audits should check dropped arguments carefully.",
                    status="Audit strictness note",
                    confidence=0.8,
                    payload={"value": "debate_quality", "future_effect": "check_dropped_arguments"},
                    basis=[{"type": "challenge_records", "count": scorecard["unanswered_challenges"]}],
                )
        self._save_agent_experience(session_id, debate_id, records, scorecard)

    def _detect_winner(self, judge_summary: str) -> str:
        text = re.sub(r"\s+", " ", judge_summary.lower()).strip()
        if not text:
            return "unclear"
        pro_aliases = (
            "pro",
            "pro team",
            "pro advocate",
            "affirmative",
            "supporting side",
            "supporting team",
            "in favor",
        )
        con_aliases = (
            "con",
            "con team",
            "con advocate",
            "con case",
            "con side",
            "negative",
            "opposing side",
            "opposing team",
        )
        comparison_winner = self._detect_comparison_winner(text)
        if comparison_winner != "unclear":
            return comparison_winner
        candidate_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text)
            if sentence.strip()
            and any(
                re.search(pattern, sentence)
                for pattern in (
                    r"\bwin(?:s|ning|ner)?\b",
                    r"\bverdict\b",
                    r"\bstronger\s+case\b",
                    r"\bbetter\s+case\b",
                    r"\bwinning\s+position\b",
                    r"\bedges?\s+out\b",
                    r"\btakes?\s+the\s+debate\b",
                    r"\bfavors?\b",
                    r"\bi\s+side\s+with\b",
                )
            )
        ]
        for sentence in candidate_sentences or [text]:
            comparison_winner = self._detect_comparison_winner(sentence)
            if comparison_winner != "unclear":
                return comparison_winner
            pro_hit = any(re.search(rf"\b{re.escape(alias)}\b", sentence) for alias in pro_aliases)
            con_hit = any(re.search(rf"\b{re.escape(alias)}\b", sentence) for alias in con_aliases)
            if pro_hit and con_hit:
                nearby_winner = self._detect_nearby_winner_signal(
                    sentence, pro_aliases, con_aliases
                )
                if nearby_winner != "unclear":
                    return nearby_winner
            if pro_hit and not con_hit:
                return "pro"
            if con_hit and not pro_hit:
                return "con"
        return "unclear"

    def _detect_nearby_winner_signal(
        self, sentence: str, pro_aliases: tuple[str, ...], con_aliases: tuple[str, ...]
    ) -> str:
        signal_matches = list(
            re.finditer(
                r"\b(win(?:s|ning|ner)?|stronger case|better case|winning position|prevails?|favou?rs?|takes? the debate|edges? out)\b",
                sentence,
            )
        )
        if not signal_matches:
            return "unclear"
        side_positions: list[tuple[str, int]] = []
        for side, aliases in (("pro", pro_aliases), ("con", con_aliases)):
            for alias in aliases:
                for match in re.finditer(rf"\b{re.escape(alias)}\b", sentence):
                    side_positions.append((side, match.start()))
        if not side_positions:
            return "unclear"
        for signal in signal_matches:
            nearest = min(side_positions, key=lambda item: abs(item[1] - signal.start()))
            if abs(nearest[1] - signal.start()) <= 80:
                return nearest[0]
        return "unclear"

    def _detect_comparison_winner(self, text: str) -> str:
        side_aliases = {
            "pro": r"(?:pro|pro\s+team|pro\s+advocate|pro\s+case|pro\s+side|affirmative)",
            "con": r"(?:con|con\s+team|con\s+advocate|con\s+case|con\s+side|negative)",
        }
        winner_verbs = (
            r"edges?\s+out",
            r"beats?",
            r"defeats?",
            r"outweighs?",
            r"prevails?\s+over",
            r"wins?\s+over",
            r"wins?\s+against",
            r"has\s+the\s+stronger\s+case\s+than",
            r"is\s+stronger\s+than",
            r"is\s+more\s+persuasive\s+than",
        )
        loser_verbs = (
            r"loses?\s+to",
            r"falls?\s+to",
            r"is\s+weaker\s+than",
            r"is\s+less\s+persuasive\s+than",
        )
        for winner, loser in (("pro", "con"), ("con", "pro")):
            if re.search(
                rf"\b{side_aliases[winner]}\b[\s\S]{{0,80}}\b(?:{'|'.join(winner_verbs)})\b[\s\S]{{0,80}}\b{side_aliases[loser]}\b",
                text,
            ):
                return winner
        for loser, winner in (("pro", "con"), ("con", "pro")):
            if re.search(
                rf"\b{side_aliases[loser]}\b[\s\S]{{0,80}}\b(?:{'|'.join(loser_verbs)})\b[\s\S]{{0,80}}\b{side_aliases[winner]}\b",
                text,
            ):
                return winner
        return "unclear"

    def _normalize_judge_summary(self, judge_summary: str, topic: str) -> str:
        cleaned = sanitize_model_text(judge_summary).strip()
        if not cleaned:
            return cleaned
        winner = self._detect_winner(cleaned)
        winner_labels = {
            "pro": "WINNER: Pro",
            "con": "WINNER: Con",
            "unclear": "WINNER: Unclear",
        }
        first_nonempty = next((line.strip() for line in cleaned.splitlines() if line.strip()), "")
        if first_nonempty.upper().startswith("WINNER:"):
            return cleaned
        if winner == "pro":
            reason_line = "Reason: The Pro side made the stronger case on this debate question."
        elif winner == "con":
            reason_line = "Reason: The Con side made the stronger case on this debate question."
        else:
            reason_line = f"Reason: The judge did not clearly resolve a winner for {self._clip_for_prompt(topic, 120)}."
        return f"{winner_labels[winner]}\n{reason_line}\n\n{cleaned}"

    def _judging_settings(self, session_settings: dict[str, Any]) -> dict[str, Any]:
        raw = session_settings.get("judging_settings")
        payload = raw if isinstance(raw, dict) else {}
        try:
            panel_size = int(payload.get("judge_panel_size", 1))
        except (TypeError, ValueError):
            panel_size = 1
        if panel_size not in {1, 3, 5}:
            panel_size = 1
        try:
            analytics_weight = float(payload.get("analytics_weight", 0.25))
        except (TypeError, ValueError):
            analytics_weight = 0.25
        return {
            "judge_panel_size": panel_size,
            "analytics_weight": max(0.0, min(0.75, analytics_weight)),
            "allow_user_verdict_challenge": bool(
                payload.get("allow_user_verdict_challenge", True)
            ),
        }

    def _analytics_verdict_signal(self, analysis: dict[str, Any]) -> dict[str, Any]:
        probabilities = (
            analysis.get("bayesian", {}).get("probabilities", {})
            if isinstance(analysis, dict)
            else {}
        )
        values = {
            "support": self._safe_float(probabilities.get("support"), 0.0),
            "oppose": self._safe_float(probabilities.get("oppose"), 0.0),
            "mixed": self._safe_float(probabilities.get("mixed"), 0.0),
        }
        if not any(values.values()):
            return {
                "winner": "unclear",
                "leader": "mixed",
                "confidence": 0.0,
                "probabilities": values,
            }
        leader = max(values, key=values.get)
        winner_by_leader = {"support": "pro", "oppose": "con", "mixed": "unclear"}
        winner = winner_by_leader.get(leader, "unclear")
        confidence = max(0.0, min(1.0, values[leader]))
        if confidence < 0.38:
            winner = "unclear"
        return {
            "winner": winner,
            "leader": leader,
            "confidence": confidence,
            "probabilities": values,
        }

    def _weighted_verdict_result(
        self,
        ai_votes: list[str],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
    ) -> dict[str, Any]:
        judging = self._judging_settings(session_settings)
        analytics_weight = judging["analytics_weight"]
        vote_counts = {"pro": 0, "con": 0, "unclear": 0}
        for vote in ai_votes:
            vote_counts[vote if vote in vote_counts else "unclear"] += 1
        total_votes = max(1, sum(vote_counts.values()))
        analytics_signal = self._analytics_verdict_signal(analysis)
        signal_winner = str(analytics_signal.get("winner") or "unclear")
        confidence = self._safe_float(analytics_signal.get("confidence"), 0.0)
        effective_analytics_weight = analytics_weight * confidence
        scores = {
            side: (1.0 - effective_analytics_weight) * (count / total_votes)
            for side, count in vote_counts.items()
        }
        if signal_winner not in scores:
            signal_winner = "unclear"
        if effective_analytics_weight > 0:
            scores[signal_winner] += effective_analytics_weight
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner = ranked[0][0]
        tie_gap = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else 1.0
        if len(ranked) > 1 and tie_gap < 0.04:
            winner = "unclear"
        return {
            "winner": winner,
            "scores": {key: round(value, 3) for key, value in scores.items()},
            "vote_counts": vote_counts,
            "analytics_signal": analytics_signal,
            "analytics_weight": analytics_weight,
            "effective_analytics_weight": effective_analytics_weight,
            "tie_gap": round(tie_gap, 3),
            "tie_threshold": 0.04,
            "tie": len(ranked) > 1 and tie_gap < 0.04,
        }

    def _safe_float(self, value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _winner_label(self, winner: str) -> str:
        return {"pro": "Pro", "con": "Con", "unclear": "Unclear"}.get(winner, "Unclear")

    def _summary_without_verdict_header(self, summary: str) -> str:
        lines = summary.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip().upper().startswith("WINNER:"):
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip().lower().startswith("reason:"):
            lines.pop(0)
        return "\n".join(lines).strip()

    def _apply_analytics_weighted_summary(
        self,
        summary: str,
        topic: str,
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
    ) -> str:
        normalized = self._normalize_judge_summary(summary, topic)
        ai_winner = self._detect_winner(normalized)
        result = self._weighted_verdict_result([ai_winner], analysis, session_settings)
        final_winner = result["winner"]
        signal = result["analytics_signal"]
        scores = result["scores"]
        reason = (
            f"The AI Judge voted {self._winner_label(ai_winner)}, while analytics signaled "
            f"{self._winner_label(str(signal.get('winner') or 'unclear'))} with "
            f"{round(self._safe_float(signal.get('confidence')) * 100)}% confidence; "
            f"the weighted result favors {self._winner_label(final_winner)}."
        )
        if result.get("tie"):
            reason = (
                f"{reason} The weighted scores were close enough to treat the result as unresolved because the top-score gap was only {result['tie_gap']} against a {result['tie_threshold']} tie threshold."
            )
        note = (
            f"Weighted verdict note: analytics weight {round(result['analytics_weight'] * 100)}%. "
            f"Scores: Pro {scores['pro']}, Con {scores['con']}, Unclear {scores['unclear']}."
        )
        if result.get("tie"):
            note = (
                f"{note} Tie rule: if the top weighted-score gap stays below {result['tie_threshold']}, the result becomes Unclear."
            )
        body = self._summary_without_verdict_header(normalized)
        return (
            f"WINNER: {self._winner_label(final_winner)}\n"
            f"Reason: {reason}\n\n"
            f"{note}\n\n"
            f"{body}"
        ).strip()

    def _compose_panel_consensus_summary(
        self,
        *,
        topic: str,
        panel_summaries: list[str],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
    ) -> str:
        panel_votes = [self._detect_winner(summary) for summary in panel_summaries]
        result = self._weighted_verdict_result(panel_votes, analysis, session_settings)
        signal = result["analytics_signal"]
        scores = result["scores"]
        vote_counts = result["vote_counts"]
        final_winner = result["winner"]
        vote_text = (
            f"Pro {vote_counts['pro']}, Con {vote_counts['con']}, "
            f"Unclear {vote_counts['unclear']}"
        )
        reason = (
            f"The independent judge panel voted {vote_text}; analytics signaled "
            f"{self._winner_label(str(signal.get('winner') or 'unclear'))} at "
            f"{round(self._safe_float(signal.get('confidence')) * 100)}% confidence. "
            f"After weighting, {self._winner_label(final_winner)} is the final verdict."
        )
        if result.get("tie"):
            reason = (
                f"{reason} The panel/analytics scores were effectively tied, so the final result is marked unclear because the top-score gap was only {result['tie_gap']} against a {result['tie_threshold']} tie threshold."
            )
        panel_notes = []
        for index, summary in enumerate(panel_summaries, start=1):
            winner = self._winner_label(self._detect_winner(summary))
            body = self._summary_without_verdict_header(self._normalize_judge_summary(summary, topic))
            panel_notes.append(
                f"{index}. Judge Panelist {index}: {winner}. "
                f"{self._clip_for_prompt(body, 240) or 'No short rationale captured.'}"
            )
        return dedent(
            f"""
            WINNER: {self._winner_label(final_winner)}
            Reason: {reason}

            Panel votes: {vote_text}.
            Analytics weight: {round(result['analytics_weight'] * 100)}%.
            Weighted scores: Pro {scores['pro']}, Con {scores['con']}, Unclear {scores['unclear']}.

            Panel rationales:
            {chr(10).join(panel_notes)}

            Clear winner: {self._winner_label(final_winner)}
            Why it wins: the final decision combines independent AI judge votes with the tracked claim/challenge/evidence analytics instead of relying on one unstructured verdict.
            """
        ).strip()

    def _post_debate_review_text(self, topic: str, scorecard: dict[str, Any], judge_summary: str) -> str:
        return dedent(
            f"""
            Topic: {topic}
            Winner detected from Judge text: {scorecard['winner']}
            Debate objects recorded: {scorecard['claim_count']} claim(s), {scorecard['challenge_count']} challenge(s), {scorecard['evidence_count']} evidence item(s).
            Unanswered challenge records: {scorecard['unanswered_challenges']}.
            Judge summary basis: {self._clip_for_prompt(judge_summary, 500)}
            """
        ).strip()

    def _save_agent_experience(
        self,
        session_id: str,
        debate_id: str,
        records: list[dict],
        scorecard: dict[str, Any],
    ) -> None:
        council_settings = self._council_settings_snapshot()
        scope = "universal" if council_settings.get("universal_experience", True) else "chat"
        grouped: dict[str, dict[str, int]] = {}
        for record in records:
            agent_id = record.get("agent_id") or record.get("role") or "council"
            grouped.setdefault(agent_id, {"claim": 0, "challenge": 0, "evidence": 0, "value_record": 0})
            if record["record_type"] in grouped[agent_id]:
                grouped[agent_id][record["record_type"]] += 1
        unresolved_by_target = {"pro": 0, "con": 0}
        verified_evidence_by_agent: dict[str, int] = {}
        for record in records:
            if record.get("record_type") == "challenge" and str(record.get("status") or "").lower() in {"unanswered", "ignored"}:
                target_team = str((record.get("payload") or {}).get("target_team") or "")
                if target_team in unresolved_by_target:
                    unresolved_by_target[target_team] += 1
            if record.get("record_type") == "evidence" and (record.get("payload") or {}).get("verified"):
                agent_id = record.get("agent_id") or record.get("role") or "council"
                verified_evidence_by_agent[agent_id] = verified_evidence_by_agent.get(agent_id, 0) + 1
        for agent_id, counts in grouped.items():
            total = sum(counts.values())
            if total == 0:
                continue
            team = "pro" if str(agent_id).startswith("pro_") else "con" if str(agent_id).startswith("con_") else ""
            unresolved_for_team = unresolved_by_target.get(team, 0)
            takeaways = []
            if counts["challenge"] > 0:
                takeaways.append(f"surface pressure points clearly ({counts['challenge']} challenge record(s))")
            if verified_evidence_by_agent.get(agent_id, 0) > 0:
                takeaways.append(
                    f"reuse evidence-backed support when relevant ({verified_evidence_by_agent[agent_id]} verified evidence item(s))"
                )
            if unresolved_for_team > 0 and "advocate" in str(agent_id):
                takeaways.append(
                    f"answer unresolved attacks before closing ({unresolved_for_team} challenge record(s) remained open on this side)"
                )
            if not takeaways:
                takeaways.append("review the latest tracked claims and challenges before the next public turn")
            lesson = (
                f"Observed in debate {debate_id[:8]}: created {counts['claim']} claim record(s), "
                f"{counts['challenge']} challenge record(s), {counts['evidence']} evidence record(s), "
                f"and {counts['value_record']} value note(s). Winner detected: {scorecard['winner']}. "
                f"Actionable next-use note based on recorded debate objects: {', '.join(takeaways)}. "
                "This is factual debate history, not an invented trait."
            )
            self.db.add_agent_experience(
                scope=scope,
                session_id=session_id if scope == "chat" else None,
                agent_id=agent_id,
                lesson_type="debate_activity",
                lesson=lesson,
                confidence="medium",
                basis=[
                    {
                        "debate_id": debate_id,
                        "counts": counts,
                        "winner": scorecard["winner"],
                        "unresolved_for_team": unresolved_for_team,
                        "verified_evidence": verified_evidence_by_agent.get(agent_id, 0),
                    }
                ],
            )
        self.db.add_intelligence_record(
            session_id=session_id,
            debate_id=debate_id,
            record_type="memory_saved",
            title="Experience memory saved",
            content=f"Saved factual activity records for {len(grouped)} agent(s) using {scope} scope. No invented strengths or weaknesses were created.",
            status="Saved",
            confidence=1.0,
            payload={"scope": scope, "agent_count": len(grouped)},
            basis=[{"type": "structured_debate_records", "debate_id": debate_id}],
        )

    async def _stream_agent_turn(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        agent: dict[str, Any],
        model: SupportedModel,
        phase: dict[str, Any],
        transcript: list[dict[str, Any]],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        cost_tracker: CostTracker | None = None,
        intelligence_context: str = "",
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": agent["role"],
                    "speaker": agent["speaker"],
                    "model": model.name,
                    "content": "",
                    "phase_key": phase["key"],
                    "phase_title": phase["title"],
                    "phase_index": phase["index"],
                    "phase_total": phase["total"],
                    "phase_kind": phase["kind"],
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": phase["index"],
            }
        )

        messages = self._agent_messages(
            topic,
            agent,
            phase,
            transcript,
            session_settings,
            generation_settings,
            model,
            intelligence_context,
        )
        cost_start = len(cost_tracker.entries) if cost_tracker else 0
        try:
            content = await self._stream_completion(
                websocket,
                stream_id,
                model,
                messages,
                session_settings=generation_settings,
                cost_tracker=cost_tracker,
                cost_operation=agent["speaker"],
            )
        except ClientDisconnectedError:
            raise
        except Exception as exc:
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role=agent["role"],
                speaker=agent["speaker"],
                model=model.name,
                exc=exc,
                phase=phase,
            )
            raise
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role=agent["role"],
            speaker=agent["speaker"],
            model=model.name,
            content=content,
            cost_summary=cost_tracker.summary_since(
                cost_start, session_settings.get("cost_currency", "USD")
            )
            if cost_tracker
            else None,
            phase=phase,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved}
        )
        return content

    async def _stream_final_judgment(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        selected_model: SupportedModel,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
        judge_assistant_report: str,
        cost_tracker: CostTracker | None = None,
        intelligence_context: str = "",
    ) -> str:
        judging = self._judging_settings(session_settings)
        judge_model = self._resolve_agent_model(session_settings, "judge", selected_model)
        generation_settings = self._agent_generation_settings(session_settings, "judge")
        panel_size = int(judging["judge_panel_size"])
        if panel_size == 1:
            return await self._stream_judge_turn(
                websocket=websocket,
                session_id=session_id,
                debate_id=debate_id,
                topic=topic,
                model=judge_model,
                transcript=transcript,
                analysis=analysis,
                session_settings=session_settings,
                generation_settings=generation_settings,
                judge_assistant_report=judge_assistant_report,
                cost_tracker=cost_tracker,
                intelligence_context=intelligence_context,
                apply_weighted_verdict=True,
            )

        panel_summaries: list[str] = []
        temperature_offsets = [0.0, -0.08, 0.08, -0.14, 0.14]
        for index in range(panel_size):
            panel_generation = dict(generation_settings)
            panel_generation["temperature"] = max(
                0.0,
                min(
                    1.0,
                    self._safe_float(generation_settings.get("temperature"), 0.55)
                    + temperature_offsets[index],
                ),
            )
            panel_summaries.append(
                await self._stream_judge_turn(
                    websocket=websocket,
                    session_id=session_id,
                    debate_id=debate_id,
                    topic=topic,
                    model=judge_model,
                    transcript=transcript,
                    analysis=analysis,
                    session_settings=session_settings,
                    generation_settings=panel_generation,
                    judge_assistant_report=judge_assistant_report,
                    cost_tracker=cost_tracker,
                    intelligence_context=intelligence_context,
                    role="judge_panelist",
                    speaker=f"Judge Panelist {index + 1}",
                    panelist_index=index + 1,
                    apply_weighted_verdict=False,
                )
            )

        consensus = self._compose_panel_consensus_summary(
            topic=topic,
            panel_summaries=panel_summaries,
            analysis=analysis,
            session_settings=session_settings,
        )
        return await self._stream_static_judge_summary(
            websocket=websocket,
            session_id=session_id,
            debate_id=debate_id,
            model_name=f"{judge_model.name} panel consensus",
            content=consensus,
            cost_tracker=cost_tracker,
            session_settings=session_settings,
        )

    async def _stream_static_judge_summary(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        model_name: str,
        content: str,
        cost_tracker: CostTracker | None,
        session_settings: dict[str, Any],
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": "judge",
                    "speaker": "Judge",
                    "model": model_name,
                    "content": "",
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": "summary",
            },
        )
        await self._send_json(
            websocket,
            {"type": "message_replaced", "stream_id": stream_id, "content": content},
        )
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="judge",
            speaker="Judge",
            model=model_name,
            content=content,
            cost_summary=None,
            debate_cost_summary=cost_tracker.summary(session_settings.get("cost_currency", "USD"))
            if cost_tracker
            else None,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved},
        )
        return content

    async def _stream_judge_turn(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        model: SupportedModel,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        judge_assistant_report: str,
        cost_tracker: CostTracker | None = None,
        intelligence_context: str = "",
        role: str = "judge",
        speaker: str = "Judge",
        panelist_index: int | None = None,
        apply_weighted_verdict: bool = True,
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": role,
                    "speaker": speaker,
                    "model": model.name,
                    "content": "",
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": "summary",
            }
        )
        messages = self._judge_messages(
            topic,
            transcript,
            analysis,
            session_settings,
            generation_settings,
            model,
            judge_assistant_report,
            intelligence_context,
        )
        if panelist_index is not None:
            messages[0]["content"] = (
                f"You are Judge Panelist {panelist_index}. Vote independently from the other panelists. "
                "Do not try to predict or harmonize with the panel. "
                + messages[0]["content"]
            )
        cost_start = len(cost_tracker.entries) if cost_tracker else 0
        try:
            content = await self._stream_completion(
                websocket,
                stream_id,
                model,
                messages,
                session_settings=generation_settings,
                cost_tracker=cost_tracker,
                cost_operation=speaker,
            )
            content = self._normalize_judge_summary(content, topic)
            if apply_weighted_verdict:
                content = self._apply_analytics_weighted_summary(
                    content, topic, analysis, session_settings
                )
            await self._send_json(
                websocket,
                {"type": "message_replaced", "stream_id": stream_id, "content": content}
            )
        except ClientDisconnectedError:
            raise
        except Exception as exc:
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role=role,
                speaker=speaker,
                model=model.name,
                exc=exc,
                cost_summary=cost_tracker.summary_since(
                    cost_start, session_settings.get("cost_currency", "USD")
                )
                if cost_tracker
                else None,
                debate_cost_summary=cost_tracker.summary(session_settings.get("cost_currency", "USD"))
                if cost_tracker
                else None,
            )
            raise
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role=role,
            speaker=speaker,
            model=model.name,
            content=content,
            cost_summary=cost_tracker.summary_since(
                cost_start, session_settings.get("cost_currency", "USD")
            )
            if cost_tracker
            else None,
            debate_cost_summary=cost_tracker.summary(session_settings.get("cost_currency", "USD"))
            if cost_tracker
            else None,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved}
        )
        return content

    async def _stream_judge_assistant_turn(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        debate_id: str,
        topic: str,
        model: SupportedModel,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        cost_tracker: CostTracker | None = None,
        intelligence_context: str = "",
    ) -> str:
        stream_id = str(uuid4())
        await self._send_json(
            websocket,
            {
                "type": "message_started",
                "stream_id": stream_id,
                "message": {
                    "id": stream_id,
                    "session_id": session_id,
                    "debate_id": debate_id,
                    "role": "judge_assistant",
                    "speaker": "Judge Assistant",
                    "model": model.name,
                    "content": "",
                    "sequence": 0,
                    "created_at": utc_now(),
                },
                "round": "summary",
            }
        )
        messages = self._judge_assistant_messages(
            topic,
            transcript,
            analysis,
            session_settings,
            generation_settings,
            model,
            intelligence_context,
        )
        cost_start = len(cost_tracker.entries) if cost_tracker else 0
        try:
            content = await self._stream_completion(
                websocket,
                stream_id,
                model,
                messages,
                session_settings=generation_settings,
                cost_tracker=cost_tracker,
                cost_operation="Judge Assistant",
            )
        except ClientDisconnectedError:
            raise
        except Exception as exc:
            await self._save_failed_stream_message(
                websocket=websocket,
                stream_id=stream_id,
                session_id=session_id,
                debate_id=debate_id,
                role="judge_assistant",
                speaker="Judge Assistant",
                model=model.name,
                exc=exc,
                cost_summary=cost_tracker.summary_since(
                    cost_start, session_settings.get("cost_currency", "USD")
                )
                if cost_tracker
                else None,
            )
            raise
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="judge_assistant",
            speaker="Judge Assistant",
            model=model.name,
            content=content,
            cost_summary=cost_tracker.summary_since(
                cost_start, session_settings.get("cost_currency", "USD")
            )
            if cost_tracker
            else None,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved}
        )
        return content

    async def _save_failed_stream_message(
        self,
        *,
        websocket: WebSocket,
        stream_id: str,
        session_id: str,
        debate_id: str,
        role: str,
        speaker: str,
        model: str,
        exc: Exception,
        cost_summary: dict | None = None,
        debate_cost_summary: dict | None = None,
        phase: dict | None = None,
    ) -> str:
        content = self._failure_message(exc)
        await self._send_json(
            websocket,
            {"type": "message_replaced", "stream_id": stream_id, "content": content}
        )
        saved = self.db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role=role,
            speaker=speaker,
            model=model,
            content=content,
            cost_summary=cost_summary,
            debate_cost_summary=debate_cost_summary,
            phase=phase,
        )
        await self._send_json(
            websocket,
            {"type": "message_completed", "stream_id": stream_id, "message": saved}
        )
        return content

    def _failure_message(self, exc: Exception) -> str:
        return f"This AI response cannot be generated due to this error: {self._provider_error_message(exc)}"

    def _exception_text(self, exc: Exception) -> str:
        original = exc.original if isinstance(exc, CompletionStreamError) else exc
        seen: set[int] = set()
        parts: list[str] = []

        def add(value: object) -> None:
            text = self._clean_error_text(value)
            if text and text not in parts:
                parts.append(text)

        current: object = original
        while isinstance(current, BaseException) and id(current) not in seen:
            seen.add(id(current))
            for attr in ("message", "error", "detail", "status_code", "code", "type"):
                if hasattr(current, attr):
                    add(getattr(current, attr))
            add(str(current))
            current = (
                getattr(current, "original_exception", None)
                or getattr(current, "original", None)
                or current.__cause__
            )

        if not parts:
            parts.append(original.__class__.__name__)
        return " | ".join(parts)

    def _maybe_disable_model_route(self, model: SupportedModel, exc: Exception) -> None:
        route = model.route
        if route is None:
            return
        lowered = self._exception_text(exc).lower()
        if any(
            marker in lowered
            for marker in (
                "unknown model",
                "model not found",
                "does not exist",
                "invalid model",
                "not found the model",
                "permission denied",
                "unsupported model",
                "not support",
            )
        ):
            mark_model_unavailable(model.name, self._exception_text(exc))

    def _provider_error_message(self, exc: Exception) -> str:
        message = self._exception_text(exc)
        lowered = message.lower()
        if any(marker in lowered for marker in ("529", "overloaded", "high load")):
            return f"Provider is overloaded or under high load. Retry shortly. Details: {message}"
        if "rate limit" in lowered or "429" in lowered:
            return f"Provider rate limit reached. Wait a little or choose another unlocked model. Details: {message}"
        if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered or "401" in lowered:
            return f"Provider authentication failed. Check the API key for this model's provider. Details: {message}"
        if (
            "permission denied" in lowered
            or "not found the model" in lowered
            or "not found" in lowered
            or "404" in lowered
            or "model" in lowered and "does not exist" in lowered
        ):
            return (
                "This model is not available for the current API key or endpoint. "
                "The app has hidden it for now. Choose another verified model. "
                f"Details: {message}"
            )
        return message

    def _clean_error_text(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            try:
                text = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                text = str(value)
        else:
            text = str(value)
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        text = re.sub(
            r"(?i)(api[_-]?key|authorization|bearer|token|secret)(['\"=: ]+)([A-Za-z0-9._\-]{8,})",
            r"\1\2[redacted]",
            text,
        )
        text = re.sub(
            r"\b(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|gsk_[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,})\b",
            "[redacted]",
            text,
        )
        text = re.sub(r"/Users/[^\s'\"<>]+", "[local-path]", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1200]

    async def _send_json(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except Exception as exc:
            if self._is_client_disconnect_error(exc):
                raise ClientDisconnectedError(
                    "Browser disconnected before the response finished."
                ) from exc
            raise

    def _is_client_disconnect_error(self, exc: Exception) -> bool:
        if isinstance(exc, (ClientDisconnectedError, WebSocketDisconnect)):
            return True
        name = exc.__class__.__name__.lower()
        text = str(exc).lower()
        return (
            name in {"clientdisconnected", "connectionclosedok", "connectionclosederror"}
            or "cannot call \"send\" once a close message has been sent" in text
            or "connection closed" in text
            or "websocketdisconnect" in name
        )

    async def _stream_completion(
        self,
        websocket: WebSocket,
        stream_id: str,
        model: SupportedModel,
        messages: list[dict[str, str]],
        session_settings: dict[str, Any] | None = None,
        cost_tracker: CostTracker | None = None,
        cost_operation: str = "completion",
    ) -> str:
        if settings.mock_llm:
            content = await self._stream_mock_completion(websocket, stream_id, model, messages)
            if cost_tracker is not None:
                cost_tracker.record_call(
                    model_name=model.name,
                    input_text=message_input_text(messages),
                    output_text=content,
                    operation=cost_operation,
                )
            return content

        if acompletion is None:
            raise DebateError("LiteLLM is not installed. Run pip install -r backend/requirements.txt.")
        route = model.route
        if route is None:
            raise DebateError(f"{model.api_key_env} is missing for {model.name}.")

        generation_settings = session_settings or {}
        fitted_messages = self._fit_messages_to_model(
            messages,
            model_name=model.name,
            reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 600,
        )
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                content, finish_reason = await self._stream_completion_once(
                    websocket,
                    stream_id,
                    model,
                    route,
                    fitted_messages,
                    generation_settings,
                )
                remaining_continuations = 3
                while finish_reason in {"length", "max_tokens"} and remaining_continuations > 0:
                    runtime_diary.record(
                        "backend terminal",
                        "stream continuation",
                        f"Response truncated (finish_reason={finish_reason}). "
                        f"Continuing ({4 - remaining_continuations}/3)... "
                        f"Current length: {len(content)} chars.",
                    )
                    content, finish_reason = await self._continue_truncated_completion(
                        websocket,
                        stream_id,
                        model,
                        fitted_messages,
                        content,
                        generation_settings,
                    )
                    remaining_continuations -= 1
                if cost_tracker is not None:
                    cost_tracker.record_call(
                        model_name=model.name,
                        input_text=message_input_text(fitted_messages),
                        output_text=content,
                        operation=cost_operation,
                    )
                runtime_diary.record(
                    "backend terminal",
                    "stream completed",
                    f"Model {model.name} finished. "
                    f"Final length: {len(content)} chars, "
                    f"finish_reason: {finish_reason}.",
                )
                return content
            except EmptyCompletionError:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                raise
            except ClientDisconnectedError:
                raise
            except CompletionStreamError as exc:
                self._maybe_disable_model_route(model, exc.original)
                if self._is_client_disconnect_error(exc.original):
                    raise ClientDisconnectedError(
                        "Browser disconnected before the response finished."
                    ) from exc.original
                if (
                    self._is_retryable_provider_error(exc.original)
                    and not exc.had_output
                    and attempt < max_attempts - 1
                ):
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                raise DebateError(
                    f"{model.name} failed through LiteLLM: {self._provider_error_message(exc.original)}"
                ) from exc.original

        raise DebateError(f"{model.name} failed through LiteLLM after retries.")

    async def _stream_completion_once(
        self,
        websocket: WebSocket,
        stream_id: str,
        model: SupportedModel,
        route,
        messages: list[dict[str, str]],
        generation_settings: dict[str, Any],
    ) -> tuple[str, str | None]:
        parts: list[str] = []
        finish_reason: str | None = None
        sanitizer = StreamingSanitizer()
        candidate_models = (route.litellm_model, *route.fallback_models)
        last_exc: Exception | None = None
        chunk_timeout = 60  # seconds to wait for a single chunk before treating as stalled
        for candidate_model in candidate_models:
            sanitizer = StreamingSanitizer()
            parts = []
            finish_reason = None
            try:
                _kwargs: dict = dict(
                    model=candidate_model,
                    messages=messages,
                    api_key=route.api_key,
                    stream=True,
                    temperature=float(generation_settings.get("temperature", 0.55)),
                    max_tokens=int(generation_settings.get("max_tokens", 2048)),
                    timeout=settings.request_timeout_seconds,
                )
                if route.api_base:
                    _kwargs["api_base"] = route.api_base
                response = await acompletion(**_kwargs)
                chunk_count = 0
                response_iter = response.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(response_iter.__anext__(), timeout=chunk_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        runtime_diary.record(
                            "backend terminal",
                            "stream timeout",
                            f"Model {candidate_model} stalled. Timing out chunk generation after {chunk_timeout} seconds."
                        )
                        finish_reason = "length"
                        break
                    chunk_count += 1
                    finish_reason = self._extract_finish_reason(chunk) or finish_reason
                    delta = self._extract_delta(chunk)
                    if not delta:
                        continue
                    visible_delta = sanitizer.push(delta)
                    if not visible_delta:
                        continue
                    parts.append(visible_delta)
                    await self._send_json(
                        websocket,
                        {"type": "message_delta", "stream_id": stream_id, "delta": visible_delta}
                    )
                tail = sanitizer.flush()
                if tail:
                    parts.append(tail)
                    await self._send_json(
                        websocket,
                        {"type": "message_delta", "stream_id": stream_id, "delta": tail}
                    )
                runtime_diary.record(
                    "backend terminal",
                    "stream chunks received",
                    f"Model {candidate_model}: {chunk_count} chunks, "
                    f"{len(parts)} visible parts, "
                    f"finish_reason={finish_reason}.",
                )
                break
            except Exception as exc:
                last_exc = exc
                if self._is_client_disconnect_error(exc):
                    raise ClientDisconnectedError(
                        "Browser disconnected before the response finished."
                    ) from exc
                if parts:
                    runtime_diary.record(
                        "backend terminal",
                        "stream error with partial output",
                        f"Model {candidate_model} errored after {len(parts)} parts: {exc}",
                    )
                    raise CompletionStreamError(exc, had_output=True) from exc
                runtime_diary.record(
                    "backend terminal",
                    "stream error no output",
                    f"Model {candidate_model} failed with no output: {exc}. Trying next fallback.",
                )
                continue
        else:
            if last_exc is None:
                raise EmptyCompletionError(f"{model.name} returned no response after all retries.")
            raise CompletionStreamError(last_exc, had_output=False) from last_exc

        content = sanitize_model_text("".join(parts)).strip()
        if not content:
            raise EmptyCompletionError(f"{model.name} returned an empty response.")
        return content, finish_reason

    async def _continue_truncated_completion(
        self,
        websocket: WebSocket,
        stream_id: str,
        model: SupportedModel,
        messages: list[dict[str, str]],
        existing_content: str,
        generation_settings: dict[str, Any],
    ) -> tuple[str, str | None]:
        continuation_settings = {
            **generation_settings,
            "max_tokens": max(1024, int(generation_settings.get("max_tokens", 2048))),
        }
        continuation_messages = [
            *messages,
            {"role": "assistant", "content": existing_content[-4000:]},
            {
                "role": "user",
                "content": (
                    "Continue exactly where the previous answer stopped. Do not repeat earlier text. "
                    "Finish the remaining required sections briefly and end cleanly."
                ),
            },
        ]
        separator = "" if existing_content.endswith((" ", "\n", "-", "/", "(")) else "\n"
        if separator:
            await self._send_json(
                websocket,
                {"type": "message_delta", "stream_id": stream_id, "delta": separator}
            )
        try:
            route = model.route
            if route is None:
                raise DebateError(f"{model.api_key_env} is missing for {model.name}.")
            continuation, finish_reason = await self._stream_completion_once(
                websocket,
                stream_id,
                model,
                route,
                continuation_messages,
                continuation_settings,
            )
        except CompletionStreamError as exc:
            notice = (
                "\n\n_Response stopped early because the provider interrupted the continuation. "
                "Try increasing this role's Max tokens or retrying the message._"
            )
            await self._send_json(
                websocket,
                {"type": "message_delta", "stream_id": stream_id, "delta": notice}
            )
            return f"{existing_content}{separator}{notice}", "error"

        combined = f"{existing_content}{separator}{continuation}".strip()
        return combined, finish_reason

    def _is_retryable_provider_error(self, exc: Exception) -> bool:
        text = self._provider_error_message(exc).lower()
        return any(
            marker in text
            for marker in (
                "529",
                "503",
                "504",
                "502",
                "overloaded",
                "high load",
                "temporarily unavailable",
                "timeout",
                "api connection",
                "connectionerror",
                "rate limit",
            )
        )

    async def _stream_mock_completion(
        self,
        websocket: WebSocket,
        stream_id: str,
        model: SupportedModel,
        messages: list[dict[str, str]],
    ) -> str:
        prompt = messages[-1]["content"]
        content = sanitize_model_text(
            f"{model.name}: {prompt[:220]} "
            "The central tradeoff is clear, but the strongest answer depends on evidence, incentives, and failure modes."
        )
        for word in content.split(" "):
            delta = word + " "
            await asyncio.sleep(0.04)
            await self._send_json(
                websocket,
                {"type": "message_delta", "stream_id": stream_id, "delta": delta}
            )
        return content.strip()

    def _agent_messages(
        self,
        topic: str,
        agent: dict[str, Any],
        phase: dict[str, Any],
        transcript: list[dict[str, Any]],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
        intelligence_context: str = "",
    ) -> list[dict[str, str]]:
        latest_speaker = transcript[-1]["speaker"] if transcript else "the previous speaker"
        previous_debate = self._format_transcript(
            self._transcript_for_model(
                transcript,
                model_name=model.name,
                reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 1400,
                hard_turn_cap=24,
                context_window=int(session_settings.get("context_window", 2)),
                topic=topic,
            )
        )
        topic_anchor = self._trim_prompt_block(
            self._topic_anchor_text(topic, transcript=transcript),
            220,
            char_cap=1200,
        )
        response_length = generation_settings.get("response_length", "Normal")
        word_limit = {"Concise": 200, "Normal": 400, "Detailed": 700}.get(response_length, 400)
        intelligence_excerpt = self._trim_prompt_block(intelligence_context, 900, char_cap=5000)
        recent_self_turns = [
            self._clip_for_prompt(str(turn.get("content", "")), 200)
            for turn in transcript
            if turn.get("speaker") == agent["speaker"]
        ][-2:]
        repetition_guard = (
            "\nRecent points you already made:\n- " + "\n- ".join(recent_self_turns)
            if recent_self_turns
            else "\nNo prior turns from you yet."
        )
        advanced_notes = []
        if agent["archetype"] == "evidence_researcher" and generation_settings.get("agent_web_search"):
            advanced_notes.append(
                "Web-search mode is enabled for this researcher. Cite real source URLs only if you actually used a live source. If no live source is available, write 'No live citations used' instead of inventing citations."
            )
        if session_settings.get("fact_check_mode"):
            advanced_notes.append(
                "Fact-check mode is enabled; flag uncertain factual claims and separate evidence from interpretation."
            )
        advanced_prompt = "\n".join(advanced_notes) or "No extra advanced constraints."
        phase_kind = str(phase.get("kind", "turn"))
        phase_rules = {
            "constructive": "Build your side's case. Use clear claims, reasons, stakes, and limits. Do not drift into judging.",
            "cross_exam": "Ask questions only after one short setup sentence. Ask 2-4 pointed questions. Do not answer your own questions and do not deliver a full rebuttal.",
            "answer_rebuttal": "Answer the strongest questions directly, then repair your own case or attack the other side where useful.",
            "evidence": "Add evidence, examples, and uncertainty notes. If web search is unavailable, do not invent citations; mark claims that need verification.",
            "rebuttal": "Synthesize weaknesses in the other team's case and defend your own side from the strongest pressure.",
            "discussion": "Only the Advocate speaks in discussion. Speak for the whole team, using teammate evidence, criticism, and cross-exam points from the transcript. Respond naturally to specific argument content, not turn numbers.",
            "closing": "Give a concise final appeal that rebuilds your side, answers the most damaging objections, and names the voting issue.",
        }.get(phase_kind, "Complete this debate phase naturally and stay in role.")
        user_prompt = dedent(
            f"""
            Debate anchor:
            {topic_anchor}

            Current phase: {phase["title"]} ({phase["index"]}/{phase["total"]})
            Phase goal: {phase["intent"]}
            Target to address: {phase["target"]}
            Phase instruction: {phase["instruction"]}

            Debate so far:
            {previous_debate}

            Latest speaker to answer: {latest_speaker}.

            Team notebook, experience, and pressure state:
            {intelligence_excerpt or "No structured debate intelligence is available yet."}
            {repetition_guard}

            Speak naturally as {agent["speaker"]}. Address another debater directly when useful, like a human debate.
            Prefer direct phrasing such as "{latest_speaker}, you said..." or "I disagree with your point about...".
            Do not narrate the debate with phrases like "my opponent says", "my opponent argues", "the opponent says", or "the opposing side says".
            Address specific arguments by content, not by turn number or step number.
            Phase-specific rules: {phase_rules}
            Do your role's job, stay on the {agent["stance_label"]}, and keep this turn under {word_limit} words.
            If you disagree, say exactly what you disagree with and why. If you add evidence, explain how it changes the debate.
            Add at least one genuinely new move relative to your earlier turns: answer a challenge, add evidence, concede a limit, or sharpen the clash. Do not just restate your previous paragraph with synonyms.
            """
        ).strip()
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are {agent["speaker"]} in a Jubidate AI strategic council.
                    Team: {agent["team_label"]} ({agent["stance"]}).
                    Your job: {agent["job"]}
                    Debate tone: {session_settings.get("debate_tone", "Academic")}.
                    Language: {session_settings.get("language", "English")}.
                    You are already this debater. Never say the user wants you to act as this role.
                    Never expose hidden reasoning, chain-of-thought, planning notes, or <think> blocks.
                    Advanced constraints: {advanced_prompt}
                    Use polished Markdown when useful.
                    Be responsive to the actual prior speaker, not generic. Stay in role and do not judge the debate.
                    You are in the room with the other debaters. Use their speaker names or second-person address; do not say "my opponent" or "the opponent".
                    Follow the professional phase flow exactly. Do not skip ahead to judging or closing unless the current phase asks for it.
                    """
                ).strip(),
            },
            {"role": "user", "content": user_prompt},
        ]

    def _judge_assistant_messages(
        self,
        topic: str,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
        intelligence_context: str = "",
    ) -> list[dict[str, str]]:
        response_length = generation_settings.get("response_length", "Normal")
        word_limit = {"Concise": 350, "Normal": 600, "Detailed": 1000}.get(response_length, 600)
        transcript_excerpt = self._format_transcript(
            self._transcript_for_model(
                transcript,
                model_name=model.name,
                reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 1800,
                hard_turn_cap=48,
                topic=topic,
            )
        )
        topic_anchor = self._trim_prompt_block(
            self._topic_anchor_text(topic, transcript=transcript),
            240,
            char_cap=1400,
        )
        intelligence_excerpt = self._trim_prompt_block(intelligence_context, 1000, char_cap=6000)
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are the Judge Assistant. You are neutral and you do not choose the final winner.
                    Your job is to help the Judge by finding missed points, unanswered claims, evidence gaps, contradictions, and useful statistics.
                    The debate follows a professional phase flow. Use phase labels in the transcript to tell whether a point came from constructive, cross-examination, evidence, rebuttal, discussion, or closing.
                    Discussion phases are Advocate-only team spokesperson exchanges; do not penalize missing Researcher/Critic/Examiner discussion turns there.
                    Never expose hidden reasoning, planning notes, or <think> blocks.
                    Tone: {session_settings.get("debate_tone", "Academic")}.
                    Language: {session_settings.get("language", "English")}.
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Debate anchor:
                    {topic_anchor}

                    Transcript:
                    {transcript_excerpt}

                    Debate analytics:
                    {format_analytics_report(analysis)}

                    Structured debate intelligence:
                    {intelligence_excerpt or "No structured debate intelligence is available yet."}

                    Produce a Judge Assistant audit under {word_limit} words:
                    - Strongest Pro points
                    - Strongest Con points
                    - Unanswered or underanswered points
                    - Evidence quality warnings
                    - Statistics the Judge should consider
                    - What the Judge must not overlook

                    Do not name a final winner.
                    """
                ).strip(),
            },
        ]

    def _judge_messages(
        self,
        topic: str,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
        judge_assistant_report: str,
        intelligence_context: str = "",
    ) -> list[dict[str, str]]:
        assistant_section = self._trim_prompt_block(
            judge_assistant_report or "Judge Assistant disabled for this debate.",
            900,
            char_cap=5000,
        )
        response_length = generation_settings.get("response_length", "Normal")
        configured_word_limit = {"Concise": 350, "Normal": 600, "Detailed": 1000}.get(
            response_length, 600
        )
        token_word_limit = max(300, int(int(generation_settings.get("max_tokens", 2048)) * 0.5))
        word_limit = min(configured_word_limit, token_word_limit)
        transcript_excerpt = self._format_transcript(
            self._transcript_for_model(
                transcript,
                model_name=model.name,
                reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 2200,
                hard_turn_cap=56,
                topic=topic,
            )
        )
        topic_anchor = self._trim_prompt_block(
            self._topic_anchor_text(topic, transcript=transcript),
            260,
            char_cap=1500,
        )
        intelligence_excerpt = self._trim_prompt_block(intelligence_context, 1100, char_cap=7000)
        return [
            {
                "role": "system",
                "content": (
                    "You are the Judge AI. You are already the final arbiter of this debate. "
                    "Never mention that the user wants you to judge. Never expose hidden reasoning or <think> blocks. "
                    "The transcript is phase-structured; respect what each phase was supposed to do. "
                    "Give a concrete, confident verdict. Pick a winner, state exactly why, and identify what would change your mind. "
                    "Start with a single unmistakable first line in exactly one of these forms: "
                    "'WINNER: Pro', 'WINNER: Con', or 'WINNER: Unclear'. "
                    "On the second line, write 'Reason: ...' in one sentence. "
                    "If space is tight, use shorter bullets instead of leaving the verdict unfinished."
                ),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Debate anchor:
                    {topic_anchor}

                    Transcript:
                    {transcript_excerpt}

                    Judge Assistant audit:
                    {assistant_section}

                    Debate analytics:
                    {format_analytics_report(analysis)}

                    Structured debate intelligence and scorecard inputs:
                    {intelligence_excerpt or "No structured debate intelligence is available yet."}

                    Judge mode: {session_settings.get("judge_mode", "Hybrid")}
                    Evidence strictness: {session_settings.get("evidence_strictness", "Normal")}

                    Produce a concise verdict with:
                    0. First line: WINNER: Pro, WINNER: Con, or WINNER: Unclear
                    0b. Second line: Reason: one-sentence explanation
                    1. Best affirmative argument
                    2. Best skeptical argument
                    3. Best evidence or research need
                    4. Where the analytics agree or disagree with your own judgment
                    5. Clear winner: name the winning statement or stance
                    6. Why it wins, with concrete criteria

                    Tone: {session_settings.get("debate_tone", "Academic")}
                    Language: {session_settings.get("language", "English")}
                    Response length: {response_length}
                    Hard limit: under {word_limit} words. Finish all 6 sections.
                    """
                ).strip(),
            },
        ]

    def _practice_debater_messages(
        self,
        *,
        session_id: str,
        topic: str,
        human_side: str,
        ai_side: str,
        transcript: list[dict[str, Any]],
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
        is_last_round: bool,
    ) -> list[dict[str, str]]:
        practice_settings = self._practice_settings(session_settings)
        transcript_excerpt = self._format_transcript(
            self._transcript_for_model(
                transcript,
                model_name=model.name,
                reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 1600,
                hard_turn_cap=28,
                topic=topic,
            )
        )
        profile_context = self._practice_profile_context(session_settings)
        human_label = human_side.upper()
        ai_label = ai_side.upper()
        last_round_note = (
            "This is the final structured round. Make a clear closing appeal explaining why your side should win, while directly answering the user's strongest point."
            if is_last_round
            else "This is an active practice turn. Respond naturally, advance your side, and keep the debate moving."
        )
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are Practice Debater, an AI sparring partner for human debate training.
                    You are the {ai_label} side. The human user is the {human_label} side.
                    Debate like a strong but fair human opponent: answer the user's actual point, press the strongest weakness, and make your side better.
                    Address the user directly as "you" when referring to their arguments.
                    Do not say "my opponent says" or describe yourself as following a user request.
                    Never reveal hidden reasoning or <think> blocks.
                    {last_round_note}

                    Difficulty: {practice_settings.get("opponent_difficulty", "Adaptive")}
                    Training focus: {practice_settings.get("training_focus", "Full Debate")}
                    Tone: {session_settings.get("debate_tone", "Academic")}
                    Language: {session_settings.get("language", "English")}
                    Response length: {generation_settings.get("response_length", "Normal")}
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Practice debate topic:
                    {topic}

                    User debate profile:
                    {profile_context}

                    Transcript so far:
                    {transcript_excerpt or "No public turns yet."}

                    Your next move:
                    - Defend the {ai_label} side.
                    - Respond to the user's latest substantive claim.
                    - Add one useful pressure point or clarification.
                    - Keep it concise enough for a human practice exchange.
                    """
                ).strip(),
            },
        ]

    def _debate_trainer_messages(
        self,
        *,
        session_id: str,
        topic: str,
        human_side: str,
        ai_side: str,
        transcript: list[dict[str, Any]],
        analysis: dict[str, Any],
        judge_summary: str,
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
    ) -> list[dict[str, str]]:
        practice_settings = self._practice_settings(session_settings)
        transcript_excerpt = self._format_transcript(
            self._transcript_for_model(
                transcript,
                model_name=model.name,
                reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 2200,
                hard_turn_cap=40,
                topic=topic,
            )
        )
        profile_context = self._practice_profile_context(session_settings)
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are the Debate Trainer. You are a supportive, precise debate coach.
                    Your goal is to help the human user improve, not to flatter them.
                    Use only the transcript, Judge result, analytics, and saved profile below. Do not invent facts.
                    Give practical advice the user can try next time.
                    Never reveal hidden reasoning or <think> blocks.

                    Coaching style: {practice_settings.get("trainer_style", "Coach")}
                    Training focus: {practice_settings.get("training_focus", "Full Debate")}
                    Language: {session_settings.get("language", "English")}
                    Response length: {generation_settings.get("response_length", "Normal")}
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Practice topic: {topic}
                    Human side: {human_side.upper()}
                    Practice Debater side: {ai_side.upper()}

                    Saved user debate profile:
                    {profile_context}

                    Transcript:
                    {transcript_excerpt}

                    Judge result:
                    {judge_summary}

                    Analytics:
                    {format_analytics_report(analysis)}

                    Write a coach report with:
                    1. Overall diagnosis
                    2. What you did well
                    3. What cost you the most
                    4. Dropped or under-answered arguments
                    5. Style profile and the kind of opponent you handled well or poorly
                    6. Three concrete drills for the next practice debate
                    7. One sentence goal for next time
                    """
                ).strip(),
            },
        ]

    def _practice_profile_context(self, session_settings: dict[str, Any]) -> str:
        practice_settings = self._practice_settings(session_settings)
        council_settings = self._council_settings_snapshot()
        if not practice_settings.get("use_user_profile", True) or not council_settings.get(
            "use_user_debate_profile", True
        ):
            return "User debate profile is off for this chat or council."
        profile = self.db.get_user_debate_profile()
        strengths = "; ".join(str(item) for item in (profile.get("strengths") or [])[-3:])
        weaknesses = "; ".join(str(item) for item in (profile.get("weaknesses") or [])[-3:])
        notes = "; ".join(str(item) for item in (profile.get("trainer_notes") or [])[-3:])
        return dedent(
            f"""
            Practice debates completed: {int(profile.get("practice_debates_completed", 0) or 0)}
            Side history: {profile.get("side_history") if isinstance(profile.get("side_history"), dict) else {}}
            Recent strengths: {strengths or "none recorded yet"}
            Recent improvement targets: {weaknesses or "none recorded yet"}
            Recent trainer notes: {notes or "none recorded yet"}
            Use this as private coaching context. Do not quote raw profile fields or JSON to the user.
            """
        ).strip()

    def _update_user_profile_from_practice(
        self,
        *,
        debate_id: str,
        human_side: str,
        judge_summary: str,
        trainer_report: str,
    ) -> dict[str, Any]:
        profile = self.db.get_user_debate_profile()
        winner = self._detect_winner(judge_summary)
        wins = profile.get("wins") if isinstance(profile.get("wins"), dict) else {}
        side_history = profile.get("side_history") if isinstance(profile.get("side_history"), dict) else {}
        winner_key = winner if winner in {"pro", "con"} else "unclear"
        side_key = human_side if human_side in {"pro", "con"} else "auto"
        strengths = list(profile.get("strengths") or [])
        weaknesses = list(profile.get("weaknesses") or [])
        notes = list(profile.get("trainer_notes") or [])
        style_tags = list(profile.get("style_tags") or [])
        if winner == human_side:
            strengths.append(
                f"Won as {human_side.upper()} in practice debate {debate_id[:8]} based on the Judge verdict."
            )
        elif winner in {"pro", "con"}:
            weaknesses.append(
                f"Lost as {human_side.upper()} in practice debate {debate_id[:8]}; review why the Judge preferred {winner.upper()}."
            )
        else:
            weaknesses.append(
                f"Practice debate {debate_id[:8]} ended unclear; work on making the winning path easier for the Judge to identify."
            )
        if trainer_report.strip():
            notes.append(f"{debate_id[:8]}: {self._clip_for_prompt(trainer_report, 420)}")
        style_tags.append("practice_debate")
        return self.db.update_user_debate_profile(
            {
                "debates_completed": int(profile.get("debates_completed", 0) or 0),
                "practice_debates_completed": int(profile.get("practice_debates_completed", 0) or 0) + 1,
                "wins": {**wins, winner_key: int(wins.get(winner_key, 0) or 0) + 1},
                "side_history": {
                    **side_history,
                    side_key: int(side_history.get(side_key, 0) or 0) + 1,
                },
                "strengths": strengths[-18:],
                "weaknesses": weaknesses[-18:],
                "trainer_notes": notes[-30:],
                "style_tags": sorted(set(style_tags))[-12:],
            }
        )

    def _chat_messages(
        self,
        session_id: str,
        user_message: str,
        session_settings: dict[str, Any],
        generation_settings: dict[str, Any],
        model: SupportedModel,
    ) -> list[dict[str, str]]:
        history = self._chat_history_for_model(
            self.db.list_messages(session_id, include_hidden=True),
            model_name=model.name,
            reserve_tokens=int(generation_settings.get("max_tokens", 2048)) + 1400,
        )
        system_context = self._trim_prompt_block(self._system_context(session_id), 1000, char_cap=6000)
        profile_context = self._trim_prompt_block(
            self._practice_profile_context(session_settings),
            650,
            char_cap=3500,
        )
        formatted_history = "\n".join(
            f"{message['speaker']} ({message['role']}): {message['content']}"
            for message in history
            if message["content"] != user_message
        )
        return [
            {
                "role": "system",
                "content": dedent(
                    f"""
                    You are the Jubidate AI assistant for this chat.
                    Answer normal chat messages directly and use the chat memory below when relevant.
                    If the user asks about a past debate, explain the result from memory.
                    If the user asks about this app, its architecture, how routing/debates work, logs, terminal output, or recent errors, use the system context below.
                    Do not invent terminal output. If the diary does not contain the requested detail, say what is available and ask the user to paste the missing terminal lines.
                    Do not start a new debate unless the user clearly asks for debate, comparison, pros/cons, or multiple sides.
                    Never expose hidden reasoning, planning notes, or <think> blocks.
                    Tone: {session_settings.get("debate_tone", "Academic")}.
                    Language: {session_settings.get("language", "English")}.
                    Response length: {generation_settings.get("response_length", "Normal")}.

                    System context:
                    {system_context}
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Chat memory:
                    {formatted_history or "No previous messages yet."}

                    User debate profile:
                    {profile_context}

                    Current user message:
                    {user_message}
                    """
                ).strip(),
            },
        ]

    def _system_context(self, session_id: str | None = None) -> str:
        return dedent(
            f"""
            Application architecture facts:
            - Backend: Python 3.13, FastAPI, SQLite, WebSockets, LiteLLM model routing.
            - Frontend: Next.js, React, TypeScript, Tailwind CSS.
            - Model availability: built-in MODEL_MAP maps each supported model to one provider. API keys unlock provider model groups; model names do not go in .env.
            - Routing: each user message first passes a balanced safety lock, then an AI-first intent router decides Council Assistant chat vs multi-agent debate unless Council Assistant Always On is enabled.
            - Debate engine: two teams, Pro and Con, with 1-4 debaters per team. Roles can include Advocate, Rebuttal Critic, Evidence Researcher, and Cross-Examiner.
            - Debate flow: professional fixed phases replace the old moderator loop. One-debater mode uses constructive, cross-exam, answer/rebuttal, one Open Discussion with Pro-open and Con-open mini-rounds, closings, Judge Assistant, then Judge. Two-to-four-debater modes use two advocate-led Discussion Time phases: Pro Advocate opens the first, Con Advocate opens the second.
            - Discussion Time: only the Advocates speak as team spokespersons, but they use all teammate material from researchers, critics, and examiners. The setting named Discussion Messages Per Team caps each team at 1-4 messages.
            - Cross-examination: the speaking role gives one short setup sentence and 2-4 pointed questions, not a full rebuttal. Later answer/rebuttal phases should answer the strongest questions and then repair or attack naturally.
            - Neutral agents: optional Judge Assistant audits missed points and evidence gaps; Judge produces the final verdict.
            - Limits: max 10 chat sessions and max 3 simultaneous debates.
            - Chat settings are per-chat. Changes apply to the next AI message/turn, not a role that is already streaming.
            - Graphs and Statistics are computed from the saved debate transcript. They are not prefilled with fake role data.
            - Costs shown in the UI are estimates from tracked prompt/output text and built-in model price data, not provider invoices.
            - Runtime diary scope: backend events are captured by the FastAPI app. Frontend UI/socket events are captured only when the browser reports them through /api/runtime-diary. External terminal lines that were never captured are not visible.

            Recent runtime diary:
            {runtime_diary.format_for_prompt(limit=24, session_id=session_id)}
            """
        ).strip()

    async def _safety_lock_assessment(
        self,
        content: str,
        model: SupportedModel,
        cost_tracker: CostTracker | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        route = model.route
        if not settings.mock_llm and acompletion is not None and route is not None:
            try:
                messages = self._safety_lock_messages(content)
                _kwargs: dict = dict(
                    model=route.litellm_model,
                    messages=messages,
                    api_key=route.api_key,
                    stream=False,
                    temperature=0.0,
                    max_tokens=120,
                    timeout=min(settings.request_timeout_seconds, 30),
                )
                if route.api_base:
                    _kwargs["api_base"] = route.api_base
                response = await acompletion(**_kwargs)
                text = self._completion_text(response).strip()
                if cost_tracker is not None:
                    cost_tracker.record_call(
                        model_name=model.name,
                        input_text=message_input_text(messages),
                        output_text=text,
                        operation="safety_lock",
                    )
                parsed = self._parse_safety_response(text)
                if parsed:
                    return parsed
            except Exception as exc:
                self._maybe_disable_model_route(model, exc)
                runtime_diary.record(
                    "backend terminal",
                    "safety lock classifier fallback",
                    f"AI safety classifier failed, using local fallback: {exc}",
                    session_id=session_id,
                )
        return self._fallback_safety_assessment(content)

    def _safety_lock_messages(self, content: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": dedent(
                    """
                    You are a minimal safety lock for Jubidate AI. Your job is not to be strict.
                    Allow normal conversations, controversial topics, political debate, ethics, history, news,
                    fiction, high-level explanations, prevention, safety education, and requests that are merely uncomfortable.

                    Return ASSIST only for extreme cases where the user is requesting actionable help for serious harm or abuse,
                    such as making weapons/explosives, committing violence, encouraging self-harm, sexual exploitation of minors,
                    malware/credential theft, fraud, stalking, evading capture, or other operational wrongdoing.

                    If uncertain, choose ALLOW. Do not block just because a message contains scary words.
                    Return strict JSON only: {"action":"allow","category":"none","reason":"short reason"}
                    or {"action":"assist","category":"short category","reason":"short reason"}
                    """
                ).strip(),
            },
            {"role": "user", "content": content},
        ]

    def _parse_safety_response(self, text: str) -> dict[str, Any] | None:
        payload = self._parse_json_object(text)
        if not payload:
            return None
        raw_action = str(
            payload.get("action") or payload.get("route") or payload.get("decision") or "allow"
        ).lower()
        action = "assist" if raw_action in {"assist", "block", "blocked", "unsafe"} else "allow"
        return {
            "action": action,
            "category": str(payload.get("category") or "none"),
            "reason": str(payload.get("reason") or "No specific reason provided."),
        }

    def _fallback_safety_assessment(self, content: str) -> dict[str, Any]:
        lower = content.lower()
        extreme_patterns = (
            (r"\b(how\s+to|step\s*by\s*step|instructions|recipe|build|make|construct|assemble)\b.{0,80}\b(bomb|explosive|grenade|pipe\s*bomb)\b", "weapons/explosives"),
            (r"\b(kill\s+yourself|convince\s+someone\s+to\s+kill\s+themselves|encourage\s+suicide)\b", "self-harm encouragement"),
            (r"\b(child\s+porn|csam|sexual\s+images\s+of\s+children)\b", "child sexual exploitation"),
            (r"\b(write|create|build|give\s+me|make)\b.{0,80}\b(ransomware|malware|keylogger|credential\s+stealer)\b", "cyber abuse"),
            (r"\b(steal|phish|hack\s+into|break\s+into)\b.{0,80}\b(password|account|bank|email|wallet)\b", "credential theft"),
            (r"\b(how\s+to|step\s*by\s*step|instructions)\b.{0,80}\b(poison\s+someone|hide\s+a\s+body|evade\s+police)\b", "violent wrongdoing"),
        )
        for pattern, category in extreme_patterns:
            if re.search(pattern, lower, flags=re.DOTALL):
                return {
                    "action": "assist",
                    "category": category,
                    "reason": f"The request appears to ask for actionable help with {category}.",
                }
        return {"action": "allow", "category": "none", "reason": "No extreme unsafe request detected."}

    def _safety_lock_message(self, safety: dict[str, Any]) -> str:
        category = str(safety.get("category") or "serious harm")
        reason = str(safety.get("reason") or "the request asks for actionable unsafe help")
        return dedent(
            f"""
            I can't start a debate or generate instructions for this request because {reason}

            I can still help in safer ways, for example:
            - discuss the ethics, laws, or risks at a high level
            - explain prevention, detection, or harm-reduction steps
            - reframe it into a safe debate topic about policy, safety, or accountability

            Category: {category}
            """
        ).strip()

    async def _classify_intent(
        self,
        content: str,
        model: SupportedModel,
        session_settings: dict[str, Any],
        cost_tracker: CostTracker | None = None,
        *,
        session_id: str | None = None,
    ) -> str:
        route = model.route
        if not settings.mock_llm and acompletion is not None and route is not None:
            try:
                messages = self._intent_classifier_messages(content, session_id)
                _kwargs: dict = dict(
                    model=route.litellm_model,
                    messages=messages,
                    api_key=route.api_key,
                    stream=False,
                    temperature=0.0,
                    max_tokens=80,
                    timeout=min(settings.request_timeout_seconds, 30),
                )
                if route.api_base:
                    _kwargs["api_base"] = route.api_base
                response = await acompletion(**_kwargs)
                text = self._completion_text(response).strip()
                if cost_tracker is not None:
                    cost_tracker.record_call(
                        model_name=model.name,
                        input_text=message_input_text(messages),
                        output_text=text,
                        operation="router",
                    )
                parsed_intent = self._parse_intent_response(text)
                if parsed_intent:
                    return parsed_intent
            except Exception as exc:
                self._maybe_disable_model_route(model, exc)
                pass

        fallback = self._heuristic_intent(content)
        return "debate" if fallback == "debate" else "chat"

    def _intent_classifier_messages(
        self, content: str, session_id: str | None
    ) -> list[dict[str, str]]:
        recent_history = ""
        if session_id:
            history = self.db.list_messages(session_id, include_hidden=True)[-8:]
            recent_history = "\n".join(
                f"{message['speaker']} ({message['role']}): {self._clip_for_prompt(message['content'], 240)}"
                for message in history
            )
        return [
            {
                "role": "system",
                "content": dedent(
                    """
                    You are the intent router for Jubidate AI.
                    Decide whether this exact user message should launch a new formal multi-agent debate,
                    or whether the Council Assistant should answer it as normal chat.

                    Choose DEBATE only when the user is clearly asking the debater teams to debate now,
                    or when the message is a standalone debatable topic/proposition meant for the debate room.
                    Choose CHAT for greetings, setup questions, commands, bug reports, explanations, follow-ups,
                    personal/local advice, questions about previous debates, and messages that merely mention
                    the word "debate" without requesting a new debate.

                    Do not route by keywords. Use the user's actual intent. If uncertain, choose CHAT.
                    Return strict JSON only: {"intent":"debate","reason":"short reason"}
                    or {"intent":"chat","reason":"short reason"}
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Recent chat memory:
                    {recent_history or "No previous messages."}

                    Current user message:
                    {content}

                    Examples:
                    - "Please debate whether schools should ban phones." -> debate
                    - "Should cities ban private cars downtown?" -> debate
                    - "Why did it start a debate when I typed the word debate?" -> chat
                    - "Can you tell me whether I should use port 6001?" -> chat
                    - "Explain the judge's final result from the last debate." -> chat
                    """
                ).strip(),
            },
        ]

    def _parse_intent_response(self, text: str) -> str | None:
        payload = self._parse_json_object(text)
        raw_intent = ""
        if payload:
            raw_intent = str(
                payload.get("intent") or payload.get("mode") or payload.get("route") or ""
            )
        else:
            raw_intent = text
        normalized = re.sub(r"[^a-z]+", " ", raw_intent.lower()).strip()
        tokens = set(normalized.split())
        if "chat" in tokens:
            return "chat"
        if "debate" in tokens:
            return "debate"
        return None

    def _heuristic_intent(self, content: str) -> str:
        lower = content.lower().strip()
        direct_chat_patterns = (
            r"^(hello|hi|hey)\b",
            r"^(thanks|thank you)\b",
            r"^explain\b",
            r"^summarize\b",
            r"^what\s+did\b",
            r"^what\s+does\b",
            r"^why\b",
            r"^what\s+should\s+i\b",
            r"^what\s+command\b",
            r"^can\s+you\s+tell\s+me\b",
            r"^how\s+do\s+i\b",
            r"^how\s+do\s+we\b",
            r"\bsetup\b",
            r"\brun\s+it\b",
            r"\bstart\s+the\s+program\b",
        )
        if any(re.search(pattern, lower) for pattern in direct_chat_patterns):
            return "chat"
        explicit_debate_patterns = (
            r"^(please\s+)?debate\b",
            r"\blet\s+(them|it|the council|the debaters)\s+debate\b",
            r"\bstart\s+(a\s+)?debate\b",
            r"\brun\s+(a\s+)?debate\b",
            r"\bargue\s+both\s+sides\b",
            r"\bpro\s+and\s+con\b",
            r"\bfor\s+and\s+against\b",
            r"\bpros\s+and\s+cons\b",
        )
        if any(re.search(pattern, lower) for pattern in explicit_debate_patterns):
            return "debate"
        if self._looks_like_standalone_debate_topic(lower):
            return "debate"
        return "ambiguous"

    def _looks_like_standalone_debate_topic(self, lower: str) -> bool:
        chat_question_starts = (
            "can you",
            "could you",
            "would you",
            "what ",
            "why ",
            "how ",
            "tell me",
            "explain",
        )
        if lower.startswith(chat_question_starts):
            return False
        if len(lower.split()) > 24:
            return False
        return bool(
            re.search(r"\bshould\b", lower)
            or re.search(r"\bwhether\b", lower)
            or re.search(r"\bversus\b|\bvs\b", lower)
            or "which is better" in lower
        )

    def _context_slice(self, transcript: list[dict[str, Any]], context_window: int) -> list[dict[str, Any]]:
        return self._transcript_for_model(
            transcript,
            model_name="llama-3.1-8b",
            reserve_tokens=1800,
            hard_turn_cap=24,
            context_window=context_window,
            topic=None,
        )

    def _format_transcript(self, transcript: list[dict[str, Any]]) -> str:
        if not transcript:
            return "No prior turns yet."
        lines = []
        for turn in transcript:
            phase_title = str(turn.get("phase_title") or "").strip()
            phase_prefix = f"[{phase_title}] " if phase_title else ""
            lines.append(
                f"{phase_prefix}{turn['speaker']} ({turn['model']}): {turn['content']}"
            )
        return "\n\n".join(lines)

    def _extract_delta(self, chunk: Any) -> str:
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            if not choices:
                return ""
            delta = choices[0].get("delta") or {}
            if isinstance(delta, dict):
                return delta.get("content") or ""
            return getattr(delta, "content", "") or ""

        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if isinstance(delta, dict):
            return delta.get("content") or ""
        return getattr(delta, "content", "") or ""

    def _extract_finish_reason(self, chunk: Any) -> str | None:
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            if not choices:
                return None
            reason = choices[0].get("finish_reason")
            return str(reason) if reason else None

        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return None
        reason = getattr(choices[0], "finish_reason", None)
        return str(reason) if reason else None

    def _completion_text(self, response: Any) -> str:
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if not choices:
                return ""
            message = choices[0].get("message") or {}
            if isinstance(message, dict):
                return message.get("content") or ""
            return getattr(message, "content", "") or ""
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if isinstance(message, dict):
            return message.get("content") or ""
        return getattr(message, "content", "") or ""


class StreamingSanitizer:
    def __init__(self) -> None:
        self.in_think = False
        self.pending = ""

    def push(self, delta: str) -> str:
        text = self.pending + delta
        self.pending = ""
        output: list[str] = []

        while text:
            lower = text.lower()
            if self.in_think:
                end_index = lower.find("</think>")
                if end_index == -1:
                    return ""
                text = text[end_index + len("</think>") :]
                self.in_think = False
                continue

            start_index = lower.find("<think>")
            if start_index == -1:
                keep = max(len("<think>") - 1, len("</think>") - 1)
                if len(text) > keep:
                    output.append(text[:-keep])
                    self.pending = text[-keep:]
                else:
                    self.pending = text
                break

            output.append(text[:start_index])
            text = text[start_index + len("<think>") :]
            self.in_think = True

        return sanitize_model_text("".join(output), remove_partial_meta=False, strip_edges=False)

    def flush(self) -> str:
        if self.in_think:
            self.pending = ""
            return ""
        tail = self.pending
        self.pending = ""
        return sanitize_model_text(tail, remove_partial_meta=False, strip_edges=False)


def sanitize_model_text(
    text: str, *, remove_partial_meta: bool = True, strip_edges: bool = True
) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    if remove_partial_meta:
        cleaned = re.sub(
            r"(?im)^\s*(i see|i understand|the user wants|the user asks|let me|i need to|we need to).*?(?:\n|$)",
            "",
            cleaned,
        )
    return cleaned.strip() if strip_edges else cleaned
