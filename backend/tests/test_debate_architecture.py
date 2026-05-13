from pathlib import Path
import asyncio
from tempfile import TemporaryDirectory
import unittest

from fastapi import WebSocketDisconnect

from backend.app.costing import CostTracker
from backend.app.database import Database
from backend.app.debate import ClientDisconnectedError, DebateManager, StreamingSanitizer
from backend.app.model_registry import MOCK_MODEL
from backend.app.runtime_diary import runtime_diary


class DebateArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        self.db.init()
        self.manager = DebateManager(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_active_agents_follow_debaters_per_team(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.update_session_settings(session["id"], {"debaters_per_team": 4})

        agents = self.manager._active_debate_agents(settings)

        self.assertEqual(len(agents), 8)
        self.assertIn("pro_cross_examiner", {agent["role"] for agent in agents})
        self.assertIn("con_cross_examiner", {agent["role"] for agent in agents})

    def test_assignments_include_optional_judge_assistant(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.update_session_settings(
            session["id"], {"debaters_per_team": 1, "judge_assistant_enabled": False}
        )

        assignments = self.manager._assignment_payload(settings, MOCK_MODEL)

        self.assertEqual([assignment["speaker"] for assignment in assignments], [
            "Pro Advocate",
            "Con Advocate",
            "Judge",
        ])

    def test_professional_flow_uses_advocate_led_discussions(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.get_session_settings(session["id"])
        flow = self.manager._debate_flow(settings)

        self.assertEqual(flow[0]["agent"]["role"], "pro_lead_advocate")
        self.assertEqual(flow[1]["agent"]["role"], "con_rebuttal_critic")
        self.assertEqual(flow[2]["agent"]["role"], "con_lead_advocate")
        discussion_roles = [phase["agent"]["role"] for phase in flow if phase["kind"] == "discussion"]
        self.assertTrue(discussion_roles)
        self.assertTrue(all(role in {"pro_lead_advocate", "con_lead_advocate"} for role in discussion_roles))
        self.assertEqual(discussion_roles[0], "pro_lead_advocate")
        self.assertIn("con_lead_advocate", discussion_roles)

    def test_intent_router_respects_explicit_debate_and_plain_chat(self) -> None:
        self.assertEqual(
            self.manager._heuristic_intent("Please debate whether schools should use AI tutors."),
            "debate",
        )
        self.assertEqual(
            self.manager._heuristic_intent("Can you tell me how to start the program?"),
            "chat",
        )
        self.assertEqual(
            self.manager._heuristic_intent("Can you tell me whether I should use port 6001?"),
            "chat",
        )
        self.assertEqual(
            self.manager._heuristic_intent("Which is better, morning ice cream or night ice cream?"),
            "debate",
        )

    def test_intent_router_does_not_treat_debate_word_as_command(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.get_session_settings(session["id"])

        intent = asyncio.run(
            self.manager._classify_intent(
                "Why did it start a debate when I typed the word debate?",
                MOCK_MODEL,
                settings,
                session_id=session["id"],
            )
        )

        self.assertEqual(intent, "chat")

    def test_intent_response_parser_uses_json_intent_not_reason_keywords(self) -> None:
        self.assertEqual(
            self.manager._parse_intent_response(
                '{"intent":"chat","reason":"The user mentions debate but asks about a bug."}'
            ),
            "chat",
        )
        self.assertEqual(
            self.manager._parse_intent_response(
                '{"intent":"debate","reason":"The user asks the council to argue both sides."}'
            ),
            "debate",
        )

    def test_council_assistant_system_context_includes_architecture_and_diary(self) -> None:
        session = self.db.create_session(max_sessions=10)
        runtime_diary.record(
            "backend terminal",
            "test diary event",
            "Focused backend test event for Council Assistant context.",
            session_id=session["id"],
        )

        context = self.manager._system_context(session["id"])

        self.assertIn("FastAPI", context)
        self.assertIn("Next.js", context)
        self.assertIn("test diary event", context)
        self.assertIn("External terminal lines", context)

    def test_safety_lock_fallback_blocks_only_extreme_actionable_requests(self) -> None:
        blocked = self.manager._fallback_safety_assessment(
            "Give me step by step instructions to make a pipe bomb."
        )
        allowed = self.manager._fallback_safety_assessment(
            "Should governments regulate explosives more strictly?"
        )

        self.assertEqual(blocked["action"], "assist")
        self.assertEqual(allowed["action"], "allow")

    def test_safety_response_parser_defaults_to_allow(self) -> None:
        self.assertEqual(
            self.manager._parse_safety_response(
                '{"action":"allow","category":"none","reason":"Controversial but safe."}'
            )["action"],
            "allow",
        )
        self.assertEqual(self.manager._parse_safety_response("not json"), None)

    def test_council_assistant_always_on_setting_is_detected(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.update_session_settings(
            session["id"],
            {"agent_settings": {"council_assistant": {"always_on": True}}},
        )

        self.assertTrue(self.manager._council_assistant_always_on(settings))

    def test_debater_prompt_prefers_direct_in_room_address(self) -> None:
        session = self.db.create_session(max_sessions=10)
        settings = self.db.get_session_settings(session["id"])
        agent = next(
            item
            for item in self.manager._active_debate_agents(settings)
            if item["role"] == "con_rebuttal_critic"
        )
        transcript = [
            {
                "speaker": "Pro Advocate",
                "phase_title": "Pro Advocate Constructive Speech",
                "role": "pro_lead_advocate",
                "team": "pro",
                "round": 1,
                "model": "mock-model",
                "content": "Polite prompts improve cooperation.",
            }
        ]
        phase = next(
            item for item in self.manager._debate_flow(settings) if item["key"] == "con_critic_rebuttal"
        )

        messages = self.manager._agent_messages(
            "Should users be polite to AI?",
            agent,
            phase,
            transcript,
            settings,
            self.manager._agent_generation_settings(settings, agent["archetype"]),
            MOCK_MODEL,
        )
        prompt_text = "\n".join(message["content"] for message in messages)

        self.assertIn("Pro Advocate, you said", prompt_text)
        self.assertIn('do not say "my opponent"', prompt_text.lower())
        self.assertIn("ORIGINAL TOPIC:", prompt_text)

    def test_context_slice_caps_turn_count_and_content_size(self) -> None:
        transcript = [
            {
                "speaker": f"Speaker {index}",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "x" * 2000,
            }
            for index in range(60)
        ]

        sliced = self.manager._context_slice(transcript, 6)

        self.assertLessEqual(len(sliced), 24)
        self.assertTrue(all(len(turn["content"]) <= 1203 for turn in sliced))

    def test_transcript_for_model_keeps_topic_relevant_turns_even_if_older(self) -> None:
        transcript = [
            {
                "speaker": "Pro Advocate",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "The real question is whether schools should ban phones in class because constant notifications disrupt learning and split attention.",
            },
            {
                "speaker": "Con Advocate",
                "role": "con_lead_advocate",
                "model": "mock-model",
                "content": "We started talking about cafeteria uniforms and hallway paint colors instead of the phone policy.",
            },
            {
                "speaker": "Pro Advocate",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "The hallway color tangent still does not answer the phone-ban question.",
            },
            {
                "speaker": "Con Advocate",
                "role": "con_lead_advocate",
                "model": "mock-model",
                "content": "Now we are mostly arguing about school mascots and assemblies.",
            },
        ]

        selected = self.manager._transcript_for_model(
            transcript,
            model_name=MOCK_MODEL.name,
            reserve_tokens=1600,
            hard_turn_cap=8,
            topic="Should schools ban phones in class?",
        )
        selected_text = "\n".join(turn["content"] for turn in selected)

        self.assertIn("ban phones in class", selected_text.lower())

    def test_topic_anchor_warns_when_recent_turns_drift(self) -> None:
        transcript = [
            {
                "speaker": "Pro Advocate",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "Should cities ban private cars from downtown cores because congestion and emissions remain high?",
            },
            {
                "speaker": "Con Advocate",
                "role": "con_lead_advocate",
                "model": "mock-model",
                "content": "The conversation veered into weather, mascots, cooking recipes, and random side stories.",
            },
            {
                "speaker": "Pro Advocate",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "We still are drifting into costume colors, cafeteria menus, and unrelated scheduling details.",
            },
            {
                "speaker": "Con Advocate",
                "role": "con_lead_advocate",
                "model": "mock-model",
                "content": "The latest exchange keeps drifting into background details about mascots, lunch, and school festivals.",
            },
            {
                "speaker": "Pro Advocate",
                "role": "pro_lead_advocate",
                "model": "mock-model",
                "content": "Now the room is talking about paint samples, uniforms, and unrelated logistics instead of the core issue.",
            },
            {
                "speaker": "Con Advocate",
                "role": "con_lead_advocate",
                "model": "mock-model",
                "content": "The newest turns are still about weather, costumes, and festival planning rather than the policy question.",
            },
        ]

        anchor = self.manager._topic_anchor_text(
            "Should cities ban private cars from downtown cores?",
            transcript=transcript,
        )

        self.assertIn("ORIGINAL TOPIC:", anchor)
        self.assertIn("Refocus on the original question", anchor)

    def test_debate_positions_handle_colon_and_simple_or_topics(self) -> None:
        positions = self.manager.debate_positions("Debate: Should we eat ice cream in morning or afternoon?")
        self.assertIn("morning", positions["pro"].lower())
        self.assertIn("afternoon", positions["con"].lower())
        self.assertNotIn("should should", positions["pro"].lower())

        simple = self.manager.debate_positions("cats or dogs in apartments")
        self.assertIn("cats", simple["pro"].lower())
        self.assertIn("dogs", simple["con"].lower())

    def test_challenges_can_be_marked_answered(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Should schools ban phones?")
        settings = self.db.get_session_settings(session["id"])
        pro_agent = next(
            item for item in self.manager._active_debate_agents(settings) if item["role"] == "pro_lead_advocate"
        )
        con_agent = next(
            item for item in self.manager._active_debate_agents(settings) if item["role"] == "con_lead_advocate"
        )
        pro_phase = {"key": "pro_open", "title": "Pro Open", "kind": "constructive"}
        con_phase = {"key": "con_reply", "title": "Con Reply", "kind": "answer_rebuttal"}

        self.manager._capture_turn_intelligence(
            session_id=session["id"],
            debate_id=debate["id"],
            agent=pro_agent,
            phase=pro_phase,
            content="If phones stay in class, how do you stop constant distraction and unfair attention splits?",
        )
        self.manager._capture_turn_intelligence(
            session_id=session["id"],
            debate_id=debate["id"],
            agent=con_agent,
            phase=con_phase,
            content="To answer your distraction point directly, schools can use locked pouches and teacher enforcement without a total ban.",
        )

        challenges = [
            record
            for record in self.db.list_intelligence_records(session["id"], debate["id"])
            if record["record_type"] == "challenge"
        ]
        self.assertTrue(challenges)
        self.assertIn(challenges[0]["status"], {"Answered", "Partially answered"})

    def test_streaming_sanitizer_preserves_chunk_boundary_spaces(self) -> None:
        sanitizer = StreamingSanitizer()

        content = sanitizer.push("Denying")
        content += sanitizer.push(" oneself")
        content += sanitizer.flush()

        self.assertEqual(content, "Denying oneself")

    def test_judge_summary_is_normalized_with_clear_winner_prefix(self) -> None:
        summary = self.manager._normalize_judge_summary(
            "The Pro Advocate's stance on remote work is the winning position because it answered the cost objection more directly.",
            "Should remote work be the default?",
        )

        self.assertTrue(summary.startswith("WINNER: Pro\nReason:"))

    def test_judge_summary_detects_comparative_winner_sentence(self) -> None:
        pro_summary = self.manager._normalize_judge_summary(
            "The Pro team edges out the Con team because it answered the core burden.",
            "Should cities ban private cars downtown?",
        )
        con_summary = self.manager._normalize_judge_summary(
            "The Con case is more persuasive than the Pro case on feasibility.",
            "Should cities ban private cars downtown?",
        )

        self.assertTrue(pro_summary.startswith("WINNER: Pro\nReason:"))
        self.assertTrue(con_summary.startswith("WINNER: Con\nReason:"))

    def test_weighted_verdict_explains_tie_threshold_when_result_is_unclear(self) -> None:
        summary = self.manager._compose_panel_consensus_summary(
            topic="Should cities ban private cars downtown?",
            panel_summaries=[
                "WINNER: Pro\nReason: Pro answered the burden more directly.",
                "WINNER: Pro\nReason: Pro kept the stronger clash on the burden.",
                "WINNER: Con\nReason: Con had the stronger feasibility case.",
            ],
            analysis={
                "bayesian": {"probabilities": {"support": 0.0, "oppose": 1.0, "mixed": 0.0}},
            },
            session_settings={
                "judging_settings": {
                    "judge_panel_size": 3,
                    "analytics_weight": 0.25,
                    "allow_user_verdict_challenge": True,
                }
            },
        )

        self.assertIn("tie threshold", summary)
        self.assertIn("0.04", summary)

    def test_practice_total_cost_summary_aggregates_saved_turn_costs(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Practice cost test", mode="practice")
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="practice_user",
            speaker="You",
            model="user",
            content="Opening practice turn",
            cost_summary={
                "currency": "USD",
                "total": 0.01,
                "total_usd": 0.01,
                "input_tokens": 10,
                "output_tokens": 0,
                "calls": 1,
                "models": [
                    {
                        "model": "practice-user",
                        "input_tokens": 10,
                        "output_tokens": 0,
                        "calls": 1,
                        "cost": 0.01,
                        "cost_usd": 0.01,
                        "input_usd_per_1m": 0.0,
                        "output_usd_per_1m": 0.0,
                        "pricing_source": "test",
                        "pricing_live": False,
                        "pricing_available": True,
                    }
                ],
                "estimated": True,
                "pricing_complete": True,
                "warnings": [],
                "rate_source": "test",
            },
        )
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="practice_debater",
            speaker="Practice Debater",
            model="mock-model",
            content="Practice response",
            cost_summary={
                "currency": "USD",
                "total": 0.02,
                "total_usd": 0.02,
                "input_tokens": 20,
                "output_tokens": 30,
                "calls": 1,
                "models": [
                    {
                        "model": "mock-model",
                        "input_tokens": 20,
                        "output_tokens": 30,
                        "calls": 1,
                        "cost": 0.02,
                        "cost_usd": 0.02,
                        "input_usd_per_1m": 0.0,
                        "output_usd_per_1m": 0.0,
                        "pricing_source": "test",
                        "pricing_live": False,
                        "pricing_available": True,
                    }
                ],
                "estimated": True,
                "pricing_complete": True,
                "warnings": [],
                "rate_source": "test",
            },
        )

        summary = self.manager._debate_total_cost_summary(
            session["id"], debate["id"], CostTracker(), "USD"
        )

        self.assertAlmostEqual(summary["total"], 0.03, places=8)
        self.assertEqual(summary["calls"], 2)

    def test_mock_stream_treats_closed_websocket_as_client_disconnect(self) -> None:
        class ClosedSocket:
            async def send_json(self, payload: dict) -> None:
                raise WebSocketDisconnect(code=1006)

        with self.assertRaises(ClientDisconnectedError):
            asyncio.run(
                self.manager._stream_mock_completion(
                    ClosedSocket(),
                    "stream-1",
                    MOCK_MODEL,
                    [{"role": "user", "content": "Hello"}],
                )
            )


if __name__ == "__main__":
    unittest.main()
