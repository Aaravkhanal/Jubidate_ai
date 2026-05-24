from contextlib import asynccontextmanager
import asyncio
import logging
import os
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.analytics import analyze_debate, session_chart_data
from app.config import settings
from app.database import Database
from app.debate import ClientDisconnectedError, DebateError, DebateManager
from app.model_registry import (
    DEFAULT_FALLBACK_ORDER,
    PROVIDER_ORDER,
    SUPPORTED_MODELS,
    available_models,
    get_background_verification_results,
    is_background_verification_completed,
    provider_status,
    run_background_verification,
    verify_models_runtime,
)
from app.runtime_diary import runtime_diary
from app.schemas import (
    ChatSession,
    CouncilSettingsUpdate,
    CreateSessionRequest,
    DebateMessage,
    DebateRecord,
    FeedbackRequest,
    RenameDebateRequest,
    RenameSessionRequest,
    ResetAgentExperienceRequest,
    ResetUserDebateProfileRequest,
    SessionSettingsUpdate,
    VerdictReviewRequest,
    RESTDebateCreateRequest,
    RESTDebateStartRequest,
    RESTDebateNextTurnRequest,
    SessionModelsUpdateRequest,
)

logger = logging.getLogger("jubidate.main")


db = Database(settings.database_path)
debate_manager = DebateManager(db)


async def safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError as exc:
        if "Cannot call \"send\" once a close message has been sent" in str(exc):
            return False
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    # Log startup diagnostics
    configured = available_models()
    nvidia_key = bool(os.getenv("NVIDIA_API_KEY", "").strip())
    logger.info(
        "%s backend starting. DB: %s | NVIDIA key: %s | Configured models: %d",
        settings.app_name, settings.database_path, nvidia_key, len(configured),
    )
    runtime_diary.record(
        "backend terminal",
        "startup",
        f"{settings.app_name} backend started. Database path: {settings.database_path}. "
        f"NVIDIA key: {'detected' if nvidia_key else 'MISSING'}. "
        f"Configured models: {len(configured)}.",
    )
    # Kick off background model verification (non-blocking)
    asyncio.create_task(run_background_verification())
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

@app.get("/")
def root():
    configured = available_models()
    return {
        "app": settings.app_name,
        "status": "running",
        "configured_models": len(configured),
        "verification_completed": is_background_verification_completed(),
        "endpoints": [
            "GET /health",
            "GET /api/models",
            "GET /api/providers/status",
            "GET /api/sessions",
            "GET /api/council-settings",
        ],
    }


@app.get("/debug-env")
def debug_env():
    return {
        "NVIDIA_API_KEY": bool(os.getenv("NVIDIA_API_KEY")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "database": str(settings.database_path),
        "active_debates": debate_manager.active_count,
    }


@app.get("/api/models")
async def models() -> dict:
    configured = available_models()
    bg_results = get_background_verification_results()
    bg_done = is_background_verification_completed()

    # If background verification has completed, use those results
    # If not, return all configured models optimistically (API key exists = usable)
    if bg_done and bg_results:
        # Use verified results
        unlocked_models = []
        for model in configured:
            availability = bg_results.get(model.name)
            if availability and availability.available:
                payload = model.public_dict(configured=True)
                if availability.reason:
                    payload["availability_reason"] = availability.reason
                unlocked_models.append(payload)
        # If ALL probes failed but key exists, still return models optimistically
        # (probes can fail due to rate limits, temporary issues, etc.)
        if not unlocked_models and configured:
            logger.warning(
                "All %d model probes failed but API key exists — returning models optimistically",
                len(configured),
            )
            unlocked_models = [model.public_dict(configured=True) for model in configured]
    elif configured:
        # Background verification not done yet — return optimistically
        unlocked_models = [model.public_dict(configured=True) for model in configured]
    else:
        unlocked_models = []

    include_mock = settings.mock_llm and not unlocked_models
    if include_mock:
        unlocked_models.insert(
            0,
            {
                "name": "mock-debate-model",
                "provider": "mock",
                "provider_label": "Mock",
                "api_key_env": "MOCK_LLM_RESPONSES",
                "litellm_model": "mock-debate-model",
                "configured": True,
                "availability_reason": None,
            },
        )

    providers = []
    for provider in PROVIDER_ORDER:
        provider_models = [model for model in SUPPORTED_MODELS if model.provider == provider]
        if not provider_models:
            continue
        # Use configured models (key exists) as the available set
        runtime_models = [model for model in provider_models if model.runtime_available]
        direct_configured = any(model.direct_api_key for model in provider_models)
        if not runtime_models and not direct_configured:
            continue

        status_label = f"{len(runtime_models)} available"
        status_reason = None
        if bg_done and bg_results:
            verified_count = sum(
                1 for m in provider_models
                if bg_results.get(m.name) and bg_results[m.name].available
            )
            status_label = f"{verified_count} verified" if verified_count else f"{len(runtime_models)} configured"
        elif not bg_done:
            status_label = f"{len(runtime_models)} configured (verifying...)"

        providers.append(
            {
                "provider": provider,
                "provider_label": provider_models[0].provider_label,
                "api_key_env": provider_models[0].api_key_env,
                "configured": True,
                "unlocked_model_count": len(runtime_models),
                "total_model_count": len(provider_models),
                "models": [model.public_dict(configured=True) for model in runtime_models],
                "status_label": status_label,
                "status_reason": status_reason,
            }
        )

    availability_notice = None
    if not unlocked_models and not include_mock:
        if configured:
            availability_notice = "Models are configured but verification is still running. Try again in a few seconds."
        else:
            availability_notice = "No working API keys are available yet."

    return {
        "models": unlocked_models,
        "providers": providers,
        "available_model_count": len(unlocked_models),
        "real_available_model_count": len(configured),
        "minimum_debate_models": 1,
        "selection_required": True,
        "mock_mode": settings.mock_llm,
        "availability_notice": availability_notice,
        "verification_completed": bg_done,
    }


@app.get("/api/providers/status")
def providers_status() -> dict:
    return provider_status()


@app.get("/api/council-settings")
def get_council_settings() -> dict:
    return db.get_council_settings()


@app.patch("/api/council-settings")
def update_council_settings(payload: CouncilSettingsUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    return db.update_council_settings(updates)


@app.post("/api/council-settings/reset-agent-experience")
def reset_universal_agent_experience(payload: ResetAgentExperienceRequest) -> dict:
    phrase = payload.confirmation.strip()
    if phrase != "RESET COUNCIL IDENTITIES":
        raise HTTPException(
            status_code=422,
            detail='Type RESET COUNCIL IDENTITIES to reset universal agent identities.',
        )
    deleted = db.reset_agent_experience(scope="universal")
    return {"deleted": deleted}


@app.get("/api/user-debate-profile")
def get_user_debate_profile() -> dict:
    return db.get_user_debate_profile()


@app.get("/api/user-debate-profile/overview")
def get_user_debate_profile_overview() -> dict:
    profile = db.get_user_debate_profile()
    sessions = {session["id"]: session for session in db.list_sessions()}
    recent_debates = []
    for debate in db.list_recent_debates_global(modes=("practice",), limit=18):
        session = sessions.get(debate["session_id"]) or {}
        metadata = debate.get("metadata") if isinstance(debate.get("metadata"), dict) else {}
        recent_debates.append(
            {
                "id": debate["id"],
                "session_id": debate["session_id"],
                "session_name": session.get("name") or "Unknown Session",
                "name": debate["name"],
                "topic": debate["topic"],
                "status": debate["status"],
                "winner": debate_manager._detect_winner(debate.get("judge_summary") or ""),
                "human_side": str(metadata.get("human_side") or "").lower() or "auto",
                "practice_flow": metadata.get("practice_flow") or "Free",
                "structured_rounds": int(metadata.get("structured_rounds") or 0),
                "started_at": debate["started_at"],
                "finished_at": debate.get("finished_at"),
            }
        )
    practice_total = int(profile.get("practice_debates_completed", 0) or 0)
    decided_total = sum(int((profile.get("wins") or {}).get(side, 0) or 0) for side in ("pro", "con"))
    less_practiced_side = "con"
    side_history = profile.get("side_history") if isinstance(profile.get("side_history"), dict) else {}
    if int(side_history.get("con", 0) or 0) > int(side_history.get("pro", 0) or 0):
        less_practiced_side = "pro"
    recommendations = []
    if practice_total == 0:
        recommendations.append("Start with one AI vs Human training chat and finish a full debate so the coach has real data.")
    if profile.get("weaknesses"):
        recommendations.append(f"Primary improvement target: {profile['weaknesses'][-1]}")
    if profile.get("strengths"):
        recommendations.append(f"Protect this strength while training harder: {profile['strengths'][-1]}")
    if practice_total > 0:
        recommendations.append(f"Practice the {less_practiced_side.upper()} side next to keep your side history balanced.")
    if not recommendations:
        recommendations.append("No reliable training recommendation yet. Finish one practice debate first.")
    trainer_notes = profile.get("trainer_notes") or ["No trainer notes yet."]
    coach_summary = (
        f"Practice debates completed: {practice_total}. "
        f"Decided wins: {decided_total}. "
        f"Most recent coaching note: {trainer_notes[-1]}"
    )
    return {
        "profile": profile,
        "recent_practice_debates": recent_debates,
        "recommendations": recommendations[:5],
        "coach_summary": coach_summary,
        "less_practiced_side": less_practiced_side,
    }


@app.post("/api/user-debate-profile/reset")
def reset_user_debate_profile(payload: ResetUserDebateProfileRequest) -> dict:
    phrase = payload.confirmation.strip()
    if phrase != "RESET USER DEBATE PROFILE":
        raise HTTPException(
            status_code=422,
            detail='Type RESET USER DEBATE PROFILE to reset the user debate profile.',
        )
    return db.reset_user_debate_profile()


@app.post("/api/runtime-diary")
def record_runtime_diary(payload: dict) -> dict:
    source = str(payload.get("source") or "frontend/browser")
    event = str(payload.get("event") or "event")
    detail = str(payload.get("detail") or "")
    session_id = str(payload.get("session_id") or "").strip() or None
    runtime_diary.record(source, event, detail, session_id=session_id)
    return {"ok": True}


@app.get("/api/ai-debater-experiences")
def get_ai_debater_experiences() -> dict:
    experiences = db.list_global_agent_experience(limit=400)
    memory_events = db.list_global_intelligence_records(
        record_types=("memory_saved", "post_debate_review", "judge_scorecard"),
        limit=40,
    )
    by_agent: dict[str, dict] = {}
    by_scope = {"universal": 0, "chat": 0}
    by_lesson_type: dict[str, int] = {}
    high_confidence = 0
    total_uses = 0
    last_recorded_at = ""
    for item in experiences:
        scope = "chat" if item.get("scope") == "chat" else "universal"
        by_scope[scope] += 1
        lesson_type = str(item.get("lesson_type") or "unknown")
        by_lesson_type[lesson_type] = by_lesson_type.get(lesson_type, 0) + 1
        if item.get("confidence") == "high":
            high_confidence += 1
        total_uses += int(item.get("use_count", 0) or 0)
        created_at = str(item.get("created_at") or "")
        if created_at > last_recorded_at:
            last_recorded_at = created_at
        agent_id = str(item.get("agent_id") or "council")
        summary = by_agent.setdefault(
            agent_id,
            {
                "agent_id": agent_id,
                "record_count": 0,
                "use_count": 0,
                "high_confidence_count": 0,
                "lesson_types": {},
                "last_recorded_at": "",
            },
        )
        summary["record_count"] += 1
        summary["use_count"] += int(item.get("use_count", 0) or 0)
        if item.get("confidence") == "high":
            summary["high_confidence_count"] += 1
        summary["lesson_types"][lesson_type] = summary["lesson_types"].get(lesson_type, 0) + 1
        if created_at > summary["last_recorded_at"]:
            summary["last_recorded_at"] = created_at
    by_agent_rows = sorted(
        by_agent.values(),
        key=lambda row: (-int(row["record_count"]), -int(row["use_count"]), row["agent_id"]),
    )
    return {
        "experiences": experiences,
        "memory_events": memory_events,
        "summary": {
            "total_records": len(experiences),
            "distinct_agents": len(by_agent_rows),
            "universal_records": by_scope["universal"],
            "chat_records": by_scope["chat"],
            "high_confidence_records": high_confidence,
            "total_uses": total_uses,
            "last_recorded_at": last_recorded_at,
        },
        "by_agent": by_agent_rows,
        "by_scope": by_scope,
        "by_lesson_type": by_lesson_type,
    }


@app.get("/api/sessions", response_model=list[ChatSession])
def list_sessions() -> list[dict]:
    return db.list_sessions()


@app.post("/api/sessions", response_model=ChatSession, status_code=201)
def create_session(payload: CreateSessionRequest | None = None) -> dict:
    try:
        body = payload or CreateSessionRequest()
        return db.create_session(
            settings.max_sessions,
            mode=body.mode,
            settings_updates=body.settings or None,
        )
    except ValueError as exc:
        if str(exc) == "SESSION_LIMIT":
            raise HTTPException(
                status_code=409,
                detail=f"Only {settings.max_sessions} chat sessions are allowed at a time.",
            ) from exc
        raise


@app.delete("/api/sessions")
def delete_all_sessions() -> dict:
    deleted = db.delete_all_sessions()
    return {"deleted": deleted}


@app.patch("/api/sessions/{session_id}", response_model=ChatSession)
def rename_session(session_id: str, payload: RenameSessionRequest) -> dict:
    try:
        session = db.rename_session(session_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    if not db.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")


@app.post("/api/sessions/{session_id}/clear-history", status_code=204)
def clear_session_history(session_id: str) -> None:
    if not db.clear_visible_history(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")


@app.post("/api/sessions/{session_id}/clear-memory", status_code=204)
def clear_session_memory(session_id: str) -> None:
    if not db.clear_memory(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")


@app.get("/api/sessions/{session_id}/messages", response_model=list[DebateMessage])
def list_messages(session_id: str) -> list[dict]:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return db.list_messages(session_id)


@app.get("/api/sessions/{session_id}/debates", response_model=list[DebateRecord])
def list_debates(session_id: str) -> list[dict]:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return db.list_debates(session_id)


@app.patch("/api/sessions/{session_id}/debates/{debate_id}", response_model=DebateRecord)
def rename_debate(session_id: str, debate_id: str, payload: RenameDebateRequest) -> dict:
    try:
        debate = db.rename_debate(session_id, debate_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found.")
    return debate


@app.delete("/api/sessions/{session_id}/debates/{debate_id}", status_code=204)
def delete_debate_statistics(session_id: str, debate_id: str) -> None:
    if not db.hide_debate_statistics(session_id, debate_id):
        raise HTTPException(status_code=404, detail="Debate not found.")


@app.get("/api/sessions/{session_id}/settings")
def get_settings(session_id: str) -> dict:
    session_settings = db.get_session_settings(session_id)
    if not session_settings:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session_settings


@app.get("/api/sessions/{session_id}/practice-state")
def get_practice_state(session_id: str) -> dict:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return debate_manager.practice_state(session_id)


@app.patch("/api/sessions/{session_id}/settings")
def update_settings(session_id: str, payload: SessionSettingsUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    session_settings = db.update_session_settings(session_id, updates)
    if not session_settings:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session_settings


@app.patch("/api/sessions/{session_id}/models", response_model=ChatSession)
def update_session_models(session_id: str, payload: SessionModelsUpdateRequest) -> dict:
    session = db.update_session_models(
        session_id,
        ai_a_model=payload.ai_a_model,
        ai_b_model=payload.ai_b_model,
        judge_model=payload.judge_model,
        rounds=payload.rounds,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.get("/api/sessions/{session_id}/analytics")
def session_analytics(
    session_id: str, debate_id: str | None = Query(default=None, alias="debate_id")
) -> dict:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    debates = db.list_debates(session_id)
    if not debates:
        return analyze_debate("", [])

    all_messages = db.list_messages(session_id)
    latest_debate = None
    debater_source: list[dict] = []
    ignored_roles = {"user", "assistant", "judge", "judge_assistant"}

    candidate_debates = debates
    if debate_id:
        selected_debate = db.get_debate(session_id, debate_id)
        if not selected_debate:
            raise HTTPException(status_code=404, detail="Debate not found.")
        candidate_debates = [selected_debate]

    for debate in candidate_debates:
        debate_messages = [
            message for message in all_messages if message["debate_id"] == debate["id"]
        ]
        debate_debaters = [
            message for message in debate_messages if message["role"] not in ignored_roles
        ]
        if debate_debaters:
            latest_debate = debate
            debater_source = debate_debaters
            break

    if latest_debate is None:
        analysis = analyze_debate("", [])
        analysis["source"] = {
            "mode": "selected_debate" if debate_id else "latest_debate",
            "debate_id": candidate_debates[0]["id"] if candidate_debates else "",
            "name": candidate_debates[0]["name"] if candidate_debates else "",
            "default_index": candidate_debates[0]["default_index"] if candidate_debates else 0,
            "topic": candidate_debates[0]["topic"] if candidate_debates else "",
            "debate_count": len(debates),
        }
        return analysis

    active_role_count = len({message["role"] for message in debater_source}) or 1
    debater_messages = [
        {
            "speaker": message["speaker"],
            "role": message["role"],
            "round": message.get("phase_index") or (index // active_role_count) + 1,
            "model": message["model"],
            "content": message["content"],
            "phase_key": message.get("phase_key"),
            "phase_title": message.get("phase_title"),
            "phase_index": message.get("phase_index"),
            "phase_total": message.get("phase_total"),
            "phase_kind": message.get("phase_kind"),
        }
        for index, message in enumerate(debater_source)
    ]
    topic = str(latest_debate.get("topic") or "")
    analysis = analyze_debate(topic, debater_messages)
    analysis = debate_manager.phase_metadata_from_messages(analysis, debater_source, topic)
    analysis["session_charts"] = session_chart_data(
        debates, all_messages, latest_debate["id"]
    )
    analysis["source"] = {
        "mode": "selected_debate" if debate_id else "latest_debate",
        "debate_id": latest_debate["id"],
        "name": latest_debate["name"],
        "default_index": latest_debate["default_index"],
        "topic": topic,
        "debate_count": len(debates),
    }
    return analysis


@app.get("/api/sessions/{session_id}/intelligence")
def session_intelligence(
    session_id: str, debate_id: str | None = Query(default=None, alias="debate_id")
) -> dict:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    debates = db.list_debates(session_id)
    selected_debate = None
    if debate_id:
        selected_debate = db.get_debate(session_id, debate_id)
        if not selected_debate:
            raise HTTPException(status_code=404, detail="Debate not found.")
    elif debates:
        selected_debate = debates[0]

    records = []
    experiences = []
    if selected_debate:
        records = db.list_intelligence_records(session_id, selected_debate["id"])
    council_settings = db.get_council_settings()
    experiences = db.list_agent_experience(
        session_id=session_id,
        include_universal=bool(council_settings.get("universal_experience", True)),
        limit=80,
    )
    by_type: dict[str, list[dict]] = {}
    for record in records:
        by_type.setdefault(record["record_type"], []).append(record)
    team_rooms = {
        "pro": [record for record in records if record.get("team") == "pro"],
        "con": [record for record in records if record.get("team") == "con"],
    }
    return {
        "debate": selected_debate,
        "records": records,
        "claims": by_type.get("claim", []),
        "challenges": by_type.get("challenge", []),
        "evidence": by_type.get("evidence", []),
        "scorecards": by_type.get("judge_scorecard", []),
        "verdict_reviews": by_type.get("verdict_review", []),
        "values": by_type.get("value_record", []),
        "memories": by_type.get("memory_saved", []),
        "reviews": by_type.get("post_debate_review", []),
        "team_rooms": team_rooms,
        "experiences": experiences,
        "feedback_questions": [
            {
                "key": "judge_missed",
                "question": "Did the Judge miss an important argument?",
                "options": ["No", "Yes, from Pro", "Yes, from Con", "Other..."],
            },
            {
                "key": "strongest_contribution",
                "question": "Which contribution most improved the debate?",
                "options": ["Pro argument", "Con argument", "Research/evidence", "Cross-exam/challenge", "Other..."],
            },
            {
                "key": "weakest_point",
                "question": "What should the council avoid or improve next time?",
                "options": ["Unsupported claim", "Weak evidence", "Ignored challenge", "Unclear verdict", "Other..."],
            },
        ] if selected_debate else [],
    }


@app.post("/api/sessions/{session_id}/debates/{debate_id}/feedback")
def add_debate_feedback(session_id: str, debate_id: str, payload: FeedbackRequest) -> dict:
    if not db.get_debate(session_id, debate_id):
        raise HTTPException(status_code=404, detail="Debate not found.")
    saved = db.add_post_debate_feedback(
        session_id=session_id,
        debate_id=debate_id,
        question_key=payload.question_key,
        answer=payload.answer,
    )
    db.add_agent_experience(
        scope="chat",
        session_id=session_id,
        agent_id="council",
        lesson_type="user_feedback",
        lesson=f"User feedback for {payload.question_key}: {payload.answer}",
        confidence="medium",
        basis=[{"debate_id": debate_id, "feedback_id": saved["id"]}],
    )
    return saved


@app.post("/api/sessions/{session_id}/debates/{debate_id}/verdict-review")
def add_verdict_review(session_id: str, debate_id: str, payload: VerdictReviewRequest) -> dict:
    debate = db.get_debate(session_id, debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found.")
    session_settings = db.get_session_settings(session_id)
    judging_settings = (
        session_settings.get("judging_settings", {}) if isinstance(session_settings, dict) else {}
    )
    if not judging_settings.get("allow_user_verdict_challenge", True):
        raise HTTPException(
            status_code=403,
            detail="Verdict challenges and overrides are disabled for this chat.",
        )
    saved = db.add_verdict_review(
        session_id=session_id,
        debate_id=debate_id,
        action=payload.action,
        winner=payload.winner,
        note=payload.note,
    )
    if not saved:
        raise HTTPException(status_code=400, detail="Could not save verdict review.")
    action_label = "User verdict override" if payload.action == "override" else "User verdict challenge"
    db.add_intelligence_record(
        session_id=session_id,
        debate_id=debate_id,
        record_type="verdict_review",
        team="neutral",
        role="user",
        agent_id="user",
        title=action_label,
        content=(
            f"{action_label}: {payload.winner.upper()}. "
            f"{payload.note.strip() or 'No note provided.'}"
        ),
        status="Saved",
        confidence=1.0,
        payload={
            "action": payload.action,
            "winner": payload.winner,
            "note": payload.note.strip(),
            "review_id": saved["id"],
        },
        basis=[{"type": "user_verdict_review", "review_id": saved["id"]}],
    )
    return saved


@app.websocket("/ws/debates/{session_id}")
async def debate_socket(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if not db.get_session(session_id):
        await safe_send_json(websocket, {"type": "error", "message": "Session not found."})
        await websocket.close(code=1008)
        return

    try:
        while True:
            payload = await websocket.receive_json()
            if payload.get("type") not in {"start_debate", "start_interaction", "end_practice_debate"}:
                if not await safe_send_json(
                    websocket,
                    {"type": "error", "message": "Unknown WebSocket event type."}
                ):
                    return
                continue

            topic = str(payload.get("topic", "")).strip()
            selected_model = str(payload.get("model", "")).strip()
            try:
                if payload.get("type") == "end_practice_debate":
                    await debate_manager.end_practice_debate(websocket, session_id, selected_model)
                else:
                    await debate_manager.run_interaction(
                        websocket,
                        session_id,
                        topic,
                        selected_model,
                        practice_side=str(payload.get("practice_side", "")).strip() or None,
                    )
            except ClientDisconnectedError:
                return
            except DebateError as exc:
                if not await safe_send_json(
                    websocket,
                    {"type": "error", "message": debate_manager._provider_error_message(exc)},
                ):
                    return
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                runtime_diary.record(
                    "backend terminal",
                    "websocket handler error",
                    debate_manager._provider_error_message(exc),
                    session_id=session_id,
                )
                if not await safe_send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": "Debate failed because of an internal server error. Check the backend terminal for the sanitized details.",
                    },
                ):
                    return
    except WebSocketDisconnect:
        return


# ─────────────────────────────────────────────────────────────────────────────
# REST-Based Turn Orchestration System
# ─────────────────────────────────────────────────────────────────────────────

import litellm
from litellm import acompletion
from app.model_registry import get_model
from textwrap import dedent

async def rest_generate_completion(model_name: str, messages: list[dict[str, str]], max_tokens: int = 500) -> str:
    # If mock_llm is true, return mock text
    if settings.mock_llm:
        return f"[Mock Response for model {model_name}] This is a compelling, highly structured logical contribution demonstrating rigor, citing robust facts, and framing a clear thesis for the debate round."

    model = get_model(model_name)
    if not model:
        return f"[Fallback Response] Model {model_name} is unmapped, here is fallback debate content."

    route = model.route
    if not route:
        # Fallback to mock/optimistic NVIDIA call or mock if key is missing
        if not os.getenv("NVIDIA_API_KEY"):
            return f"[Mock Fallback Response] API Key for {model_name} was missing. Here is a simulated, high-quality analytical contribution."
        # If API key exists, try creating route dynamically
        litellm_model = f"openai/nvidia/{model_name}" if not model_name.startswith("openai/") else model_name
        from app.model_registry import ModelRoute
        route = ModelRoute(litellm_model, os.getenv("NVIDIA_API_KEY", ""), "nvidia")

    candidate_models = (route.litellm_model, *route.fallback_models)
    last_exc = None
    for candidate_model in candidate_models:
        try:
            kwargs = {
                "model": candidate_model,
                "messages": messages,
                "api_key": route.api_key,
                "stream": False,
                "temperature": 0.55,
                "max_tokens": max_tokens,
                "timeout": 45,
            }
            if route.api_base:
                kwargs["api_base"] = route.api_base
            response = await acompletion(**kwargs)
            # Safe parsing
            if response and response.choices:
                return response.choices[0].message.content or ""
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        logger.error(f"REST LiteLLM call failed for {model_name}: {last_exc}")
        return f"[LLM Error Fallback Response] Model {model_name} encountered an error: {str(last_exc)}"
    return "[Empty Response]"


@app.get("/debate/models")
def get_debate_models():
    return {"models": [m.name for m in available_models()]}


@app.get("/debate/modes")
def get_debate_modes():
    return {
        "modes": [
            {"key": "ai_vs_human", "label": "Human vs AI"},
            {"key": "ai_vs_ai", "label": "AI vs AI"}
        ]
    }


@app.post("/debate/create")
def rest_create_debate_session(payload: RESTDebateCreateRequest):
    mode = payload.mode.strip().lower()
    ai_a = payload.ai_a_model.strip()
    ai_b = (payload.ai_b_model or "").strip()
    judge = payload.judge_model.strip()
    rounds = payload.rounds

    if mode == "ai_vs_human":
        if ai_a.lower() == judge.lower():
            raise HTTPException(
                status_code=422,
                detail="Judge AI must not be the same model as the Opponent AI."
            )
    elif mode == "ai_vs_ai":
        if not ai_b:
            raise HTTPException(
                status_code=422,
                detail="AI B model is required for AI vs AI mode."
            )
        if ai_a.lower() == judge.lower() or ai_b.lower() == judge.lower():
            raise HTTPException(
                status_code=422,
                detail="Judge model must always be different from both AI A and AI B."
            )
        if ai_a.lower() == ai_b.lower():
            raise HTTPException(
                status_code=422,
                detail="AI A and AI B must be different debater models."
            )
    else:
        raise HTTPException(
            status_code=422,
            detail="Invalid debate mode selected."
        )

    session = db.create_session(
        settings.max_sessions,
        mode=mode,
        ai_a_model=ai_a,
        ai_b_model=ai_b,
        judge_model=judge,
        rounds=rounds,
    )
    return session


@app.post("/debate/start")
async def rest_start_debate(payload: RESTDebateStartRequest):
    session_id = payload.session_id
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="Topic must not be empty.")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    debate = db.create_debate(session_id, topic, mode="debate")
    debate_id = debate["id"]

    db.add_message(
        session_id=session_id,
        debate_id=debate_id,
        role="user",
        speaker="System" if session["mode"] == "ai_vs_ai" else "You",
        model="user" if session["mode"] == "ai_vs_ai" else "human",
        content=topic,
    )

    if session["mode"] == "ai_vs_human":
        ai_a_model = session["ai_a_model"]
        sys_prompt = dedent(
            f"""
            You are a master debater in a highly prestigious strategic council. Your objective is to argue with supreme clarity, academic rigour, and unyielding logical force.
            You are debating the topic: '{topic}'.
            Your assigned side: CON (opposing side).
            Your opponent is: Human (proposing side).
            Keep your response academic, extremely cohesive, and under 500 words. Do not write meta-commentary.
            """
        ).strip()
        user_prompt = dedent(
            f"""
            Topic: {topic}
            Your Side: CON

            The Human Pro opponent has initiated the debate with the topic proposal:
            "{topic}"

            It is your turn. Write your opening constructive argument opposing this topic.
            """
        ).strip()

        completion = await rest_generate_completion(
            model_name=ai_a_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600
        )

        db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="assistant",
            speaker=f"Con - {ai_a_model}",
            model=ai_a_model,
            content=completion,
            phase={
                "key": "con_constructive_1",
                "title": "Con Opening Argument",
                "index": 1,
                "total": session["rounds"] * 2,
                "kind": "constructive"
            }
        )

    else:
        ai_a_model = session["ai_a_model"]
        sys_prompt = dedent(
            f"""
            You are a master debater in a highly prestigious strategic council. Your objective is to argue with supreme clarity, academic rigour, and unyielding logical force.
            You are debating the topic: '{topic}'.
            Your assigned side: PRO (supporting side).
            Your opponent model is: {session['ai_b_model']}.
            Keep your response academic, extremely cohesive, and under 500 words. Do not write meta-commentary.
            """
        ).strip()
        user_prompt = dedent(
            f"""
            Topic: {topic}
            Your Side: PRO

            The debate has begun on the topic: "{topic}".
            It is your turn. Write your opening constructive argument in favor of this topic.
            """
        ).strip()

        completion = await rest_generate_completion(
            model_name=ai_a_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600
        )

        db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="assistant",
            speaker=f"Pro - {ai_a_model}",
            model=ai_a_model,
            content=completion,
            phase={
                "key": "pro_constructive_1",
                "title": "Pro Opening Argument",
                "index": 1,
                "total": session["rounds"] * 2,
                "kind": "constructive"
            }
        )

    return {
        "session": db.get_session(session_id),
        "debate": db.get_debate(session_id, debate_id),
        "messages": db.list_messages_for_debate(session_id, debate_id)
    }


@app.post("/debate/next-turn")
async def rest_next_turn(payload: RESTDebateNextTurnRequest):
    session_id = payload.session_id
    debate_id = payload.debate_id
    session = db.get_session(session_id)
    debate = db.get_debate(session_id, debate_id)

    if not session or not debate:
        raise HTTPException(status_code=404, detail="Session or Debate not found.")

    topic = debate["topic"]
    messages = db.list_messages_for_debate(session_id, debate_id)

    if session["mode"] == "ai_vs_human":
        human_text = (payload.content or "").strip()
        if not human_text:
            raise HTTPException(status_code=422, detail="Human argument content is required for next turn.")

        human_messages = [m for m in messages if m["role"] == "user" and m["model"] == "human"]
        human_turns = len(human_messages) + 1

        human_turn_idx = human_turns * 2 - 1
        db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="user",
            speaker="You",
            model="human",
            content=human_text,
            phase={
                "key": f"pro_rebuttal_{human_turns}",
                "title": f"Pro Turn {human_turns}",
                "index": human_turn_idx,
                "total": session["rounds"] * 2,
                "kind": "rebuttal"
            }
        )

        updated_messages = db.list_messages_for_debate(session_id, debate_id)
        transcript_text = "\n\n".join([f"{m['speaker']}: {m['content']}" for m in updated_messages if m["model"] != "user"])

        ai_a_model = session["ai_a_model"]
        is_last_round = human_turns >= session["rounds"]

        sys_prompt = dedent(
            f"""
            You are a master debater in a highly prestigious strategic council. Your objective is to argue with supreme clarity, academic rigour, and unyielding logical force.
            You are debating the topic: '{topic}'.
            Your assigned side: CON (opposing side).
            Your opponent is: Human (proposing side).
            Keep your response academic, extremely cohesive, and under 500 words. Do not write meta-commentary.
            """
        ).strip()
        user_prompt = dedent(
            f"""
            Topic: {topic}
            Your Side: CON

            Below is the chronological transcript of the debate so far:
            {transcript_text}

            It is your turn. Write your rebuttal opposing the Pro side's arguments.
            """
        ).strip()

        completion = await rest_generate_completion(
            model_name=ai_a_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600
        )

        ai_turn_idx = human_turns * 2
        db.add_message(
            session_id=session_id,
            debate_id=debate_id,
            role="assistant",
            speaker=f"Con - {ai_a_model}",
            model=ai_a_model,
            content=completion,
            phase={
                "key": f"con_rebuttal_{human_turns}",
                "title": f"Con Rebuttal {human_turns}",
                "index": ai_turn_idx,
                "total": session["rounds"] * 2,
                "kind": "rebuttal"
            }
        )

        if is_last_round:
            final_messages = db.list_messages_for_debate(session_id, debate_id)
            final_transcript = "\n\n".join([f"{m['speaker']}: {m['content']}" for m in final_messages if m["model"] != "user"])

            judge_model = session["judge_model"]
            judge_sys = dedent(
                f"""
                You are an elite, independent Adjudicator. Your task is to analyze the debate with absolute objectivity and render a final, structured verdict.
                You must:
                1. Independently evaluate the logical coherence of both sides.
                2. Identify key points of clash and who won them.
                3. Highlight any ignored challenges or unsupported claims.
                4. Explicitly declare a winner ('Pro' or 'Con') or declare it a draw/unclear with a rigorous justification.
                5. Do not bias towards either side. Be neutral, critical, and objective.
                """
            ).strip()
            judge_user = dedent(
                f"""
                Topic: {topic}

                Below is the complete transcript of the debate:
                {final_transcript}

                Perform your final adjudication now. Write a comprehensive, premium evaluation detailing your reasoning, a scoring matrix, and a clear declaration of the winner.
                """
            ).strip()

            verdict = await rest_generate_completion(
                model_name=judge_model,
                messages=[
                    {"role": "system", "content": judge_sys},
                    {"role": "user", "content": judge_user}
                ],
                max_tokens=1000
            )

            db.add_message(
                session_id=session_id,
                debate_id=debate_id,
                role="judge",
                speaker="Judge",
                model=judge_model,
                content=verdict,
            )

            db.complete_debate(debate_id, verdict)

    else:
        ai_messages = [m for m in messages if m["role"] == "assistant"]
        turn_count = len(ai_messages)

        if turn_count >= session["rounds"] * 2:
            return {
                "session": db.get_session(session_id),
                "debate": db.get_debate(session_id, debate_id),
                "messages": db.list_messages_for_debate(session_id, debate_id)
            }

        is_con_turn = (turn_count % 2 == 1)
        transcript_text = "\n\n".join([f"{m['speaker']}: {m['content']}" for m in messages if m["model"] != "user"])

        if is_con_turn:
            ai_b_model = session["ai_b_model"]
            sys_prompt = dedent(
                f"""
                You are a master debater in a highly prestigious strategic council. Your objective is to argue with supreme clarity, academic rigour, and unyielding logical force.
                You are debating the topic: '{topic}'.
                Your assigned side: CON (opposing side).
                Your opponent model is: {session['ai_a_model']}.
                Keep your response academic, extremely cohesive, and under 500 words. Do not write meta-commentary.
                """
            ).strip()
            user_prompt = dedent(
                f"""
                Topic: {topic}
                Your Side: CON

                Below is the chronological transcript of the debate so far:
                {transcript_text}

                It is your turn. Write your next strategic argument opposing the Pro side's thesis.
                """
            ).strip()

            completion = await rest_generate_completion(
                model_name=ai_b_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=600
            )

            current_round = (turn_count // 2) + 1
            db.add_message(
                session_id=session_id,
                debate_id=debate_id,
                role="assistant",
                speaker=f"Con - {ai_b_model}",
                model=ai_b_model,
                content=completion,
                phase={
                    "key": f"con_rebuttal_{current_round}",
                    "title": f"Con Turn {current_round}",
                    "index": turn_count + 1,
                    "total": session["rounds"] * 2,
                    "kind": "rebuttal"
                }
            )

            if current_round >= session["rounds"]:
                final_messages = db.list_messages_for_debate(session_id, debate_id)
                final_transcript = "\n\n".join([f"{m['speaker']}: {m['content']}" for m in final_messages if m["model"] != "user"])

                judge_model = session["judge_model"]
                judge_sys = dedent(
                    f"""
                    You are an elite, independent Adjudicator. Your task is to analyze the debate with absolute objectivity and render a final, structured verdict.
                    You must:
                    1. Independently evaluate the logical coherence of both sides.
                    2. Identify key points of clash and who won them.
                    3. Highlight any ignored challenges or unsupported claims.
                    4. Explicitly declare a winner ('Pro' or 'Con') or declare it a draw/unclear with a rigorous justification.
                    5. Do not bias towards either side. Be neutral, critical, and objective.
                    """
                ).strip()
                judge_user = dedent(
                    f"""
                    Topic: {topic}

                    Below is the complete transcript of the debate:
                    {final_transcript}

                    Perform your final adjudication now. Write a comprehensive, premium evaluation detailing your reasoning, a scoring matrix, and a clear declaration of the winner.
                    """
                ).strip()

                verdict = await rest_generate_completion(
                    model_name=judge_model,
                    messages=[
                        {"role": "system", "content": judge_sys},
                        {"role": "user", "content": judge_user}
                    ],
                    max_tokens=1000
                )

                db.add_message(
                    session_id=session_id,
                    debate_id=debate_id,
                    role="judge",
                    speaker="Judge",
                    model=judge_model,
                    content=verdict,
                )

                db.complete_debate(debate_id, verdict)

        else:
            ai_a_model = session["ai_a_model"]
            sys_prompt = dedent(
                f"""
                You are a master debater in a highly prestigious strategic council. Your objective is to argue with supreme clarity, academic rigour, and unyielding logical force.
                You are debating the topic: '{topic}'.
                Your assigned side: PRO (supporting side).
                Your opponent model is: {session['ai_b_model']}.
                Keep your response academic, extremely cohesive, and under 500 words. Do not write meta-commentary.
                """
            ).strip()
            user_prompt = dedent(
                f"""
                Topic: {topic}
                Your Side: PRO

                Below is the chronological transcript of the debate so far:
                {transcript_text}

                It is your turn. Write your next strategic argument defending the Pro side's thesis.
                """
            ).strip()

            completion = await rest_generate_completion(
                model_name=ai_a_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=600
            )

            current_round = (turn_count // 2) + 1
            db.add_message(
                session_id=session_id,
                debate_id=debate_id,
                role="assistant",
                speaker=f"Pro - {ai_a_model}",
                model=ai_a_model,
                content=completion,
                phase={
                    "key": f"pro_rebuttal_{current_round}",
                    "title": f"Pro Turn {current_round}",
                    "index": turn_count + 1,
                    "total": session["rounds"] * 2,
                    "kind": "rebuttal"
                }
            )

    return {
        "session": db.get_session(session_id),
        "debate": db.get_debate(session_id, debate_id),
        "messages": db.list_messages_for_debate(session_id, debate_id)
    }

