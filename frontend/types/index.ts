export type ChatSession = {
  id: string;
  name: string;
  mode: "ai_vs_ai" | "ai_vs_human";
  default_index: number;
  created_at: string;
  updated_at: string;
};

export type PracticeSettings = {
  human_side: "Auto" | "Pro" | "Con";
  practice_flow: "Free" | "Structured";
  structured_rounds: number;
  use_user_profile: boolean;
  trainer_style: "Coach" | "Direct" | "Gentle" | "Examiner";
  training_focus: "Full Debate" | "Rebuttal" | "Evidence" | "Clarity" | "Cross-Examination";
  opponent_difficulty: "Adaptive" | "Beginner" | "Normal" | "Hard";
};

export type UserDebateProfile = {
  version: number;
  debates_completed: number;
  practice_debates_completed: number;
  wins: Record<"pro" | "con" | "unclear", number>;
  side_history: Record<"pro" | "con" | "auto", number>;
  strengths: string[];
  weaknesses: string[];
  trainer_notes: string[];
  style_tags: string[];
  last_updated_at: string;
};

export type UserDebateProfileOverview = {
  profile: UserDebateProfile;
  recent_practice_debates: Array<{
    id: string;
    session_id: string;
    session_name: string;
    name: string;
    topic: string;
    status: string;
    winner: "pro" | "con" | "unclear";
    human_side: "pro" | "con" | "auto";
    practice_flow: "Free" | "Structured";
    structured_rounds: number;
    started_at: string;
    finished_at: string | null;
  }>;
  recommendations: string[];
  coach_summary: string;
  less_practiced_side: "pro" | "con";
};

export type PracticeState = {
  active: boolean;
  debate_id?: string;
  topic?: string;
  human_side?: string;
  ai_side?: string;
  side_source?: string;
  side_reason?: string;
  practice_flow?: "Free" | "Structured";
  structured_rounds?: number;
  human_turns?: number;
  rounds_left?: number | null;
  ending?: boolean;
};

export type DebateMessage = {
  id: string;
  session_id: string;
  debate_id: string;
  role: string;
  speaker: string;
  model: string;
  content: string;
  cost_summary: CostSummary | null;
  debate_cost_summary: CostSummary | null;
  phase_key: string | null;
  phase_title: string | null;
  phase_index: number | null;
  phase_total: number | null;
  phase_kind: string | null;
  sequence: number;
  created_at: string;
};

export type CouncilSettings = {
  universal_experience: boolean;
  use_agent_identity_profiles: boolean;
  use_user_debate_profile: boolean;
  debate_intelligence_depth: "Light" | "Normal" | "Deep";
  use_value_consequence_system: boolean;
  default_judge_mode: "Debate Performance" | "Truth-Seeking" | "Hybrid";
  theme: "Light" | "Dark" | "System";
  confirmation_preferences: Record<
    "delete_chat" | "clear_chat_history" | "clear_chat_memory",
    boolean
  >;
};

export type DebateIntelligenceRecord = {
  id: string;
  session_id: string;
  debate_id: string;
  record_type: string;
  team: string;
  role: string;
  agent_id: string;
  title: string;
  content: string;
  status: string;
  confidence: number;
  payload: Record<string, unknown>;
  basis: unknown[];
  created_at: string;
  updated_at: string;
};

export type AgentExperienceRecord = {
  id: string;
  scope: string;
  session_id: string | null;
  agent_id: string;
  lesson_type: string;
  lesson: string;
  confidence: "low" | "medium" | "high";
  basis: unknown[];
  created_at: string;
  last_used_at: string | null;
  use_count: number;
};

export type AgentExperienceOverview = {
  experiences: AgentExperienceRecord[];
  memory_events: DebateIntelligenceRecord[];
  summary: {
    total_records: number;
    distinct_agents: number;
    universal_records: number;
    chat_records: number;
    high_confidence_records: number;
    total_uses: number;
    last_recorded_at: string;
  };
  by_agent: Array<{
    agent_id: string;
    record_count: number;
    use_count: number;
    high_confidence_count: number;
    lesson_types: Record<string, number>;
    last_recorded_at: string;
  }>;
  by_scope: Record<string, number>;
  by_lesson_type: Record<string, number>;
};

export type DebateIntelligence = {
  debate: DebateRecord | null;
  records: DebateIntelligenceRecord[];
  claims: DebateIntelligenceRecord[];
  challenges: DebateIntelligenceRecord[];
  evidence: DebateIntelligenceRecord[];
  scorecards: DebateIntelligenceRecord[];
  verdict_reviews: DebateIntelligenceRecord[];
  values: DebateIntelligenceRecord[];
  memories: DebateIntelligenceRecord[];
  reviews: DebateIntelligenceRecord[];
  team_rooms: { pro: DebateIntelligenceRecord[]; con: DebateIntelligenceRecord[] };
  experiences: AgentExperienceRecord[];
  feedback_questions: Array<{ key: string; question: string; options: string[] }>;
};

export type SessionSettings = {
  overall_model: string;
  debaters_per_team: number;
  discussion_messages_per_team: number;
  judge_assistant_enabled: boolean;
  agent_settings: Record<
    string,
    {
      model: string;
      temperature: number;
      max_tokens: number;
      response_length: string;
      web_search: boolean;
      always_on: boolean;
    }
  >;
  role_models: Record<string, string>;
  temperature: number;
  max_tokens: number;
  debate_tone: string;
  language: string;
  response_length: string;
  auto_scroll: boolean;
  show_timestamps: boolean;
  show_token_count: boolean;
  show_money_cost: boolean;
  cost_currency: string;
  show_model_costs: boolean;
  show_every_message_cost_in_debate: boolean;
  context_window: number;
  debate_rounds: number;
  researcher_web_search: boolean;
  fact_check_mode: boolean;
  export_format: string;
  auto_save_interval: number;
  use_experience: boolean;
  judge_mode: string;
  evidence_strictness: string;
  practice_settings: PracticeSettings;
  judging_settings: {
    judge_panel_size: 1 | 3 | 5;
    analytics_weight: number;
    allow_user_verdict_challenge: boolean;
  };
  updated_at?: string;
};

export type CostSummary = {
  currency: string;
  total: number;
  total_usd: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
  estimated: boolean;
  pricing_complete?: boolean;
  warnings?: string[];
  rate_source: string;
  models: Array<{
    model: string;
    input_tokens: number;
    output_tokens: number;
    calls: number;
    cost: number;
    cost_usd: number;
    input_usd_per_1m: number;
    output_usd_per_1m: number;
    pricing_source?: string;
    pricing_live?: boolean;
    pricing_available?: boolean;
  }>;
};

export type SupportedModel = {
  name: string;
  provider: string;
  provider_label: string;
  api_key_env: string;
  litellm_model: string;
  configured: boolean;
  availability_reason?: string | null;
};

export type ProviderSummary = {
  provider: string;
  provider_label: string;
  api_key_env: string;
  configured: boolean;
  unlocked_model_count: number;
  total_model_count: number;
  models: SupportedModel[];
  status_label?: string;
  status_reason?: string | null;
};

export type ModelsResponse = {
  models: SupportedModel[];
  providers: ProviderSummary[];
  available_model_count: number;
  real_available_model_count: number;
  minimum_debate_models: number;
  selection_required: boolean;
  mock_mode: boolean;
  availability_notice?: string | null;
};

export type DebateAssignment = {
  role: string;
  speaker: string;
  model: string;
  provider: string;
};

export type DebateRecord = {
  id: string;
  session_id: string;
  name: string;
  default_index: number;
  mode: string;
  topic: string;
  status: string;
  judge_summary: string | null;
  error: string | null;
  metadata?: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
};

export type DebateAnalytics = {
  turn_count: number;
  round: number;
  method_notes: string[];
  ensemble: {
    majority_vote: string;
    weighted_vote: string;
    votes: Record<string, number>;
    weighted_votes: Record<string, number>;
  };
  bayesian: {
    leader: string;
    probabilities: Record<string, number>;
  };
  argument_mining: {
    claims: Array<{
      speaker: string;
      stance: string;
      confidence: number;
      text: string;
    }>;
    evidence_count: number;
    rebuttal_count: number;
    redundancy_count: number;
  };
  stance: {
    by_role: Record<string, string>;
  };
  confidence: {
    average: number;
    by_role: Record<string, number>;
  };
  credibility: {
    elo_by_role: Record<string, number>;
    normalized_by_role: Record<string, number>;
  };
  game_theory: {
    auction_winner: string | null;
    auction_stance: string;
    winning_bid: number;
    nash_pressure: number;
  };
  argument_graph: {
    node_count: number;
    edge_count: number;
    support_edges: number;
    attack_edges: number;
    strongest_claims: Array<{
      speaker: string;
      stance: string;
      strength: number;
      text: string;
    }>;
  };
  attention: {
    top_terms: string[];
  };
  delphi: {
    convergence: number;
    rounds_analyzed: number;
    last_round_distribution: Record<string, number>;
  };
  mixture_of_experts: {
    role_weights: Record<string, number>;
    lead_expert: string | null;
  };
  source?: {
    mode: "latest_debate" | "selected_debate";
    debate_id: string;
    name: string;
    default_index: number;
    topic: string;
    debate_count: number;
  };
  phase?: {
    current: {
      key: string;
      title: string;
      kind: string;
      index: number;
      total: number;
      speaker: string;
      team: string;
    } | null;
    completed: number;
    total: number;
    flow_name: string;
    sequence: Array<{
      key: string;
      title: string;
      kind: string;
      index: number;
      total: number;
      speaker: string;
      team: string;
    }>;
    pro_position: string;
    con_position: string;
  };
  session_charts?: {
    win_rate_by_team: {
      pro: number;
      con: number;
      unclear: number;
      resolved: number;
      total_completed: number;
      pro_rate: number;
      con_rate: number;
    };
    cost_by_phase: Record<string, number>;
    debate_durations: Array<{
      debate_id: string;
      name: string;
      status: string;
      duration_seconds: number;
    }>;
    messages_by_role: Record<string, number>;
    citations: Array<{
      speaker: string;
      url: string;
      domain: string;
      debate_id: string;
      debate_name: string;
      phase_title: string;
    }>;
  };
};

export type DebateEvent =
  | {
      type: "debate_started";
      debate: DebateRecord;
      topic: string;
      positions?: { pro: string; con: string };
      selected_model: SupportedModel;
      assignments: DebateAssignment[];
      judge: { speaker: string; model: string; provider: string };
      active_debates: number;
    }
  | {
      type: "interaction_started";
      mode: "chat" | "practice";
      debate: { id: string; topic: string };
      selected_model: SupportedModel;
    }
  | {
      type: "practice_started";
      debate: DebateRecord;
      state: PracticeState;
      selected_model: SupportedModel;
    }
  | {
      type: "practice_state_updated";
      state: PracticeState;
    }
  | {
      type: "practice_completed";
      debate_id: string;
      profile: UserDebateProfile;
      cost_summary?: CostSummary;
    }
  | {
      type: "team_preparation_started" | "team_preparation_completed";
      debate_id: string;
      message: string;
    }
  | {
      type: "message_started";
      stream_id: string;
      message: DebateMessage;
      round: number | "summary";
    }
  | {
      type: "message_delta";
      stream_id: string;
      delta: string;
    }
  | {
      type: "message_replaced";
      stream_id: string;
      content: string;
    }
  | {
      type: "message_completed";
      stream_id: string;
      message: DebateMessage;
    }
  | {
      type: "analysis_updated";
      round: number;
      analysis: DebateAnalytics;
    }
  | {
      type: "debate_completed";
      debate_id: string;
      judge_summary: string;
      active_debates: number;
      cost_summary?: CostSummary;
    }
  | {
      type: "interaction_completed";
      mode: "chat" | "practice";
      debate_id: string;
      cost_summary?: CostSummary;
    }
  | {
      type: "error";
      message: unknown;
    };
