from pydantic import BaseModel, Field


class ChatSession(BaseModel):
    id: str
    name: str
    mode: str = "ai_vs_ai"
    ai_a_model: str = ""
    ai_b_model: str = ""
    judge_model: str = ""
    rounds: int = 2
    default_index: int
    created_at: str
    updated_at: str


class CreateSessionRequest(BaseModel):
    mode: str = Field(default="ai_vs_ai", max_length=32)
    ai_a_model: str = ""
    ai_b_model: str = ""
    judge_model: str = ""
    rounds: int = 2
    settings: dict | None = None


class RenameSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RenameDebateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class DebateStartRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=5500)
    model: str = Field(min_length=1, max_length=120)


class CouncilSettingsUpdate(BaseModel):
    universal_experience: bool | None = None
    use_agent_identity_profiles: bool | None = None
    use_user_debate_profile: bool | None = None
    debate_intelligence_depth: str | None = None
    use_value_consequence_system: bool | None = None
    default_judge_mode: str | None = None
    theme: str | None = None
    confirmation_preferences: dict[str, bool] | None = None


class ResetAgentExperienceRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=120)


class ResetUserDebateProfileRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=120)


class FeedbackRequest(BaseModel):
    question_key: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=1200)


class SessionSettingsUpdate(BaseModel):
    overall_model: str | None = Field(default=None, max_length=120)
    debaters_per_team: int | None = Field(default=None, ge=1, le=4)
    discussion_messages_per_team: int | None = Field(default=None, ge=1, le=4)
    judge_assistant_enabled: bool | None = None
    agent_settings: dict[str, dict] | None = None
    role_models: dict[str, str] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=120, le=2000)
    debate_tone: str | None = None
    language: str | None = None
    response_length: str | None = None
    auto_scroll: bool | None = None
    show_timestamps: bool | None = None
    show_token_count: bool | None = None
    show_money_cost: bool | None = None
    cost_currency: str | None = Field(default=None, max_length=3)
    show_model_costs: bool | None = None
    show_every_message_cost_in_debate: bool | None = None
    context_window: int | None = Field(default=None, ge=0, le=6)
    debate_rounds: int | None = Field(default=None, ge=1, le=6)
    researcher_web_search: bool | None = None
    fact_check_mode: bool | None = None
    export_format: str | None = None
    auto_save_interval: int | None = Field(default=None, ge=5, le=300)
    use_experience: bool | None = None
    judge_mode: str | None = None
    evidence_strictness: str | None = None
    practice_settings: dict | None = None
    judging_settings: dict | None = None


class VerdictReviewRequest(BaseModel):
    action: str = Field(pattern="^(challenge|override)$")
    winner: str = Field(default="unclear", pattern="^(pro|con|unclear)$")
    note: str = Field(default="", max_length=1200)


class DebateIntelligenceRecord(BaseModel):
    id: str
    session_id: str
    debate_id: str
    record_type: str
    team: str
    role: str
    agent_id: str
    title: str
    content: str
    status: str
    confidence: float
    payload: dict
    basis: list
    created_at: str
    updated_at: str


class AgentExperienceRecord(BaseModel):
    id: str
    scope: str
    session_id: str | None = None
    agent_id: str
    lesson_type: str
    lesson: str
    confidence: str
    basis: list
    created_at: str
    last_used_at: str | None = None
    use_count: int


class DebateRecord(BaseModel):
    id: str
    session_id: str
    name: str
    default_index: int
    mode: str
    topic: str
    status: str
    judge_summary: str | None = None
    error: str | None = None
    metadata: dict | None = None
    started_at: str
    finished_at: str | None = None


class DebateMessage(BaseModel):
    id: str
    session_id: str
    debate_id: str
    role: str
    speaker: str
    model: str
    content: str
    cost_summary: dict | None = None
    debate_cost_summary: dict | None = None
    phase_key: str | None = None
    phase_title: str | None = None
    phase_index: int | None = None
    phase_total: int | None = None
    phase_kind: str | None = None
    sequence: int
    created_at: str


class RESTDebateCreateRequest(BaseModel):
    mode: str
    ai_a_model: str
    ai_b_model: str | None = ""
    judge_model: str
    rounds: int = 2


class RESTDebateStartRequest(BaseModel):
    session_id: str
    topic: str


class RESTDebateNextTurnRequest(BaseModel):
    session_id: str
    debate_id: str
    content: str | None = None


class SessionModelsUpdateRequest(BaseModel):
    ai_a_model: str | None = None
    ai_b_model: str | None = None
    judge_model: str | None = None
    rounds: int | None = None
