"use client";

import { useMemo, useState, type ReactNode } from "react";

import type {
  AgentExperienceOverview,
  ChatSession,
  ModelsResponse,
  UserDebateProfileOverview
} from "@/types";

type GlobalWorkspaceProps = {
  view: "welcome" | "aiExperiences" | "userProfile";
  sessions: ChatSession[];
  models: ModelsResponse | null;
  experiences: AgentExperienceOverview | null;
  profileOverview: UserDebateProfileOverview | null;
  onCreateSession: (mode?: ChatSession["mode"]) => void;
};

export function GlobalWorkspace({
  view,
  sessions,
  models,
  experiences,
  profileOverview,
  onCreateSession
}: GlobalWorkspaceProps) {
  if (view === "aiExperiences") {
    return <AiDebaterExperiencesPage sessions={sessions} overview={experiences} />;
  }
  if (view === "userProfile") {
    return <UserDebateProfilePage overview={profileOverview} onCreateSession={onCreateSession} />;
  }
  return <WelcomePage models={models} onCreateSession={onCreateSession} />;
}

function WelcomePage({
  models,
  onCreateSession
}: {
  models: ModelsResponse | null;
  onCreateSession: (mode?: ChatSession["mode"]) => void;
}) {
  const providers = (models?.providers ?? []).filter((p) => p.unlocked_model_count > 0);
  const available = models?.available_model_count ?? 0;
  return (
    <main className="flex h-full min-w-0 flex-1 flex-col" style={{ background: 'var(--sm-bg-primary)' }}>
      <div className="sm-aurora-bg" />
      <div className="sm-grid-bg" />

      <section className="relative z-10 min-h-0 flex-1 overflow-y-auto">
        {/* ── Hero ── */}
        <div className="relative flex flex-col items-center justify-center px-6 pb-8 pt-16 text-center">
          <div className="sm-animate-fade-in mb-4 inline-flex items-center gap-2 rounded-full px-4 py-1.5"
               style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)' }}>
            <span className="sm-orb" style={{ width: 6, height: 6 }} />
            <span className="text-xs font-semibold tracking-wide" style={{ color: 'var(--sm-accent-indigo-light)' }}>
              {available} AI models online · {providers.length} providers active
            </span>
          </div>

          <h1 className="font-display sm-animate-slide-up text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl lg:text-6xl">
            <span className="sm-gradient-text">Strategic Intelligence</span>
            <br />
            <span style={{ color: 'var(--sm-text-primary)' }}>Operating System</span>
          </h1>

          <p className="sm-animate-fade-in mx-auto mt-6 max-w-2xl text-base leading-8 sm:text-lg"
             style={{ color: 'var(--sm-text-secondary)', animationDelay: '0.15s' }}>
            Deploy multi-agent reasoning models, orchestrate strategic simulations,
            and synthesize tactical insights — within a secure cognitive matrix.
          </p>

          <div className="sm-animate-fade-in mt-8 flex flex-wrap items-center justify-center gap-4"
               style={{ animationDelay: '0.25s' }}>
            <button
              onClick={() => onCreateSession("ai_vs_human")}
              className="sm-btn sm-btn-primary sm-animated-border"
              style={{ padding: '14px 32px', fontSize: '0.95rem', borderRadius: '14px' }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M9 2v14M2 9h14" />
              </svg>
              Initialize Strategic Session
            </button>
            <button
              onClick={() => onCreateSession("ai_vs_ai")}
              className="sm-btn sm-btn-secondary"
              style={{ padding: '14px 28px', fontSize: '0.95rem', borderRadius: '14px' }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                <circle cx="6" cy="6" r="3" /><circle cx="12" cy="12" r="3" />
                <path d="M8.5 8.5l1 1" />
              </svg>
              Launch Strategic Simulation
            </button>
          </div>
        </div>

        {/* ── Bento Grid ── */}
        <div className="sm-stagger relative z-10 mx-auto max-w-6xl space-y-5 px-6 pb-12">

          {/* Row 1: Mode Cards */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="sm-glass-card p-6 cursor-pointer" onClick={() => onCreateSession("ai_vs_human")}>
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl"
                     style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.15))' }}>
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={{ color: 'var(--sm-accent-indigo-light)' }}>
                    <circle cx="10" cy="6" r="3.5" /><path d="M3 18c0-3.9 3.1-7 7-7s7 3.1 7 7" />
                  </svg>
                </div>
                <span className="sm-badge sm-badge-indigo">Optimized</span>
              </div>
              <h3 className="font-display text-lg font-bold" style={{ color: 'var(--sm-text-primary)' }}>
                Human Strategy Mode
              </h3>
              <p className="mt-2 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)' }}>
                Engage in synchronized reasoning with adaptive AI, receive strategic evaluations,
                and optimize your tactical pathways.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {["Logic Testing", "Cognitive Profiling", "Synapse Feedback"].map((t) => (
                  <span key={t} className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider"
                        style={{ background: 'rgba(99,102,241,0.08)', color: 'var(--sm-accent-indigo-light)' }}>{t}</span>
                ))}
              </div>
            </div>

            <div className="sm-glass-card p-6 cursor-pointer" onClick={() => onCreateSession("ai_vs_ai")}>
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl"
                     style={{ background: 'linear-gradient(135deg, rgba(6,182,212,0.2), rgba(59,130,246,0.15))' }}>
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={{ color: 'var(--sm-accent-cyan-light)' }}>
                    <path d="M4 4h5v5H4zM11 11h5v5h-5z" /><path d="M9 6.5h2M11 13.5h-2" strokeDasharray="2 2" />
                  </svg>
                </div>
                <span className="sm-badge sm-badge-cyan">Inference Node</span>
              </div>
              <h3 className="font-display text-lg font-bold" style={{ color: 'var(--sm-text-primary)' }}>
                Multi-Agent Simulation
              </h3>
              <p className="mt-2 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)' }}>
                Monitor Alpha and Beta AI clusters synthesizing complex queries,
                parsing signal from noise, and rendering logic models.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {["Multi-Agent", "Deep Analytics", "Evidence Tracking"].map((t) => (
                  <span key={t} className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider"
                        style={{ background: 'rgba(6,182,212,0.08)', color: 'var(--sm-accent-cyan-light)' }}>{t}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Row 2: Stats + Providers */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="sm-glass-card flex flex-col items-center justify-center p-6 text-center">
              <p className="font-display text-4xl font-extrabold sm-gradient-text">{available}</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>Verified Models</p>
            </div>
            <div className="sm-glass-card flex flex-col items-center justify-center p-6 text-center">
              <p className="font-display text-4xl font-extrabold sm-gradient-text">{providers.length}</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>Active Providers</p>
            </div>
            <div className="sm-glass-card flex flex-col items-center justify-center p-6 text-center">
              <p className="font-display text-4xl font-extrabold sm-gradient-text">∞</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>Queries Resolved</p>
            </div>
          </div>

          {/* Row 3: Inference Engines */}
          <div className="sm-glass-card p-6">
            <div className="mb-4 flex items-center gap-3">
              <h3 className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>
                Active Neural Clusters
              </h3>
              <div className="h-px flex-1" style={{ background: 'var(--sm-border)' }} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {providers.length === 0 ? (
                <p className="col-span-full text-sm" style={{ color: 'var(--sm-text-muted)' }}>
                  No engines online. Add an API key in .env and restart.
                </p>
              ) : (
                providers.map((provider) => (
                  <div
                    key={provider.provider}
                    className="group flex items-center gap-3 rounded-xl p-3 transition-all duration-300"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--sm-border)' }}
                  >
                    <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                         style={{ background: 'rgba(99,102,241,0.08)' }}>
                      <div className="h-2 w-2 rounded-full"
                           style={{ background: '#22c55e', boxShadow: '0 0 8px rgba(34,197,94,0.6)' }} />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold" style={{ color: 'var(--sm-text-primary)' }}>
                        {provider.provider_label}
                      </p>
                      <p className="text-[11px]" style={{ color: 'var(--sm-text-tertiary)' }}>
                        {provider.unlocked_model_count} model{provider.unlocked_model_count !== 1 ? 's' : ''} online
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Row 4: Features Bento */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { icon: "🧠", title: "Feedback Loop", body: "Interaction feeds a real cognitive profile. Synapse responses adapt over time." },
              { icon: "👁", title: "Cognitive Map", body: "Inspect the system's long-term neural cache instead of hidden nodes." },
              { icon: "⚖️", title: "Logic Evaluation", body: "Signals, inference arrays, matrices — the inference engine models real data." },
              { icon: "📄", title: "Export Anywhere", body: "Markdown, JSON, and PDF. Sessions become shareable strategic reports." },
            ].map((f) => (
              <div key={f.title} className="sm-glass-card p-5">
                <span className="text-2xl">{f.icon}</span>
                <h4 className="mt-3 text-sm font-bold" style={{ color: 'var(--sm-text-primary)' }}>{f.title}</h4>
                <p className="mt-1.5 text-xs leading-5" style={{ color: 'var(--sm-text-tertiary)' }}>{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

function AiDebaterExperiencesPage({
  sessions,
  overview
}: {
  sessions: ChatSession[];
  overview: AgentExperienceOverview | null;
}) {
  const [copied, setCopied] = useState(false);
  const sessionNames = useMemo(
    () => Object.fromEntries(sessions.map((session) => [session.id, session.name])),
    [sessions]
  );
  const copySummary = async () => {
    if (!overview) {
      return;
    }
    const topAgents = overview.by_agent
      .slice(0, 5)
      .map((item) => `${formatAgentLabel(item.agent_id)} (${item.record_count})`)
      .join(", ");
    const text = [
      "Cognitive Cache",
      `Experience records: ${overview.summary.total_records}`,
      `Distinct agents: ${overview.summary.distinct_agents}`,
      `Universal records: ${overview.summary.universal_records}`,
      `Chat records: ${overview.summary.chat_records}`,
      `Top identities: ${topAgents || "None yet"}`
    ].join("\n");
    await safeCopy(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col" style={{ background: 'var(--sm-bg-primary)' }}>
      <section className="electron-drag p-6" style={{ borderBottom: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-accent-indigo-light)' }}>Global memory layer</p>
            <h1 className="font-display mt-1 text-3xl font-bold sm-gradient-text">Cognitive Cache</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7" style={{ color: 'var(--sm-text-secondary)' }}>
              Inspect what the neural nodes have stored over time.
              Factual records built from signal tracking, evidence arrays, inference evaluations, and feedback.
            </p>
          </div>
          <button
            type="button"
            onClick={() => copySummary().catch(() => undefined)}
            className="sm-btn sm-btn-secondary"
          >
            {copied ? "Copied" : "Copy Overview"}
          </button>
        </div>
      </section>

      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        {!overview ? (
          <LoadingPanel message="Loading cognitive cache matrix..." />
        ) : (
          <div className="mx-auto max-w-6xl space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Experience Records" value={String(overview.summary.total_records)} />
              <MetricCard label="Tracked Identities" value={String(overview.summary.distinct_agents)} />
              <MetricCard
                label="Universal / Chat"
                value={`${overview.summary.universal_records} / ${overview.summary.chat_records}`}
              />
              <MetricCard label="Total Reuses" value={String(overview.summary.total_uses)} />
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
              <Panel title="What the council is currently carrying forward">
                <p className="mb-3 text-sm leading-6 text-zinc-600">
                  The top rows below are the strongest active identity records by use count, confidence,
                  and recency. This is the memory that most visibly shapes future turns.
                </p>
                <div className="space-y-3">
                  {overview.experiences.length === 0 ? (
                    <p className="text-sm text-zinc-600">
                      No experience records exist yet. Finish a full strategy simulation or practice session first.
                    </p>
                  ) : (
                    overview.experiences.slice(0, 8).map((experience) => (
                      <div key={experience.id} className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-zinc-950">
                            {formatAgentLabel(experience.agent_id)}
                          </span>
                          <Tag>{experience.scope === "chat" ? "Chat-scoped" : "Universal"}</Tag>
                          <Tag>{formatAgentLabel(experience.lesson_type)}</Tag>
                          <Tag>{experience.confidence}</Tag>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-zinc-700">{experience.lesson}</p>
                        <p className="mt-2 text-xs text-zinc-500">
                          Uses: {experience.use_count} · Session:{" "}
                          {experience.session_id ? sessionNames[experience.session_id] || "Unknown Session" : "All chats"}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </Panel>

              <Panel title="Memory guardrails">
                <div className="space-y-3 text-sm leading-6 text-zinc-700">
                  <Callout
                    title="No fake personality"
                    body="Identity stays empty until the system has real recorded activity. The app avoids inventing strengths, weaknesses, or values out of thin air."
                  />
                  <Callout
                    title="Visible source trail"
                    body="Experience is backed by saved strategic objects such as claims, challenges, evidence, judge scorecards, and user feedback."
                  />
                  <Callout
                    title="Global by default"
                    body="Universal experience lets roles learn across chats, while chat-scoped lessons still stay local when a session needs its own behavior."
                  />
                </div>
              </Panel>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title="Identity load by agent">
                <div className="space-y-3">
                  {overview.by_agent.length === 0 ? (
                    <p className="text-sm text-zinc-600">No agent identities have been recorded yet.</p>
                  ) : (
                    overview.by_agent.map((item) => (
                      <div key={item.agent_id} className="rounded-md border border-zinc-200 bg-zinc-50 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-zinc-950">
                              {formatAgentLabel(item.agent_id)}
                            </p>
                            <p className="text-xs text-zinc-500">
                              {item.record_count} record(s) · {item.high_confidence_count} high confidence
                            </p>
                          </div>
                          <span className="text-sm font-semibold text-zinc-800">
                            {item.use_count} reuse(s)
                          </span>
                        </div>
                        <div className="mt-3">
                          <Bar value={item.record_count} max={Math.max(1, overview.by_agent[0]?.record_count || 1)} />
                        </div>
                        <p className="mt-2 text-xs text-zinc-500">
                          Most common lesson types: {Object.keys(item.lesson_types).slice(0, 3).map(formatAgentLabel).join(", ") || "None"}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </Panel>

              <Panel title="Lesson types in memory">
                <div className="space-y-3">
                  {Object.keys(overview.by_lesson_type).length === 0 ? (
                    <p className="text-sm text-zinc-600">No lesson types have been captured yet.</p>
                  ) : (
                    Object.entries(overview.by_lesson_type)
                      .sort((left, right) => right[1] - left[1])
                      .map(([type, count]) => (
                        <div key={type}>
                          <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                            <span className="font-medium text-zinc-900">{formatAgentLabel(type)}</span>
                            <span className="text-zinc-600">{count}</span>
                          </div>
                          <Bar value={count} max={Math.max(...Object.values(overview.by_lesson_type), 1)} />
                        </div>
                      ))
                  )}
                </div>
              </Panel>
            </div>

            <Panel title="Recent memory and review saves">
              <div className="space-y-3">
                {overview.memory_events.length === 0 ? (
                  <p className="text-sm text-zinc-600">
                    No memory-save, review, or scorecard records have been created yet.
                  </p>
                ) : (
                  overview.memory_events.map((record) => (
                    <div key={record.id} className="rounded-md border border-zinc-200 bg-white p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-zinc-950">{record.title}</span>
                        <Tag>{formatAgentLabel(record.record_type)}</Tag>
                        {record.role ? <Tag>{formatAgentLabel(record.role)}</Tag> : null}
                        {record.team ? <Tag>{record.team.toUpperCase()}</Tag> : null}
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">{record.content}</p>
                    </div>
                  ))
                )}
              </div>
            </Panel>
          </div>
        )}
      </section>
    </main>
  );
}

function UserDebateProfilePage({
  overview,
  onCreateSession
}: {
  overview: UserDebateProfileOverview | null;
  onCreateSession: (mode?: ChatSession["mode"]) => void;
}) {
  const [copied, setCopied] = useState(false);
  const copySummary = async () => {
    if (!overview) {
      return;
    }
    const profile = overview.profile;
    const text = [
      "Performance Matrix",
      `Strategy sessions completed: ${profile.practice_debates_completed}`,
      `Strengths: ${profile.strengths.join("; ") || "None yet"}`,
      `Improvement targets: ${profile.weaknesses.join("; ") || "None yet"}`,
      `Coach summary: ${overview.coach_summary}`
    ].join("\n");
    await safeCopy(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col" style={{ background: 'var(--sm-bg-primary)' }}>
      <section className="electron-drag p-6" style={{ borderBottom: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-accent-cyan-light)' }}>Global coaching layer</p>
            <h1 className="font-display mt-1 text-3xl font-bold sm-gradient-text">Performance Matrix</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7" style={{ color: 'var(--sm-text-secondary)' }}>
              Your long-term training dashboard. Tracks how your collaborative sessions have been evaluated,
              what the system keeps adapting to, and cognitive pathways to optimize.
            </p>
          </div>
          <button
            type="button"
            onClick={() => copySummary().catch(() => undefined)}
            className="sm-btn sm-btn-secondary"
          >
            {copied ? "Copied" : "Copy Training Snapshot"}
          </button>
        </div>
      </section>

      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        {!overview ? (
          <LoadingPanel message="Loading performance matrix..." />
        ) : (
          <div className="mx-auto max-w-6xl space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Neural Sessions"
                value={String(overview.profile.practice_debates_completed)}
              />
              <MetricCard
                label="Decided Verdicts"
                value={String((overview.profile.wins.pro || 0) + (overview.profile.wins.con || 0))}
              />
              <MetricCard
                label="Less Practiced Side"
                value={overview.less_practiced_side.toUpperCase()}
              />
              <MetricCard
                label="Last Updated"
                value={formatShortDate(overview.profile.last_updated_at)}
              />
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
              <Panel title="Coach summary">
                <p className="text-sm leading-7 text-zinc-700">{overview.coach_summary}</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-950">Recommended next drills</h3>
                    <ul className="mt-2 space-y-2 text-sm leading-6 text-zinc-700">
                      {overview.recommendations.map((item, index) => (
                        <li key={`${item}-${index}`} className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-950">Best next session setup</h3>
                    <div className="mt-2 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm leading-6 text-zinc-700">
                      <p>Mode: Human Strategy Alignment</p>
                      <p>Human side: {overview.less_practiced_side.toUpperCase()}</p>
                      <p>
                        Flow:{" "}
                        {overview.profile.practice_debates_completed < 3 ? "Free for fluency" : "Structured for deliberate reps"}
                      </p>
                      <p>
                        Focus:{" "}
                        {overview.profile.weaknesses.length > 0 ? "Target your latest weakness" : "Full Strategy Session"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onCreateSession("ai_vs_human")}
                      className="sm-btn sm-btn-primary mt-3"
                    >
                      Start Training Chat
                    </button>
                  </div>
                </div>
              </Panel>

              <Panel title="Performance snapshot">
                <div className="space-y-4">
                  <SnapshotRow
                    label="Won as Pro"
                    value={overview.profile.wins.pro || 0}
                    max={Math.max(1, overview.profile.practice_debates_completed)}
                  />
                  <SnapshotRow
                    label="Won as Con"
                    value={overview.profile.wins.con || 0}
                    max={Math.max(1, overview.profile.practice_debates_completed)}
                  />
                  <SnapshotRow
                    label="Unclear outcomes"
                    value={overview.profile.wins.unclear || 0}
                    max={Math.max(1, overview.profile.practice_debates_completed)}
                  />
                  <SnapshotRow
                    label="Auto side usage"
                    value={overview.profile.side_history.auto || 0}
                    max={Math.max(1, overview.profile.practice_debates_completed)}
                  />
                </div>
              </Panel>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title="Strengths">
                <BulletList
                  items={overview.profile.strengths}
                  emptyText="No confirmed strengths have been recorded yet. Finish a few strategy sessions first."
                />
              </Panel>
              <Panel title="Improvement targets">
                <BulletList
                  items={overview.profile.weaknesses}
                  emptyText="No recurring weaknesses have been recorded yet."
                />
              </Panel>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title="Style tags">
                {overview.profile.style_tags.length === 0 ? (
                  <p className="text-sm text-zinc-600">No style tags recorded yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {overview.profile.style_tags.map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel title="Trainer notes">
                <BulletList
                  items={overview.profile.trainer_notes}
                  emptyText="No trainer notes have been saved yet."
                />
              </Panel>
            </div>

            <Panel title="Recent practice history">
              {overview.recent_practice_debates.length === 0 ? (
                <p className="text-sm text-zinc-600">
                  No completed strategy sessions yet. Start one alignment chat and finish the session to populate this history.
                </p>
              ) : (
                <div className="space-y-3">
                  {overview.recent_practice_debates.map((debate) => (
                    <div key={debate.id} className="rounded-md border border-zinc-200 bg-white p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-zinc-950">{debate.name}</span>
                        <Tag>{debate.session_name}</Tag>
                        <Tag>{debate.winner.toUpperCase()}</Tag>
                        <Tag>{debate.human_side.toUpperCase()}</Tag>
                        <Tag>{debate.practice_flow}</Tag>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">{debate.topic}</p>
                      <p className="mt-2 text-xs text-zinc-500">
                        Finished {formatShortDate(debate.finished_at || debate.started_at)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        )}
      </section>
    </main>
  );
}

function LoadingPanel({ message }: { message: string }) {
  return (
    <section className="flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-4 p-6">
      <div className="sm-typing-indicator"><span /><span /><span /></div>
      <p className="text-sm" style={{ color: 'var(--sm-text-muted)' }}>{message}</p>
    </section>
  );
}

function ChoiceCard({
  eyebrow,
  title,
  description,
  bullets,
  cta,
  onClick
}: {
  eyebrow: string;
  title: string;
  description: string;
  bullets: string[];
  cta: string;
  onClick: () => void;
}) {
  return (
    <div className="sm-card sm-gradient-border overflow-hidden p-5 transition-all duration-300 hover:scale-[1.02]" style={{ borderRadius: 'var(--sm-radius-lg)' }}>
      <p className="text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-accent-indigo-light)' }}>{eyebrow}</p>
      <h3 className="font-display mt-2 text-lg font-bold" style={{ color: 'var(--sm-text-primary)' }}>{title}</h3>
      <p className="mt-2 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)' }}>{description}</p>
      <ul className="mt-3 space-y-2 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)' }}>
        {bullets.map((bullet) => (
          <li key={bullet} className="flex items-start gap-2"><span style={{ color: 'var(--sm-accent-cyan)' }}>▸</span> {bullet}</li>
        ))}
      </ul>
      <button type="button" onClick={onClick} className="sm-btn sm-btn-primary mt-4">{cta}</button>
    </div>
  );
}

function Callout({ title, body }: { title: string; body: string }) {
  return (
    <div className="sm-card p-4" style={{ borderRadius: 'var(--sm-radius-md)' }}>
      <p className="text-sm font-bold" style={{ color: 'var(--sm-text-primary)' }}>{title}</p>
      <p className="mt-1 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)' }}>{body}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="sm-card p-5" style={{ borderRadius: 'var(--sm-radius-lg)' }}>
      <h2 className="font-display text-lg font-bold" style={{ color: 'var(--sm-text-primary)' }}>{title}</h2>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="sm-card sm-gradient-border p-4" style={{ borderRadius: 'var(--sm-radius-lg)' }}>
      <p className="text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-text-muted)' }}>{label}</p>
      <p className="font-display mt-2 text-2xl font-bold sm-gradient-text">{value}</p>
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="sm-badge">
      {children}
    </span>
  );
}

function Bar({ value, max }: { value: number; max: number }) {
  const width =
    value <= 0
      ? "0%"
      : `${Math.max(4, Math.round((Math.max(0, value) / Math.max(1, max)) * 100))}%`;
  return (
    <div className="sm-progress-track">
      <div className="sm-progress-fill" style={{ width }} />
    </div>
  );
}

function SnapshotRow({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-sm">
        <span className="font-medium" style={{ color: 'var(--sm-text-primary)' }}>{label}</span>
        <span style={{ color: 'var(--sm-text-tertiary)' }}>{value}</span>
      </div>
      <Bar value={value} max={max} />
    </div>
  );
}

function BulletList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (items.length === 0) {
    return <p className="text-sm" style={{ color: 'var(--sm-text-muted)' }}>{emptyText}</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="sm-card px-3 py-2 text-sm leading-6" style={{ color: 'var(--sm-text-secondary)', borderRadius: 'var(--sm-radius-md)' }}>
          {item}
        </li>
      ))}
    </ul>
  );
}

function formatAgentLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatShortDate(value: string) {
  if (!value) {
    return "Not yet";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

async function safeCopy(text: string) {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch { /* clipboard API can throw in insecure contexts */ }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}
