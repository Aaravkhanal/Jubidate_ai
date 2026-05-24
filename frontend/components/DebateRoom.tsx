"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useVoiceSettings, useVoiceSynthesis, useSpeechRecognition } from "@/hooks/useVoice";
import { DebateContainer } from "./chat/DebateContainer";
import { LiveModelSwap } from "./orchestration/LiveModelSwap";
import { CognitiveMatrixPanel } from "./orchestration/CognitiveMatrixPanel";
import { AlphaClusterPanel } from "./orchestration/AlphaClusterPanel";
import { BetaClusterPanel } from "./orchestration/BetaClusterPanel";

import type {
  AgentExperienceRecord,
  ChatSession,
  CouncilSettings,
  CostSummary,
  DebateAnalytics,
  DebateAssignment,
  DebateIntelligence,
  DebateIntelligenceRecord,
  DebateMessage,
  DebateRecord,
  ModelsResponse,
  PracticeState,
  SessionSettings,
  SupportedModel
} from "@/types";

export type RoomPanel = "chat" | "stats" | "proRoom" | "conRoom" | "settings";

type DebateRoomProps = {
  selectedSession: ChatSession | null;
  messages: DebateMessage[];
  partialMessages: Record<string, DebateMessage>;
  models: ModelsResponse | null;
  topic: string;
  status: string;
  error: string | null;
  assignments: DebateAssignment[];
  currentRound?: number;
  totalRounds?: number;
  activeSpeaker?: string;
  streamingStatus?: string;
  debates: DebateRecord[];
  selectedDebateId: string;
  analytics: DebateAnalytics | null;
  realtimeAnalytics: any | null;
  analyticsHistory: DebateAnalytics[];
  intelligence: DebateIntelligence | null;
  practiceState: PracticeState | null;
  isTeamPreparing: boolean;
  showCouncilSettings: boolean;
  councilSettings: CouncilSettings | null;
  settings: SessionSettings | null;
  isRunning: boolean;
  selectedModelName: string;
  activePanel: RoomPanel;
  renamingSessionId: string | null;
  onPanelChange: (panel: RoomPanel) => void;
  onTopicChange: (topic: string) => void;
  onModelChange: (modelName: string) => void;
  onDebateChange: (debateId: string) => void;
  onSend: () => void;
  onEndPractice: () => void;
  onSettingsChange: (updates: Partial<SessionSettings>) => void;
  onCouncilSettingsChange: (updates: Partial<CouncilSettings>) => void;
  onResetUniversalIdentities: (confirmation: string) => Promise<{ deleted: number }>;
  onResetUserDebateProfile: (confirmation: string) => Promise<unknown>;
  onFeedbackSubmit: (questionKey: string, answer: string) => Promise<void>;
  onVerdictReview: (
    action: "challenge" | "override",
    winner: "pro" | "con" | "unclear",
    note: string
  ) => Promise<void>;
  onRename: (session: ChatSession, name: string) => Promise<boolean>;
  onRenameDebate: (debate: DebateRecord, name: string) => Promise<boolean>;
  onDeleteRequest: (session: ChatSession) => void;
  onDeleteDebateRequest: (session: ChatSession, debate: DebateRecord) => void;
  onClearRequest: (session: ChatSession, mode: "history" | "memory") => void;
  onNewDebate: () => void;
  onLiveModelSwap?: (role: "ai_a" | "ai_b" | "judge", model: string) => Promise<boolean>;
};

const roleStyles: Record<string, string> = {
  user: "sm-role-user",
  assistant: "sm-role-assistant",
  advocate: "sm-role-advocate",
  critic: "sm-role-critic",
  researcher: "sm-role-researcher",
  devils_advocate: "sm-role-devils_advocate",
  pro_lead_advocate: "sm-role-pro_lead_advocate",
  pro_rebuttal_critic: "sm-role-pro_rebuttal_critic",
  pro_evidence_researcher: "sm-role-pro_evidence_researcher",
  pro_cross_examiner: "sm-role-pro_cross_examiner",
  con_lead_advocate: "sm-role-con_lead_advocate",
  con_rebuttal_critic: "sm-role-con_rebuttal_critic",
  con_evidence_researcher: "sm-role-con_evidence_researcher",
  con_cross_examiner: "sm-role-con_cross_examiner",
  judge_assistant: "sm-role-judge_assistant",
  judge_panelist: "sm-role-judge_panelist",
  judge: "sm-role-judge",
  practice_user: "sm-role-practice_user",
  practice_debater: "sm-role-practice_debater",
  debate_trainer: "sm-role-debate_trainer"
};

const panels: Array<{ id: RoomPanel; label: string }> = [
  { id: "chat", label: "Intelligence Stream" },
  { id: "stats", label: "Cognitive Matrix" },
  { id: "proRoom", label: "Alpha Cluster" },
  { id: "conRoom", label: "Beta Cluster" },
  { id: "settings", label: "Command Center" }
];

const costCurrencies = ["USD", "CNY", "HKD", "EUR", "JPY", "GBP", "AUD", "CAD", "SGD"];
const USER_INPUT_WARN_CHARS = 5000;
const USER_INPUT_MAX_CHARS = 5500;

const teamRoleSettings = [
  {
    key: "lead_advocate",
    label: "Advocate",
    minDebaters: 1,
    description: "Builds the main case for each team."
  },
  {
    key: "rebuttal_critic",
    label: "Rebuttal Critic",
    minDebaters: 2,
    description: "Attacks the other team's strongest claims."
  },
  {
    key: "evidence_researcher",
    label: "Evidence Researcher",
    minDebaters: 3,
    description: "Adds evidence, context, and uncertainty notes."
  },
  {
    key: "cross_examiner",
    label: "Cross-Examiner",
    minDebaters: 4,
    description: "Asks pressure questions and exposes contradictions."
  }
];

const neutralRoleSettings = [
  {
    key: "judge_assistant",
    label: "Judge Assistant",
    description: "Audits missed points and statistics before the verdict."
  },
  {
    key: "judge",
    label: "Judge",
    description: "Makes the final decision."
  }
];

export function DebateRoom({
  selectedSession,
  messages,
  partialMessages,
  models,
  topic,
  status,
  error,
  assignments,
  currentRound = 0,
  totalRounds = 0,
  activeSpeaker = "",
  streamingStatus = "",
  debates,
  selectedDebateId,
  analytics,
  realtimeAnalytics,
  analyticsHistory,
  intelligence,
  practiceState,
  isTeamPreparing,
  showCouncilSettings,
  councilSettings,
  settings,
  isRunning,
  selectedModelName,
  activePanel,
  renamingSessionId,
  onPanelChange,
  onTopicChange,
  onModelChange,
  onDebateChange,
  onSend,
  onEndPractice,
  onSettingsChange,
  onCouncilSettingsChange,
  onResetUniversalIdentities,
  onResetUserDebateProfile,
  onFeedbackSubmit,
  onVerdictReview,
  onRename,
  onRenameDebate,
  onDeleteRequest,
  onDeleteDebateRequest,
  onClearRequest,
  onNewDebate,
  onLiveModelSwap
}: DebateRoomProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const partialList = Object.values(partialMessages);
  const unlockedModels = models?.models ?? [];
  const canSend =
    Boolean(selectedSession) &&
    Boolean(selectedModelName) &&
    topic.trim().length > 0 &&
    topic.length <= USER_INPUT_MAX_CHARS &&
    !isRunning &&
    unlockedModels.length > 0;

  const partialsHash = partialList.map((m) => m.content.length).join(",");

  useEffect(() => {
    if (settings?.auto_scroll && activePanel === "chat") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, partialsHash, settings?.auto_scroll, activePanel]);

  if (showCouncilSettings) {
    return (
      <main className="flex h-full min-w-0 flex-1 flex-col" style={{ background: 'var(--sm-bg-primary)' }}>
        <section className="electron-drag p-4" style={{ borderBottom: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
          <p className="text-xs font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-accent-indigo-light)' }}>System configuration</p>
          <h2 className="font-display text-2xl font-bold" style={{ color: 'var(--sm-text-primary)' }}>System Settings</h2>
          <p className="mt-1 text-sm" style={{ color: 'var(--sm-text-secondary)' }}>Universal behavior, long-term experience, identity memory, and reset controls.</p>
        </section>
        <CouncilSettingsPanel
          settings={councilSettings}
          onChange={onCouncilSettingsChange}
          onResetUniversalIdentities={onResetUniversalIdentities}
          onResetUserDebateProfile={onResetUserDebateProfile}
        />
      </main>
    );
  }

  if (!selectedSession) {
    return (
      <main className="flex h-full min-w-0 flex-1 items-center justify-center p-6" style={{ background: 'var(--sm-bg-primary)' }}>
        <p className="max-w-md text-center text-xl font-semibold" style={{ color: 'var(--sm-text-secondary)' }}>
          Create a session to begin.
        </p>
      </main>
    );
  }

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col" style={{ background: 'var(--sm-bg-primary)' }}>
      <section className="electron-drag p-4" style={{ borderBottom: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--sm-accent-indigo-light)' }}>
                {selectedSession.mode === "ai_vs_human" ? "Neural Orchestration" : "Matrix Synthesis"}
              </p>
              <span className="sm-badge sm-badge-indigo">
                {selectedSession.mode === "ai_vs_human" ? "Human-AI Alignment" : "Autonomous Array"}
              </span>
              {selectedSession.mode === "ai_vs_human" && practiceState?.active ? (
                <span className="sm-badge sm-badge-pro">
                  You: {(practiceState.human_side || "").toUpperCase()} · Cognitive Opponent: {(practiceState.ai_side || "").toUpperCase()}
                </span>
              ) : null}
              {selectedSession.mode === "ai_vs_human" &&
              practiceState?.active &&
              practiceState.practice_flow === "Structured" ? (
                <span className="sm-badge">
                  {practiceState.rounds_left ?? 0} round(s) left
                </span>
              ) : null}
            </div>
            <h2 className="font-display truncate text-2xl font-bold" style={{ color: 'var(--sm-text-primary)' }}>
              {selectedSession?.name ?? "No session selected"}
            </h2>
            <p className="mt-1 text-sm" style={{ color: 'var(--sm-text-tertiary)' }}>{status}</p>
          </div>

          <div className="flex flex-col gap-3 lg:items-end">
            {selectedSession.mode === "ai_vs_human" && practiceState?.active ? (
              <button
                type="button"
                onClick={onEndPractice}
                disabled={isRunning}
                className="sm-btn sm-btn-danger"
              >
                Terminate Session
              </button>
            ) : null}
            <ProviderReadiness models={models} />
          </div>
        </div>
      </section>

      {((selectedSession.mode === "ai_vs_ai" && isRunning) || (selectedSession.mode === "ai_vs_human" && practiceState?.active)) && (
        <div 
          className="px-4 py-3 flex flex-col gap-2 transition-all duration-300 border-b"
          style={{ 
            borderColor: 'var(--sm-border)',
            background: 'linear-gradient(90deg, rgba(99,102,241,0.04), rgba(6,182,212,0.02))'
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <div className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
              </div>
              <span className="text-xs font-bold tracking-wider uppercase" style={{ color: 'var(--sm-text-secondary)' }}>
                {(selectedSession.mode === "ai_vs_ai" || (selectedSession.mode === "ai_vs_human" && practiceState?.practice_flow === "Structured")) 
                  ? `Round ${
                      selectedSession.mode === "ai_vs_human" 
                        ? (settings?.practice_settings?.structured_rounds || 6) - (practiceState?.rounds_left ?? 0) + 1 
                        : currentRound || 0
                    } of ${
                      selectedSession.mode === "ai_vs_human" 
                        ? (settings?.practice_settings?.structured_rounds || 6) 
                        : totalRounds || 0
                    }` 
                  : "Free Debate Session"
                }
              </span>
              {activeSpeaker && (
                <>
                  <span style={{ color: 'var(--sm-text-tertiary)' }}>•</span>
                  <span className="text-xs font-bold text-cyan-400">
                    Active Speaker: {activeSpeaker}
                  </span>
                </>
              )}
            </div>
            
            <div className="flex items-center gap-3">
              {streamingStatus && (
                <span className="text-[11px] font-medium italic" style={{ color: 'var(--sm-text-tertiary)' }}>
                  {streamingStatus}
                </span>
              )}
            </div>
          </div>
          
          {(selectedSession.mode === "ai_vs_ai" || (selectedSession.mode === "ai_vs_human" && practiceState?.practice_flow === "Structured")) && (
            <div className="w-full rounded-full h-1.5 overflow-hidden" style={{ background: 'rgba(255,255,255,0.05)' }}>
              <div 
                className="bg-gradient-to-r from-indigo-500 to-cyan-500 h-1.5 rounded-full transition-all duration-500 ease-out" 
                style={{ 
                  width: `${
                    Math.min(100, Math.max(0, (
                      (selectedSession.mode === "ai_vs_human" 
                        ? (settings?.practice_settings?.structured_rounds || 6) - (practiceState?.rounds_left ?? 0) + 1 
                        : currentRound || 0
                      ) / (
                        selectedSession.mode === "ai_vs_human" 
                          ? (settings?.practice_settings?.structured_rounds || 6) 
                          : totalRounds || 0
                      )
                    ) * 100))
                  }%` 
                }}
              />
            </div>
          )}
        </div>
      )}

      <div className="min-h-0 flex flex-1">
        <aside
          className="group hidden w-12 hover:w-44 shrink-0 overflow-hidden lg:block transition-all duration-300 ease-in-out"
          style={{ borderRight: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}
        >
          <div className="flex flex-col gap-1 p-2 pt-3">
            {panels.map((panel) => {
              const panelIcons: Record<string, React.ReactElement> = {
                chat: <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M3 3h12a1 1 0 011 1v7a1 1 0 01-1 1H6l-4 3V4a1 1 0 011-1z"/></svg>,
                stats: <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><line x1="4" y1="16" x2="4" y2="10"/><line x1="9" y1="16" x2="9" y2="4"/><line x1="14" y1="16" x2="14" y2="7"/></svg>,
                proRoom: <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="9" cy="6" r="3"/><path d="M3 16c0-3.3 2.7-6 6-6s6 2.7 6 6"/></svg>,
                conRoom: <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="9" cy="6" r="3"/><path d="M3 16c0-3.3 2.7-6 6-6s6 2.7 6 6"/><line x1="6" y1="6" x2="12" y2="6"/></svg>,
                settings: <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="9" cy="9" r="2.5"/><path d="M9 2v2M9 14v2M2 9h2M14 9h2M3.9 3.9l1.4 1.4M12.7 12.7l1.4 1.4M3.9 14.1l1.4-1.4M12.7 5.3l1.4-1.4"/></svg>,
              };
              const isActive = activePanel === panel.id;
              return (
                <button
                  key={panel.id}
                  type="button"
                  title={panel.label}
                  onClick={() => onPanelChange(panel.id)}
                  className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left text-sm font-semibold transition-all duration-200 whitespace-nowrap overflow-hidden"
                  style={{
                    background: isActive ? 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(6,182,212,0.08))' : 'transparent',
                    color: isActive ? 'var(--sm-accent-indigo-light)' : 'var(--sm-text-secondary)',
                    border: isActive ? '1px solid var(--sm-border-accent)' : '1px solid transparent',
                    minWidth: 0,
                  }}
                >
                  <span className="shrink-0">{panelIcons[panel.id]}</span>
                  <span className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">{panel.label}</span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col">
          <div className="p-2 lg:hidden" style={{ borderBottom: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {panels.map((panel) => (
                <button
                  key={panel.id}
                  type="button"
                  onClick={() => onPanelChange(panel.id)}
                  className={`rounded-xl px-2 py-2 text-xs font-semibold transition-all duration-200 ${
                    activePanel === panel.id
                      ? ""
                      : ""
                  }`}
                  style={{
                    background: activePanel === panel.id
                      ? 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(6,182,212,0.08))'
                      : 'var(--sm-bg-glass)',
                    color: activePanel === panel.id ? 'var(--sm-accent-indigo-light)' : 'var(--sm-text-secondary)',
                    border: activePanel === panel.id ? '1px solid var(--sm-border-accent)' : '1px solid var(--sm-border)'
                  }}
                >
                  {panel.label}
                </button>
              ))}
            </div>
          </div>

          {activePanel === "chat" ? (
            <>
              <section className="min-h-0 flex-1 overflow-y-auto p-4">
                {isTeamPreparing ? <TeamPreparationNotice /> : null}
                {selectedSession.ai_a_model || assignments.length > 0 ? <AssignmentStrip session={selectedSession} assignments={assignments} /> : null}
                {messages.length === 0 && partialList.length === 0 ? (
                  <div className="mx-auto flex h-full max-w-2xl flex-col justify-center text-center">
                    <p className="font-display text-2xl font-bold sm-gradient-text">
                      {selectedSession.mode === "ai_vs_human"
                        ? "Initialize the intelligence stream."
                        : "Initialize cognitive query matrix."}
                    </p>
                    <p className="mt-2" style={{ color: 'var(--sm-text-secondary)' }}>
                      {selectedSession.mode === "ai_vs_human"
                        ? "Select reasoning path, then synchronize with the cognitive opponent."
                        : "Input query parameters to engage the autonomous reasoning clusters."}
                    </p>
                  </div>
                ) : (
                  <DebateContainer
                    messages={messages}
                    partialMessages={partialMessages}
                    settings={settings}
                  />
                )}
              </section>

              <Composer
                models={models}
                topic={topic}
                sessionMode={selectedSession.mode}
                practiceState={practiceState}
                selectedModelName={selectedModelName}
                isRunning={isRunning}
                canSend={canSend}
                error={error}
                hasMessages={messages.length > 0}
                onTopicChange={onTopicChange}
                onModelChange={onModelChange}
                onSend={onSend}
                onNewDebate={onNewDebate}
                isRESTSession={Boolean(selectedSession?.ai_a_model)}
                selectedSession={selectedSession}
                onLiveModelSwap={onLiveModelSwap}
              />
            </>
          ) : null}

          {activePanel === "stats" ? (
            <StatsPanel
              analytics={analytics}
              realtimeAnalytics={realtimeAnalytics}
              sessionMode={selectedSession?.mode}
              history={analyticsHistory}
              debates={debates}
              selectedDebateId={selectedDebateId}
              onDebateChange={onDebateChange}
              intelligence={intelligence}
              settings={settings}
              onFeedbackSubmit={onFeedbackSubmit}
              onVerdictReview={onVerdictReview}
            />
          ) : null}

          {activePanel === "proRoom" ? (
            <TeamRoomPanel intelligence={intelligence} team="pro" />
          ) : null}

          {activePanel === "conRoom" ? (
            <TeamRoomPanel intelligence={intelligence} team="con" />
          ) : null}

          {activePanel === "settings" ? (
            <SettingsPanel
              key={selectedSession?.id ?? "no-session"}
              session={selectedSession}
              settings={settings}
              practiceState={practiceState}
              models={models}
              messages={messages}
              analytics={analytics}
              intelligence={intelligence}
              selectedDebateId={selectedDebateId}
              selectedModelName={selectedModelName}
              isRenaming={renamingSessionId === selectedSession?.id}
              isRunning={isRunning}
              debates={debates}
              onModelChange={onModelChange}
              onSettingsChange={onSettingsChange}
              onRename={onRename}
              onRenameDebate={onRenameDebate}
              onDeleteRequest={onDeleteRequest}
              onDeleteDebateRequest={onDeleteDebateRequest}
              onClearRequest={onClearRequest}
            />
          ) : null}
        </section>
      </div>
    </main>
  );
}

function ProviderIcon({ providerName }: { providerName: string }) {
  const name = providerName.toLowerCase();
  if (name.includes("google")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-blue-400">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
      </svg>
    );
  }
  if (name.includes("groq")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-orange-500">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }
  if (name.includes("fireworks")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-pink-500">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }
  if (name.includes("openrouter")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-purple-400">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
        <path d="M12 8v8M8 12h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    );
  }
  if (name.includes("minimax")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-cyan-400">
        <path d="M4 4h16v16H4V4z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-slate-400">
      <path d="M12 2L2 22h20L12 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function ProviderReadiness({ models }: { models: ModelsResponse | null }) {
  return (
    <div className="flex flex-wrap gap-3 lg:w-[540px] justify-end">
      {models?.providers.map((provider) => (
        <div
          key={provider.provider}
          className={`group relative flex flex-col justify-between overflow-hidden rounded-xl border backdrop-blur-md p-3.5 transition-all duration-300 w-full sm:w-[calc(50%-6px)] ${
            provider.configured
              ? "bg-white/5 border-cyan-500/20 hover:border-cyan-400/40 hover:bg-cyan-900/10 hover:shadow-[0_0_20px_rgba(6,182,212,0.15)]"
              : "bg-black/20 border-white/5 hover:border-white/10 opacity-70"
          }`}
        >
          {provider.configured && (
             <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-cyan-500/10 pointer-events-none opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
          )}
          
          <div className="relative z-10 flex items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-2">
              <ProviderIcon providerName={provider.provider_label} />
              <span className="font-display text-[13px] font-bold tracking-wide text-white">
                {provider.provider_label}
              </span>
            </div>
            
            <div className="flex items-center gap-2">
              {provider.configured && (
                 <span className="flex items-center gap-1">
                   <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 sm-animate-pulse-glow" />
                 </span>
              )}
              <span
                className={`rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest transition-colors ${
                  provider.configured
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                    : provider.status_label === "Unavailable"
                      ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                      : "bg-slate-500/20 text-slate-400 border border-slate-500/30"
                }`}
              >
                {provider.status_label ?? (provider.configured ? `READY` : "LOCKED")}
              </span>
            </div>
          </div>
          
          <div className="relative z-10 pl-6 flex justify-between items-center">
            <p className="text-[10px] text-slate-400 tracking-wider">
               {provider.configured ? `${provider.unlocked_model_count} STRATEGY NODES` : provider.api_key_env}
            </p>
          </div>
          
          {provider.status_reason && provider.status_label === "Unavailable" ? (
            <p className="relative z-10 mt-2 text-[10px] leading-relaxed text-amber-300/80 pl-6">
              {provider.status_reason}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function AssignmentStrip({ 
  session, 
  assignments 
}: { 
  session: ChatSession | null; 
  assignments: DebateAssignment[] 
}) {
  const isRESTSession = Boolean(session?.ai_a_model);
  
  if (isRESTSession && session) {
    const isPractice = session.mode === "ai_vs_human";
    return (
      <div className="mx-auto mb-6 grid max-w-4xl gap-3 grid-cols-1 sm:grid-cols-3">
        {/* Card 1: Pro */}
        <div 
          className="sm-card p-4 transition-all duration-300 relative overflow-hidden" 
          style={{ 
            borderRadius: 'var(--sm-radius-md)',
            border: '1px solid rgba(99,102,241,0.2)',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.05), transparent)'
          }}
        >
          <span className="text-[10px] font-bold tracking-widest uppercase text-indigo-400 block mb-1">PRO TEAM</span>
          <p className="text-sm font-bold" style={{ color: 'var(--sm-text-primary)' }}>
            {isPractice ? "Human Operator" : "AI Debater A (Pro)"}
          </p>
          <p className="mt-1.5 truncate text-[11px]" style={{ color: 'var(--sm-text-tertiary)' }} title={isPractice ? "Human Stance" : session.ai_a_model}>
            {isPractice ? "Operator Node" : session.ai_a_model}
          </p>
        </div>

        {/* Card 2: Con */}
        <div 
          className="sm-card p-4 transition-all duration-300 relative overflow-hidden" 
          style={{ 
            borderRadius: 'var(--sm-radius-md)',
            border: '1px solid rgba(6,182,212,0.2)',
            background: 'linear-gradient(135deg, rgba(6,182,212,0.05), transparent)'
          }}
        >
          <span className="text-[10px] font-bold tracking-widest uppercase text-cyan-400 block mb-1">CON TEAM</span>
          <p className="text-sm font-bold" style={{ color: 'var(--sm-text-primary)' }}>
            {isPractice ? "AI Opponent" : "AI Debater B (Con)"}
          </p>
          <p className="mt-1.5 truncate text-[11px]" style={{ color: 'var(--sm-text-tertiary)' }} title={isPractice ? session.ai_a_model : session.ai_b_model}>
            {isPractice ? session.ai_a_model : session.ai_b_model}
          </p>
        </div>

        {/* Card 3: Judge */}
        <div 
          className="sm-card p-4 transition-all duration-300 relative overflow-hidden" 
          style={{ 
            borderRadius: 'var(--sm-radius-md)',
            border: '1px solid rgba(245,158,11,0.3)',
            background: 'linear-gradient(135deg, rgba(245,158,11,0.06), transparent)'
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold tracking-widest uppercase block" style={{ color: 'var(--sm-accent-amber-light)' }}>JUDGE</span>
            <span className="rounded-md px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-widest bg-amber-500/20 text-amber-400 border border-amber-500/30">
              STANDBY
            </span>
          </div>
          <p className="text-sm font-bold mt-1" style={{ color: 'var(--sm-text-primary)' }}>
            Independent Adjudicator
          </p>
          <p className="mt-1.5 truncate text-[11px]" style={{ color: 'var(--sm-text-tertiary)' }} title={session.judge_model}>
            {session.judge_model}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto mb-4 grid max-w-4xl gap-2 sm:grid-cols-2 xl:grid-cols-5">
      {assignments.map((assignment) => (
        <div key={assignment.role} className="sm-card p-3" style={{ borderRadius: 'var(--sm-radius-md)' }}>
          <p className="text-sm font-semibold" style={{ color: 'var(--sm-text-primary)' }}>{assignment.speaker}</p>
          <p className="mt-1 truncate text-xs" style={{ color: 'var(--sm-text-tertiary)' }} title={assignment.model}>
            {assignment.model}
          </p>
        </div>
      ))}
    </div>
  );
}

function Composer({
  models,
  topic,
  sessionMode,
  practiceState,
  selectedModelName,
  isRunning,
  canSend,
  error,
  hasMessages = false,
  onTopicChange,
  onModelChange,
  onSend,
  onNewDebate,
  isRESTSession = false,
  selectedSession,
  onLiveModelSwap
}: {
  models: ModelsResponse | null;
  topic: string;
  sessionMode: ChatSession["mode"];
  practiceState: PracticeState | null;
  selectedModelName: string;
  isRunning: boolean;
  canSend: boolean;
  error: string | null;
  hasMessages?: boolean;
  onTopicChange: (topic: string) => void;
  onModelChange: (modelName: string) => void;
  onSend: () => void;
  onNewDebate: () => void;
  isRESTSession?: boolean;
  selectedSession: ChatSession | null;
  onLiveModelSwap?: (role: "ai_a" | "ai_b" | "judge", model: string) => Promise<boolean>;
}) {
  const unlockedModels = models?.models ?? [];
  const charCount = topic.length;
  const overHardLimit = charCount > USER_INPUT_MAX_CHARS;
  const nearLimit = charCount >= USER_INPUT_WARN_CHARS && !overHardLimit;
  const modelsByProvider = unlockedModels.reduce<Record<string, typeof unlockedModels>>(
    (groups, model) => {
      const provider = model.provider_label;
      groups[provider] = groups[provider] ?? [];
      groups[provider].push(model);
      return groups;
    },
    {}
  );
  const { settings: voiceSettings } = useVoiceSettings();
  const { isListening, startListening, stopListening, isSupported } = useSpeechRecognition(voiceSettings.provider);
  const [baseText, setBaseText] = useState("");

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      setBaseText(topic);
      startListening((text, isFinal) => {
        const newText = baseText ? baseText + " " + text : text;
        onTopicChange(newText);
        if (isFinal) {
          setBaseText(newText);
        }
      });
    }
  };

  const isPractice = sessionMode === "ai_vs_human";
  const messageLabel = isPractice
    ? practiceState?.active
      ? "Your Turn To Input Synaptic Response"
      : "Initialize Strategic Reasoning"
    : "Strategic Objective";
  const placeholder = isPractice
    ? practiceState?.active
      ? "Synchronize strategic agents or defend your logic node..."
      : "Define your intelligence objective..."
    : "Define your intelligence objective or prompt the clusters for analysis...";

  return (
    <section className="p-4" style={{ borderTop: '1px solid var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
      <div className="mx-auto max-w-4xl">
        {error ? (
          <div className="mb-4 flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/5 p-4 relative overflow-hidden">
            <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(244,63,94,0.02)_50%,transparent_75%,transparent_100%)] bg-[length:20px_20px] animate-[slide_1s_linear_infinite]" />
            <div className="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-500/20 text-red-400">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            </div>
            <div className="relative z-10">
              <h4 className="text-sm font-bold text-red-400">System Desynchronization</h4>
              <p className="mt-1 text-xs text-red-300/80 leading-relaxed">
                {error.includes("empty response") || error.includes("kimi-fw") 
                  ? "Strategic node failed to synchronize. The inference engine returned an incomplete stream. Reinitializing is recommended."
                  : error}
              </p>
            </div>
          </div>
        ) : null}
        {models?.availability_notice ? (
          <p className="mb-3 rounded-xl px-3 py-2 text-sm" style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)', color: 'var(--sm-accent-amber-light)' }}>
            {models.availability_notice}
          </p>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-[auto_minmax(0,1fr)] xl:items-start">
          {isRESTSession ? (
            <div className="w-full xl:w-[320px] shrink-0">
              {onLiveModelSwap && (
                <LiveModelSwap
                  mode={selectedSession?.mode as any}
                  aiA={selectedSession?.ai_a_model || ""}
                  aiB={selectedSession?.ai_b_model || ""}
                  judge={selectedSession?.judge_model || ""}
                  models={models}
                  onSwap={onLiveModelSwap}
                />
              )}
            </div>
          ) : (
            <div className="space-y-2 w-full xl:w-[240px] shrink-0">
              <div>
                <label htmlFor="model" className="mb-2 block text-sm font-medium" style={{ color: 'var(--sm-text-primary)' }}>
                  Overall Model
                </label>
                <select
                  id="model"
                  value={selectedModelName}
                  onChange={(event) => onModelChange(event.target.value)}
                  disabled={unlockedModels.length === 0 || isRunning}
                  className="sm-select h-12 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {unlockedModels.length === 0 ? <option value="">No verified models</option> : null}
                  {Object.entries(modelsByProvider).map(([provider, providerModels]) => (
                    <optgroup key={provider} label={provider}>
                      {providerModels.map((model) => (
                        <option key={model.name} value={model.name}>
                          {model.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
              <p className="text-sm leading-6" style={{ color: 'var(--sm-text-tertiary)' }}>
                {isPractice
                  ? "Alignment mode uses one AI opponent, then Judge and Coach when the session ends."
                  : "The router decides whether this is a normal chat or a strategy simulation."}
              </p>
            </div>
          )}

          <div className="flex-1 min-w-0">
            <label htmlFor="topic" className="mb-2 block text-sm font-medium" style={{ color: 'var(--sm-text-primary)' }}>
              {messageLabel}
            </label>
            <div className="flex flex-col gap-4">
              <div className="relative flex flex-col flex-1">
                <textarea
                  id="topic"
                  value={isRESTSession && sessionMode === "ai_vs_ai" && hasMessages ? "Autonomous simulation running turn-by-turn. Press 'Execute Next Turn' below to step the simulation." : topic}
                  onChange={(event) => onTopicChange(event.target.value)}
                  disabled={isRESTSession && sessionMode === "ai_vs_ai" && hasMessages}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      if (isRESTSession && sessionMode === "ai_vs_ai" && hasMessages ? !isRunning : canSend) {
                        onSend();
                      }
                    }
                  }}
                  placeholder={placeholder}
                  rows={3}
                  className={`sm-textarea min-h-[120px] w-full bg-white/[0.04] border border-white/10 rounded-2xl p-4 pr-16 text-sm text-white font-medium placeholder:text-slate-500 focus:border-cyan-500/50 focus:shadow-[0_0_20px_rgba(6,182,212,0.15)] transition-all resize-none ${isListening ? "border-cyan-500/80 shadow-[0_0_25px_rgba(6,182,212,0.25)]" : ""}`}
                />
                <div className="absolute bottom-3 right-3 flex gap-3 items-center pointer-events-auto">
                  {isListening && (
                    <div className="flex items-center gap-1.5 px-2 bg-zinc-950/60 backdrop-blur rounded-full py-0.5 border border-white/5">
                      <span className="h-1.5 w-1 bg-cyan-400 animate-[bounce_1s_infinite_100ms] rounded-full" />
                      <span className="h-2 w-1 bg-cyan-400 animate-[bounce_1s_infinite_200ms] rounded-full" />
                      <span className="h-3 w-1 bg-cyan-400 animate-[bounce_1s_infinite_300ms] rounded-full" />
                      <span className="h-2 w-1 bg-cyan-400 animate-[bounce_1s_infinite_400ms] rounded-full" />
                      <span className="h-1.5 w-1 bg-cyan-400 animate-[bounce_1s_infinite_500ms] rounded-full" />
                    </div>
                  )}
                  {isSupported && (
                    <button
                      type="button"
                      onClick={handleVoiceToggle}
                      className={`relative flex h-10 w-10 items-center justify-center rounded-full transition-all duration-300 ${
                        isListening 
                          ? "bg-cyan-500 text-white sm-animate-pulse-glow shadow-[0_0_20px_rgba(6,182,212,0.6)] scale-110" 
                          : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white hover:scale-105 border border-white/5 hover:border-white/20"
                      }`}
                      title="Voice Input"
                    >
                      {isListening && (
                        <span className="absolute inset-0 rounded-full border border-cyan-400 animate-ping opacity-75" />
                      )}
                      {isListening ? (
                        <svg className="relative z-10" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="6" height="6"/></svg>
                      ) : (
                        <svg className="relative z-10" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                      )}
                    </button>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-3 justify-end items-center">
                {hasMessages && (
                  <button
                    type="button"
                    onClick={onNewDebate}
                    disabled={isRunning}
                    className="h-11 px-5 rounded-xl bg-gradient-to-r from-red-500/20 to-amber-500/10 hover:from-red-500/30 hover:to-amber-500/20 border border-red-500/30 text-red-200 font-bold tracking-wide shadow-[0_0_15px_rgba(239,68,68,0.1)] hover:shadow-[0_0_20px_rgba(239,68,68,0.2)] transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  >
                    New Debate
                  </button>
                )}
                <button
                  type="button"
                  onClick={onSend}
                  disabled={!(isRESTSession && sessionMode === "ai_vs_ai" && hasMessages ? !isRunning : canSend)}
                  className="h-11 px-6 rounded-xl bg-gradient-to-r from-indigo-500 to-cyan-500 text-white font-bold tracking-wide shadow-[0_0_15px_rgba(99,102,241,0.4)] hover:shadow-[0_0_25px_rgba(6,182,212,0.6)] transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {isRunning ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      Processing
                    </span>
                  ) : (isRESTSession && sessionMode === "ai_vs_ai" && hasMessages) ? "Execute Next Turn" : (isPractice ? "Synchronize" : "Execute")}
                </button>
              </div>
            </div>
          </div>
        </div>
        <div className="mt-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm" style={{ color: 'var(--sm-text-tertiary)' }}>
            {models?.mock_mode
              ? "Mock responses are enabled."
              : `${models?.available_model_count ?? 0} verified model(s). One is required.`}
          </p>
          <p
            className={`text-sm ${overHardLimit ? "font-semibold text-red-700" : nearLimit ? "text-amber-700" : ""}`}
          >
            {charCount}/{USER_INPUT_MAX_CHARS} characters
          </p>
        </div>
        {nearLimit ? (
          <p className="mt-2 rounded-xl px-3 py-2 text-sm" style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)', color: 'var(--sm-accent-amber-light)' }}>
            You are close to the 5500 character limit.
          </p>
        ) : null}
        {overHardLimit ? (
          <p className="mt-2 rounded-xl px-3 py-2 text-sm" style={{ background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.2)', color: 'var(--sm-accent-con-light)' }}>
            This message is too long. Please shorten it to 5500 characters or less before sending.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function MessageBubble({
  message,
  settings,
  pending = false
}: {
  message: DebateMessage;
  settings: SessionSettings | null;
  pending?: boolean;
}) {
  const isUser = message.role === "user" || message.role === "practice_user";
  const { settings: voiceSettings } = useVoiceSettings();
  const { speak, stop, isSpeaking } = useVoiceSynthesis(voiceSettings);
  
  useEffect(() => {
    if (!isUser && !pending && voiceSettings.autoPlay && voiceSettings.enabled) {
      speak(message.content);
    }
  }, [pending, isUser, voiceSettings.autoPlay, voiceSettings.enabled, message.content, speak]);

  return (
    <article
      className={`relative mb-6 overflow-hidden rounded-2xl p-6 transition-all duration-500 ${
        isUser
          ? "ml-auto max-w-3xl border border-white/5 bg-white/[0.03]"
          : "mr-auto max-w-4xl sm-glass-card border border-indigo-500/20"
      } ${pending ? "shadow-[0_0_40px_rgba(99,102,241,0.15)] ring-1 ring-indigo-500/30" : ""}`}
      style={{
        transform: pending ? 'translateY(-4px)' : 'translateY(0)',
      }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono text-[10px] font-bold shadow-lg ${
            isUser 
              ? "bg-[linear-gradient(135deg,rgba(255,255,255,0.1),rgba(255,255,255,0.02))] text-white border border-white/10" 
              : "bg-[linear-gradient(135deg,var(--sm-accent-indigo),var(--sm-accent-cyan))] text-white"
          }`}>
            {isUser ? "HMN" : "SYS"}
            {!isUser && pending && (
               <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-cyan-400 sm-animate-pulse-glow" />
            )}
          </div>
          <div>
            <h3 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-white flex items-center gap-2">
              {message.speaker}
              {pending && <span className="sm-typing-indicator ml-2"><span/><span/><span/></span>}
            </h3>
            {message.model && (
              <p className="font-mono text-[10px] tracking-[0.15em] mt-1" style={{ color: "var(--sm-accent-cyan-light)" }}>
                {message.model}
              </p>
            )}
          </div>
        </div>
        
        <div className="flex flex-wrap items-center gap-2 text-[10px] font-medium">
          {settings?.show_timestamps && (
            <span className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-slate-400">
              {new Date(message.created_at).toLocaleTimeString()}
            </span>
          )}
          {settings?.show_token_count && (
            <span className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-slate-400">
              {estimateTokens(message.content)} tokens
            </span>
          )}
          {!isUser && voiceSettings.enabled && !pending && (
            <button
              onClick={() => isSpeaking ? stop() : speak(message.content)}
              className={`flex items-center gap-1.5 rounded-md border border-white/10 px-2 py-1 transition-all ${
                isSpeaking ? "bg-cyan-500/20 text-cyan-400 sm-animate-pulse-glow" : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white"
              }`}
              title={isSpeaking ? "Stop Synthesis" : "Synthesize Response"}
            >
              {isSpeaking ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              )}
              {isSpeaking ? "Playing" : "Listen"}
            </button>
          )}
          {pending && (
            <span className="sm-badge sm-badge-cyan sm-animate-pulse-glow flex items-center gap-1.5 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
              Stream Active
            </span>
          )}
        </div>
      </div>
      
      {pending && (
        <div className="absolute top-0 left-0 right-0 sm-streaming-bar" />
      )}
      
      <div className={`text-[15px] leading-relaxed text-slate-200 ${pending ? 'sm-streaming-cursor' : ''}`}>
        <MarkdownText text={message.content || "Connecting to inference engine..."} />
      </div>
      <MessageCosts message={message} settings={settings} />
    </article>
  );
}

export function MessageCosts({
  message,
  settings
}: {
  message: DebateMessage;
  settings: SessionSettings | null;
}) {
  if (!settings?.show_money_cost) {
    return null;
  }

  const isCouncilAssistantMessage = message.role === "assistant";
  const isDebateMessage =
    message.role === "judge" ||
    message.role === "judge_assistant" ||
    message.role === "judge_panelist" ||
    message.role === "practice_debater" ||
    message.role === "debate_trainer" ||
    message.role.startsWith("pro_") ||
    message.role.startsWith("con_");

  if (isCouncilAssistantMessage) {
    return <CostBox summary={message.cost_summary} settings={settings} label="Turn Value" />;
  }

  if (!isDebateMessage) {
    return null;
  }

  const showIndividual = settings.show_every_message_cost_in_debate;
  const overallSummary = message.debate_cost_summary;
  const fallbackOverall = message.role === "judge" && !overallSummary ? message.cost_summary : null;

  return (
    <>
      {showIndividual ? (
        <CostBox summary={message.cost_summary} settings={settings} label="Turn Value" />
      ) : null}
      <CostBox
        summary={overallSummary ?? fallbackOverall}
        settings={settings}
        label="Session Value"
      />
    </>
  );
}

export function CostBox({
  summary,
  settings,
  label = "Session Value"
}: {
  summary: CostSummary | null | undefined;
  settings: SessionSettings | null;
  label?: string;
}) {
  if (!summary || !settings?.show_money_cost) {
    return null;
  }
  return (
    <div className="sm-card mt-3 px-3 py-2 text-xs" style={{ borderRadius: 'var(--sm-radius-md)', color: 'var(--sm-text-secondary)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold" style={{ color: 'var(--sm-text-primary)' }}>
          {label}: {formatCost(summary.total, summary.currency)}
        </span>
        <span>
          {summary.calls} call(s), {summary.input_tokens} input tokens, {summary.output_tokens} output tokens
        </span>
      </div>
      {settings.show_model_costs && summary.models.length > 0 ? (
        <div className="mt-2" style={{ borderTop: '1px solid var(--sm-border)' }}>
          {summary.models.map((item) => (
            <div key={item.model} className="flex flex-wrap justify-between gap-2 py-1" style={{ borderBottom: '1px solid var(--sm-border)' }}>
              <span className="font-medium" style={{ color: 'var(--sm-text-primary)' }}>
                {item.model}
                {item.pricing_live ? (
                  <span className="sm-badge sm-badge-pro ml-2" style={{ fontSize: '10px' }}>
                    Live
                  </span>
                ) : null}
              </span>
              <span>
                {formatCost(item.cost, summary.currency)} · {item.calls} call(s) · {item.input_tokens} in / {item.output_tokens} out
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <p className="mt-1" style={{ fontSize: '11px', color: 'var(--sm-text-muted)' }}>
        Estimated from visible text tokens. {summary.rate_source}
      </p>
      {summary.warnings && summary.warnings.length > 0 ? (
        <div className="mt-2 space-y-1">
          {summary.warnings.map((warning, index) => (
            <p key={index} style={{ fontSize: '11px', color: 'var(--sm-accent-amber-light)' }}>
              {warning}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StatsPanel({
  analytics,
  realtimeAnalytics,
  sessionMode,
  history,
  debates,
  selectedDebateId,
  onDebateChange,
  intelligence,
  settings,
  onFeedbackSubmit,
  onVerdictReview
}: {
  analytics: DebateAnalytics | null;
  realtimeAnalytics?: any | null;
  sessionMode?: string;
  history: DebateAnalytics[];
  debates: DebateRecord[];
  selectedDebateId: string;
  onDebateChange: (debateId: string) => void;
  intelligence: DebateIntelligence | null;
  settings: SessionSettings | null;
  onFeedbackSubmit: (questionKey: string, answer: string) => Promise<void>;
  onVerdictReview: (
    action: "challenge" | "override",
    winner: "pro" | "con" | "unclear",
    note: string
  ) => Promise<void>;
}) {
  if (sessionMode === "ai_vs_ai" && realtimeAnalytics) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-4 space-y-6">
        <CognitiveMatrixPanel data={realtimeAnalytics.cognitive_matrix} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AlphaClusterPanel data={realtimeAnalytics.alpha_cluster} />
          <BetaClusterPanel data={realtimeAnalytics.beta_cluster} />
        </div>
      </section>
    );
  }

  if (!analytics) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex max-w-md flex-col items-center justify-center py-24 text-center">
          <svg className="mb-4 opacity-20" width="64" height="64" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <line x1="12" y1="52" x2="12" y2="32"/><line x1="26" y1="52" x2="26" y2="16"/>
            <line x1="40" y1="52" x2="40" y2="24"/><line x1="54" y1="52" x2="54" y2="8"/>
          </svg>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--sm-text-primary)' }}>Analytics</h2>
          <p className="mt-2 text-sm" style={{ color: 'var(--sm-text-muted)' }}>
            Start a debate to generate real analytics from the council transcript.
          </p>
        </div>
      </section>
    );
  }

  const [deepDiveOpen, setDeepDiveOpen] = useState(false);

  return (
    <section className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-6xl space-y-4">

        {/* ── Header row ── */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--sm-accent-indigo-light)' }}>Analytics</p>
            <h2 className="font-display text-2xl font-bold" style={{ color: 'var(--sm-text-primary)' }}>Strategic Intelligence</h2>
            <p className="mt-1 text-sm" style={{ color: 'var(--sm-text-tertiary)' }}>
              Round {analytics.round} · {analytics.turn_count} turns
              {analytics.source ? ` · ${analytics.source.name || 'Selected debate'}` : ''}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            {debates.length >= 2 ? (
              <label className="text-sm font-medium" style={{ color: 'var(--sm-text-secondary)' }}>
                Switch Debate
                <select
                  value={selectedDebateId || analytics.source?.debate_id || ""}
                  onChange={(event) => onDebateChange(event.target.value)}
                  className="mt-1 h-10 w-full rounded-md sm-card px-3 sm:w-64"
                >
                  {debates.map((debate) => (
                    <option key={debate.id} value={debate.id}>
                      {debate.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
        </div>

        {/* ── Phase bar ── */}
        {analytics.phase ? (
          <div>
            <PhasePanel phase={analytics.phase} />
          </div>
        ) : null}

        {/* ── PRIMARY METRICS ── */}
        <div>
          <p className="mb-3 text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>Primary Metrics</p>
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Current Winner" value={analytics.ensemble.weighted_vote} />
            <Metric label="Logic Lead" value={analytics.bayesian.leader} />
            <Metric label="Confidence" value={toPercent(analytics.confidence.average)} />
            <Metric label="Convergence" value={toPercent(analytics.delphi.convergence)} />
          </div>
        </div>

        {/* ── CHARTS ROW 1 ── */}
        <div className="grid gap-4 xl:grid-cols-3">
          <Panel title="Logic Lead Breakdown">
            <PieChart values={analytics.bayesian.probabilities} />
          </Panel>
          <Panel title="Influence Split">
            {Object.entries(analytics.mixture_of_experts.role_weights).map(([role, value]) => (
              <Bar key={role} label={formatAgentLabel(role)} value={value} />
            ))}
          </Panel>
          <Panel title="Stance Votes">
            <StanceVotesChart analytics={analytics} />
          </Panel>
        </div>

        {/* ── CHARTS ROW 2 ── */}
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <Panel title="Logic Lead Trend">
            <LineChart history={history.length > 0 ? history : [analytics]} />
          </Panel>
          <Panel title="Game Theory Matrix">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex flex-col justify-center rounded-xl bg-gradient-to-br from-indigo-500/10 to-transparent p-3 border border-indigo-500/20 group hover:border-indigo-500/50 transition-colors relative overflow-hidden">
                <div className="absolute top-0 right-0 p-2 opacity-20 group-hover:opacity-100 transition-opacity"><span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping inline-block"/></div>
                <dt className="text-[10px] font-mono uppercase tracking-widest text-indigo-300">Auction Priority</dt>
                <dd className="mt-1 font-display font-bold text-white truncate">{analytics.game_theory.auction_winner ?? "Pending"}</dd>
              </div>
              <div className="flex flex-col justify-center rounded-xl bg-gradient-to-br from-cyan-500/10 to-transparent p-3 border border-cyan-500/20 group hover:border-cyan-500/50 transition-colors relative overflow-hidden">
                <div className="absolute bottom-0 left-0 h-0.5 w-full bg-cyan-500/20"><div className="h-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.8)]" style={{width: `${Math.min(100, analytics.game_theory.nash_pressure * 100)}%`}} /></div>
                <dt className="text-[10px] font-mono uppercase tracking-widest text-cyan-300">Nash Pressure</dt>
                <dd className="mt-1 font-mono font-bold text-cyan-400 drop-shadow-[0_0_5px_rgba(34,211,238,0.5)]">{toPercent(analytics.game_theory.nash_pressure)}</dd>
              </div>
              <div className="flex flex-col justify-center rounded-xl bg-gradient-to-br from-emerald-500/10 to-transparent p-3 border border-emerald-500/20 group hover:border-emerald-500/50 transition-colors">
                <dt className="text-[10px] font-mono uppercase tracking-widest text-emerald-300">Logic Nodes</dt>
                <dd className="mt-1 font-mono font-bold text-emerald-400">{analytics.argument_graph.node_count}</dd>
              </div>
              <div className="flex flex-col justify-center rounded-xl bg-gradient-to-br from-rose-500/10 to-transparent p-3 border border-rose-500/20 group hover:border-rose-500/50 transition-colors">
                <dt className="text-[10px] font-mono uppercase tracking-widest text-rose-300">Synaptic Edges</dt>
                <dd className="mt-1 font-mono font-bold text-rose-400 text-xs tracking-wider">
                  <span className="text-emerald-400">{analytics.argument_graph.support_edges}S</span> / <span className="text-rose-400">{analytics.argument_graph.attack_edges}A</span>
                </dd>
              </div>
            </div>
          </Panel>
        </div>

        {/* ── SESSION CHARTS ── */}
        {analytics.session_charts ? (
          <>
            <div className="grid gap-4 xl:grid-cols-3">
              <Panel title="Win Rate By Team">
                <WinRateChart data={analytics.session_charts.win_rate_by_team} />
              </Panel>
              <Panel title="Session Value by Phase">
                <ValueBarChart
                  values={analytics.session_charts.cost_by_phase}
                  unit="USD"
                  formatter={(value) => `$${value.toFixed(6)}`}
                  emptyText="No per-phase cost recorded yet."
                />
              </Panel>
              <Panel title="Debate Duration">
                <DurationChart rows={analytics.session_charts.debate_durations} />
              </Panel>
            </div>
            <div className="grid gap-4 xl:grid-cols-[1fr_2fr]">
              <Panel title="Messages Per Role">
                <MessagesPieChart values={analytics.session_charts.messages_by_role} />
              </Panel>
              <Panel title="Citations">
                <CitationBox citations={analytics.session_charts.citations} />
              </Panel>
            </div>
          </>
        ) : null}

        {/* ── ARGUMENT MINING ── */}
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel title="Argument Mining">
            <p className="text-sm" style={{ color: 'var(--sm-text-secondary)' }}>
              {analytics.argument_mining.evidence_count} evidence cue(s), {analytics.argument_mining.rebuttal_count} rebuttal cue(s), {analytics.argument_mining.redundancy_count} redundant turn(s)
            </p>
            <div className="mt-2 space-y-2">
              {analytics.argument_graph.strongest_claims.map((claim, index) => (
                <p key={`${claim.speaker}-${index}`} className="text-sm">
                  <span className="font-semibold" style={{ color: 'var(--sm-text-primary)' }}>{claim.speaker}:</span>{' '}
                  <span style={{ color: 'var(--sm-text-secondary)' }}>{claim.text}</span>
                </p>
              ))}
            </div>
          </Panel>
          <Panel title="Key Terms">
            <div className="flex flex-wrap gap-2">
              {analytics.attention.top_terms.map((term) => (
                <span key={term} className="rounded-full border px-3 py-1 text-xs font-medium" style={{ borderColor: 'var(--sm-border)', color: 'var(--sm-text-secondary)', background: 'var(--sm-bg-tertiary)' }}>
                  {term}
                </span>
              ))}
            </div>
          </Panel>
        </div>

        {/* ── DEEP DIVE ACCORDION (Intelligence Ledgers) ── */}
        {intelligence?.debate ? (
          <div className="rounded-2xl border" style={{ borderColor: 'var(--sm-border)', background: 'var(--sm-bg-secondary)' }}>
            <button
              type="button"
              onClick={() => setDeepDiveOpen((prev) => !prev)}
              className="flex w-full items-center justify-between p-5 text-left"
            >
              <div>
                <p className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--sm-accent-indigo-light)' }}>Deep Dive</p>
                <h3 className="text-base font-semibold mt-0.5" style={{ color: 'var(--sm-text-primary)' }}>Intelligence Ledgers</h3>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs" style={{ color: 'var(--sm-text-muted)' }}>
                  {intelligence.records.length} record(s)
                </span>
                <svg
                  width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                  className={`transition-transform duration-300 ${deepDiveOpen ? 'rotate-180' : 'rotate-0'}`}
                  style={{ color: 'var(--sm-text-muted)' }}
                >
                  <polyline points="4,7 9,12 14,7"/>
                </svg>
              </div>
            </button>

            {deepDiveOpen ? (
              <div className="border-t px-5 pb-5 pt-4 space-y-4" style={{ borderColor: 'var(--sm-border)' }}>
                {/* Claim + Challenge */}
                <div className="grid gap-4 xl:grid-cols-2">
                  <Panel title="Claim Ledger">
                    <RecordList
                      records={intelligence.claims}
                      emptyText="No claims recorded yet."
                    />
                  </Panel>
                  <Panel title="Challenge Tracker">
                    <RecordList
                      records={intelligence.challenges}
                      emptyText="No challenges recorded yet."
                    />
                  </Panel>
                </div>
                {/* Evidence + Scorecard */}
                <div className="grid gap-4 xl:grid-cols-2">
                  <Panel title="Fact-Check Log">
                    <RecordList
                      records={intelligence.evidence}
                      emptyText="No evidence records yet."
                    />
                  </Panel>
                  <Panel title="Judge Scorecard">
                    <RecordList
                      records={intelligence.scorecards}
                      emptyText="Scorecard appears after the Strategic outcome."
                    />
                  </Panel>
                </div>
                {/* Values + Memory */}
                <div className="grid gap-4 xl:grid-cols-2">
                  <Panel title="Value System">
                    <RecordList
                      records={intelligence.values}
                      emptyText="No value notes yet."
                    />
                  </Panel>
                  <Panel title="Institutional Memory">
                    <RecordList
                      records={intelligence.memories}
                      emptyText="No memory saved for this debate yet."
                    />
                    <ExperienceList experiences={intelligence.experiences} />
                  </Panel>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

      </div>
    </section>
  );
}

function PhasePanel({ phase }: { phase: NonNullable<DebateAnalytics["phase"]> }) {
  const completed = Math.max(0, Math.min(phase.total || 0, phase.completed || 0));
  const width = phase.total > 0 ? `${Math.round((completed / phase.total) * 100)}%` : "0%";
  return (
    <Panel title="Phase">
      <div className="grid gap-4 pb-1 lg:grid-cols-[1fr_2fr]">
        <div className="space-y-2 text-sm ">
          <p className="font-semibold ">{phase.flow_name}</p>
          <p>{phase.pro_position}</p>
          <p>{phase.con_position}</p>
          <p>
            Progress: {completed}/{phase.total || phase.sequence.length}
          </p>
          <div className="h-2 rounded sm-card">
            <div className="h-2 rounded sm-btn-primary" style={{ width }} />
          </div>
          <p className="text-xs ">
            Phase data comes from saved transcript metadata for the selected debate.
          </p>
        </div>
        <div className="max-h-64 overflow-y-auto rounded-md sm-card">
          {phase.sequence.map((item) => (
            <div
              key={item.key}
              className={`flex gap-3 border-b border-zinc-100 px-3 py-2 text-sm last:border-b-0 ${
                phase.current?.key === item.key ? "bg-emerald-50" : ""
              }`}
            >
              <span className="w-8 shrink-0 font-semibold ">{item.index}</span>
              <div className="min-w-0 flex-1">
                <p className="font-medium ">{item.title}</p>
                <p className="text-xs ">
                  {item.speaker} · {item.kind.replaceAll("_", " ")}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function WinRateChart({
  data
}: {
  data: NonNullable<DebateAnalytics["session_charts"]>["win_rate_by_team"];
}) {
  if (data.resolved === 0) {
    return (
      <p className="text-sm ">
        No resolved Alpha/Beta verdicts yet. Completed sessions with clear Judge winners will appear here.
      </p>
    );
  }
  const resolved = data.resolved;
  return (
    <div>
      <Bar label="Alpha" value={data.pro / resolved} />
      <Bar label="Beta" value={data.con / resolved} />
      <p className="mt-2 text-xs ">
        {data.resolved} resolved winner(s) from {data.total_completed} completed debate(s).
        {data.unclear > 0 ? ` ${data.unclear} verdict(s) were unclear.` : ""}
      </p>
    </div>
  );
}

function StanceVotesChart({ analytics }: { analytics: DebateAnalytics }) {
  const total = Math.max(
    0.001,
    Object.values(analytics.ensemble.weighted_votes).reduce((sum, value) => sum + value, 0)
  );
  return (
    <div>
      {Object.entries(analytics.ensemble.weighted_votes).map(([label, value]) => (
        <Bar key={label} label={label} value={value / total} />
      ))}
    </div>
  );
}

function ValueBarChart({
  values,
  unit,
  formatter,
  emptyText
}: {
  values: Record<string, number>;
  unit: string;
  formatter: (value: number) => string;
  emptyText: string;
}) {
  const entries = Object.entries(values).filter(([, value]) => value > 0);
  const max = Math.max(...entries.map(([, value]) => value), 0);
  if (entries.length === 0 || max <= 0) {
    return <p className="text-sm ">{emptyText}</p>;
  }
  return (
    <div>
      <p className="mb-2 text-xs font-medium ">Unit: {unit}</p>
      {entries.map(([label, value]) => (
        <ValueBar key={label} label={label} value={value} max={max} formatted={formatter(value)} />
      ))}
    </div>
  );
}

function DurationChart({
  rows
}: {
  rows: NonNullable<DebateAnalytics["session_charts"]>["debate_durations"];
}) {
  const completed = rows.filter((row) => row.duration_seconds > 0);
  const max = Math.max(...completed.map((row) => row.duration_seconds), 0);
  if (completed.length === 0 || max <= 0) {
    return <p className="text-sm ">Completed debate duration will appear here.</p>;
  }
  return (
    <div>
      <p className="mb-2 text-xs font-medium ">Unit: seconds</p>
      {completed.slice(-8).map((row) => (
        <ValueBar
          key={row.debate_id}
          label={row.name}
          value={row.duration_seconds}
          max={max}
          formatted={formatDuration(row.duration_seconds)}
        />
      ))}
    </div>
  );
}

function MessagesPieChart({ values }: { values: Record<string, number> }) {
  const entries = Object.entries(values).filter(([, value]) => value > 0);
  if (entries.length === 0) {
    return <p className="text-sm ">No role messages recorded for this debate yet.</p>;
  }
  return <MultiPieChart entries={entries} unit="message(s)" />;
}

function CitationBox({
  citations
}: {
  citations: NonNullable<DebateAnalytics["session_charts"]>["citations"];
}) {
  if (citations.length === 0) {
    return (
      <p className="text-sm ">
        No live researcher citations have been recorded in this chat. Researchers are instructed to
        cite real URLs only when web search/source access is actually available.
      </p>
    );
  }
  return (
    <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
      {citations.map((citation, index) => (
        <div key={`${citation.url}-${index}`} className="rounded-md sm-card p-2 text-sm">
          <p className="font-medium ">{citation.speaker}</p>
          <p className="text-xs ">
            {citation.debate_name} · {citation.phase_title}
          </p>
          <a
            href={citation.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 block break-all  underline"
          >
            {citation.domain}
          </a>
        </div>
      ))}
    </div>
  );
}


function TeamPreparationNotice() {
  return (
    <div className="mx-auto mb-4 grid max-w-4xl gap-3 md:grid-cols-2">
      <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4">
        <p className="text-sm font-semibold text-emerald-900">Alpha Cluster is preparing</p>
        <p className="mt-1 text-sm ">
          The Alpha team is building a private notebook from its assigned roles, usable experience,
          and the current topic. The opponent will not receive these notes, but you can review them.
        </p>
      </div>
      <div className="rounded-md border border-red-200 bg-red-50 p-4">
        <p className="text-sm font-semibold text-red-900">Beta Team Room is preparing</p>
        <p className="mt-1 text-sm text-red-800">
          The Beta team is building a separate private notebook before the public debate starts.
          Public speaking begins after both rooms finish their structured notes.
        </p>
      </div>
    </div>
  );
}

function IntelligencePanel({
  intelligence,
  settings,
  onFeedbackSubmit,
  onVerdictReview
}: {
  intelligence: DebateIntelligence | null;
  settings: SessionSettings | null;
  onFeedbackSubmit: (questionKey: string, answer: string) => Promise<void>;
  onVerdictReview: (
    action: "challenge" | "override",
    winner: "pro" | "con" | "unclear",
    note: string
  ) => Promise<void>;
}) {
  if (!intelligence?.debate) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-2xl font-semibold ">Strategic Intelligence</h2>
          <p className="mt-2 ">
            Start a debate to create tracked claims, challenges, evidence, scorecards, and real experience records.
          </p>
        </div>
      </section>
    );
  }

  const debate = intelligence.debate;
  const unresolved = intelligence.challenges.filter((record) => /unanswered|ignored/i.test(record.status));
  const verifiedEvidence = intelligence.evidence.filter((record) => /verified/i.test(record.status));

  return (
    <section className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-2xl font-semibold ">Strategic Intelligence</h2>
            <p className="text-sm ">
              {debate.name} · {debate.topic}
            </p>
          </div>
          <p className="text-sm font-medium ">
            {intelligence.records.length} structured record(s)
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="Tracked claims" value={String(intelligence.claims.length)} />
          <Metric label="Open challenges" value={String(unresolved.length)} />
          <Metric label="Evidence records" value={String(intelligence.evidence.length)} />
          <Metric label="Verified URLs" value={String(verifiedEvidence.length)} />
        </div>

        <Panel title="Post-debate review summary">
          <RecordList
            records={intelligence.reviews}
            emptyText="The review appears after the Judge finishes and the debate is finalized."
          />
        </Panel>

        <VerdictReviewPanel
          key={`verdict-${debate.id}`}
          records={intelligence.verdict_reviews}
          settings={settings}
          debate={debate}
          onVerdictReview={onVerdictReview}
        />

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Claim Ledger">
            <RecordList
              records={intelligence.claims}
              emptyText="No claim objects have been recorded yet. New public turns create claim records from the actual transcript."
            />
          </Panel>
          <Panel title="Challenge And Resolution Tracker">
            <RecordList
              records={intelligence.challenges}
              emptyText="No challenges have been recorded yet. Critic, Examiner, and question-like turns create challenge records."
            />
          </Panel>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Fact-Check Log">
            <RecordList
              records={intelligence.evidence}
              emptyText="No evidence records yet. Model-knowledge evidence is labeled separately from live URL evidence."
            />
          </Panel>
          <Panel title="Judge Scorecard">
            <RecordList
              records={intelligence.scorecards}
              emptyText="The scorecard appears after the Strategic outcome. It is based on tracked claims, challenges, evidence, and the Judge text."
            />
          </Panel>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Value And Consequence System">
            <RecordList
              records={intelligence.values}
              emptyText="No value or consequence notes yet. The system records only concrete issues like unsupported evidence or dropped challenges."
            />
          </Panel>
          <Panel title="Cross-Debate Institutional Memory">
            <RecordList
              records={intelligence.memories}
              emptyText="No memory save event for this debate yet. Memory records are created from saved debate objects, not invented traits."
            />
            <ExperienceList experiences={intelligence.experiences} />
          </Panel>
        </div>

        <FeedbackQuestionsPanel
          key={`feedback-${debate.id}`}
          resetKey={debate.id}
          questions={intelligence.feedback_questions}
          onFeedbackSubmit={onFeedbackSubmit}
        />
      </div>
    </section>
  );
}

function VerdictReviewPanel({
  records,
  settings,
  debate,
  onVerdictReview
}: {
  records: DebateIntelligenceRecord[];
  settings: SessionSettings | null;
  debate: DebateRecord;
  onVerdictReview: (
    action: "challenge" | "override",
    winner: "pro" | "con" | "unclear",
    note: string
  ) => Promise<void>;
}) {
  const [action, setAction] = useState<"challenge" | "override">("challenge");
  const [winner, setWinner] = useState<"pro" | "con" | "unclear">("unclear");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = settings?.judging_settings?.allow_user_verdict_challenge ?? true;
  const completed = debate.status === "completed";

  useEffect(() => {
    setAction("challenge");
    setWinner("unclear");
    setNote("");
    setSaved(false);
    setError(null);
  }, [debate.id]);

  const submit = async () => {
    if (!completed || !allowed || saving) {
      return;
    }
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await onVerdictReview(action, winner, note);
      setNote("");
      setSaved(true);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save verdict review.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel title="Verdict review">
      <p className="text-sm leading-6 ">
        Challenge the Judge when something was missed, or override the displayed winner when you
        want the chat statistics to use your final call. The original Judge message stays unchanged.
      </p>
      <RecordList
        records={records}
        emptyText="No verdict challenge or override has been saved for this debate yet."
      />
      {!allowed ? (
        <p className="mt-3 rounded-md sm-card px-3 py-2 text-sm ">
          Verdict review is disabled in this chat's Judgment Quality settings.
        </p>
      ) : null}
      {completed && allowed ? (
        <div className="mt-4 grid gap-3 md:grid-cols-[160px_160px_1fr_auto] md:items-end">
          <SelectSetting
            label="Action"
            value={action}
            options={["challenge", "override"]}
            onChange={(value) => {
              setAction(value as "challenge" | "override");
              setSaved(false);
            }}
          />
          <SelectSetting
            label="Winner"
            value={winner}
            options={["pro", "con", "unclear"]}
            onChange={(value) => {
              setWinner(value as "pro" | "con" | "unclear");
              setSaved(false);
            }}
          />
          <label className="text-sm font-medium ">
            Note
            <input
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
                setSaved(false);
              }}
              maxLength={1200}
              placeholder="What did the Judge miss, or why should the winner change?"
              className="mt-1 h-11 w-full rounded-md border  px-3"
            />
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="h-11 rounded-md  px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      ) : null}
      {!completed ? (
        <p className="mt-3 text-sm ">
          Verdict review becomes available after the Judge finishes.
        </p>
      ) : null}
      {saved ? <p className="mt-2 text-sm ">Verdict review saved.</p> : null}
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
    </Panel>
  );
}

function TeamRoomPanel({
  intelligence,
  team
}: {
  intelligence: DebateIntelligence | null;
  team: "pro" | "con";
}) {
  const teamName = team === "pro" ? "Alpha" : "Beta";
  const records = intelligence?.team_rooms[team] ?? [];
  const notebooks = records.filter((record) => record.record_type === "team_notebook");
  const pressureRecords = records.filter((record) => record.record_type !== "team_notebook");
  const experiences = (intelligence?.experiences ?? []).filter((experience) =>
    experience.agent_id.toLowerCase().startsWith(`${team}_`)
  );

  if (!intelligence?.debate) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-2xl font-semibold ">{teamName} Team Room</h2>
          <p className="mt-2 ">
            This room fills with view-only private team notebooks after a debate starts.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <div>
          <h2 className="text-2xl font-semibold ">{teamName} Team Room</h2>
          <p className="mt-1 text-sm ">
            Private from the opposing team inside the debate system, visible to you for transparency.
            These are structured notebooks and records, not hidden chain-of-thought.
          </p>
        </div>

        <Panel title={`${teamName} Private Notebook`}>
          <RecordList
            records={notebooks}
            emptyText="No notebook records yet. The team preparation phase creates these before public debate begins."
          />
        </Panel>

        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title={`${teamName} Pressure And Objects`}>
            <RecordList
              records={pressureRecords}
              emptyText="No team-specific claims, challenges, or evidence records yet."
              limit={10}
            />
          </Panel>
          <Panel title={`${teamName} Experience Identity`}>
            <p className="mb-3 text-sm ">
              Identity is built from real saved activity only. Empty identity is valid; the system should not invent strengths or memories.
            </p>
            <ExperienceList experiences={experiences} emptyText={`No reliable ${teamName} experience recorded yet.`} />
          </Panel>
        </div>
      </div>
    </section>
  );
}

function CouncilSettingsPanel({
  settings,
  onChange,
  onResetUniversalIdentities,
  onResetUserDebateProfile
}: {
  settings: CouncilSettings | null;
  onChange: (updates: Partial<CouncilSettings>) => void;
  onResetUniversalIdentities: (confirmation: string) => Promise<{ deleted: number }>;
  onResetUserDebateProfile: (confirmation: string) => Promise<unknown>;
}) {
  const [resetOpen, setResetOpen] = useState(false);
  const [profileResetOpen, setProfileResetOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [profileConfirmation, setProfileConfirmation] = useState("");
  const [resetNotice, setResetNotice] = useState<string | null>(null);
  const [profileNotice, setProfileNotice] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [profileResetError, setProfileResetError] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [isProfileResetting, setIsProfileResetting] = useState(false);

  if (!settings) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        <p className="">Loading Council Settings...</p>
      </section>
    );
  }

  const handleReset = async () => {
    setResetError(null);
    setResetNotice(null);
    setIsResetting(true);
    try {
      const result = await onResetUniversalIdentities(confirmation);
      setResetNotice(`Reset complete. ${result.deleted} universal identity record(s) were hidden.`);
      setConfirmation("");
      setResetOpen(false);
    } catch (exc) {
      setResetError(exc instanceof Error ? exc.message : "Could not reset universal identities.");
    } finally {
      setIsResetting(false);
    }
  };

  const handleProfileReset = async () => {
    setProfileResetError(null);
    setProfileNotice(null);
    setIsProfileResetting(true);
    try {
      await onResetUserDebateProfile(profileConfirmation);
      setProfileNotice("User debate profile reset complete.");
      setProfileConfirmation("");
      setProfileResetOpen(false);
    } catch (exc) {
      setProfileResetError(exc instanceof Error ? exc.message : "Could not reset user debate profile.");
    } finally {
      setIsProfileResetting(false);
    }
  };

  return (
    <section className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-5xl space-y-4">
        <Panel title="Appearance">
          <SelectSetting
            label="Theme"
            value={settings.theme}
            options={["Light", "Dark", "System"]}
            onChange={(value) => onChange({ theme: value as CouncilSettings["theme"] })}
          />
          <p className="mt-3 text-sm ">
            Choose Light, Dark, or System to follow your operating system preference.
          </p>
        </Panel>

        <Panel title="Universal experience">
          <div className="grid gap-3 md:grid-cols-2">
            <ToggleSetting
              label="Universal Experience"
              value={settings.universal_experience}
              onChange={(value) => onChange({ universal_experience: value })}
            />
            <ToggleSetting
              label="Use Agent Identity Profiles"
              value={settings.use_agent_identity_profiles}
              onChange={(value) => onChange({ use_agent_identity_profiles: value })}
            />
            <ToggleSetting
              label="Use User Debate Profile"
              value={settings.use_user_debate_profile}
              onChange={(value) => onChange({ use_user_debate_profile: value })}
            />
          </div>
          <p className="mt-3 text-sm ">
            Universal experience lets agent identities use factual records from all chats. Identity profiles stay empty until real debate records exist.
          </p>
        </Panel>

        <Panel title="Confirmation messages">
          <div className="grid gap-3 md:grid-cols-3">
            <ToggleSetting
              label="Skip Delete Chat Confirmation"
              value={settings.confirmation_preferences.delete_chat}
              onChange={(value) =>
                onChange({
                  confirmation_preferences: {
                    ...settings.confirmation_preferences,
                    delete_chat: value
                  }
                })
              }
            />
            <ToggleSetting
              label="Skip Clear History Confirmation"
              value={settings.confirmation_preferences.clear_chat_history}
              onChange={(value) =>
                onChange({
                  confirmation_preferences: {
                    ...settings.confirmation_preferences,
                    clear_chat_history: value
                  }
                })
              }
            />
            <ToggleSetting
              label="Skip Clear Memory Confirmation"
              value={settings.confirmation_preferences.clear_chat_memory}
              onChange={(value) =>
                onChange({
                  confirmation_preferences: {
                    ...settings.confirmation_preferences,
                    clear_chat_memory: value
                  }
                })
              }
            />
          </div>
        </Panel>

        <Panel title="Debate intelligence defaults">
          <div className="grid gap-3 md:grid-cols-3">
            <SelectSetting
              label="Strategic Intelligence Depth"
              value={settings.debate_intelligence_depth}
              options={["Light", "Normal", "Deep"]}
              onChange={(value) =>
                onChange({ debate_intelligence_depth: value as CouncilSettings["debate_intelligence_depth"] })
              }
            />
            <SelectSetting
              label="Default Judge Mode"
              value={settings.default_judge_mode}
              options={["Debate Performance", "Truth-Seeking", "Hybrid"]}
              onChange={(value) =>
                onChange({ default_judge_mode: value as CouncilSettings["default_judge_mode"] })
              }
            />
            <ToggleSetting
              label="Value Consequence System"
              value={settings.use_value_consequence_system}
              onChange={(value) => onChange({ use_value_consequence_system: value })}
            />
          </div>
          <p className="mt-3 text-sm ">
            Light uses deterministic notebooks. Normal and Deep ask the assigned models to produce user-visible structured team notes before public debate.
          </p>
        </Panel>

        <Panel title="Reset universal identities">
          <p className="text-sm ">
            This hides universal agent experience records. It does not delete chats, messages, or debate statistics.
            Use this only when you want the council identities to start learning again from zero.
          </p>
          {!resetOpen ? (
            <button
              type="button"
              onClick={() => {
                setResetOpen(true);
                setResetNotice(null);
                setResetError(null);
              }}
              className="mt-3 rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
            >
              Reset Universal Agent Identities
            </button>
          ) : (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-semibold text-red-900">
                Type RESET COUNCIL IDENTITIES to confirm.
              </p>
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                className="mt-2 h-10 w-full rounded-md border border-red-300  px-3 text-sm"
                placeholder="RESET COUNCIL IDENTITIES"
              />
              {resetError ? <p className="mt-2 text-sm text-red-800">{resetError}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleReset}
                  disabled={isResetting || confirmation !== "RESET COUNCIL IDENTITIES"}
                  className="rounded-md bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isResetting ? "Resetting..." : "Confirm Reset"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setResetOpen(false);
                    setConfirmation("");
                    setResetError(null);
                  }}
                  className="rounded-md border  px-4 py-2 text-sm font-semibold text-zinc-800 hover:sm-card"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {resetNotice ? <p className="mt-3 text-sm ">{resetNotice}</p> : null}
        </Panel>

        <Panel title="Reset user debate profile">
          <p className="text-sm ">
            This resets the human practice profile used by AI Strategist and Strategy Coach.
            It does not delete chats or AI agent identities.
          </p>
          {!profileResetOpen ? (
            <button
              type="button"
              onClick={() => {
                setProfileResetOpen(true);
                setProfileNotice(null);
                setProfileResetError(null);
              }}
              className="mt-3 rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
            >
              Reset User Debate Profile
            </button>
          ) : (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3">
              <p className="text-sm font-semibold text-red-900">
                Type RESET USER DEBATE PROFILE to confirm.
              </p>
              <input
                value={profileConfirmation}
                onChange={(event) => setProfileConfirmation(event.target.value)}
                className="mt-2 h-10 w-full rounded-md border border-red-300  px-3 text-sm"
                placeholder="RESET USER DEBATE PROFILE"
              />
              {profileResetError ? <p className="mt-2 text-sm text-red-800">{profileResetError}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleProfileReset}
                  disabled={isProfileResetting || profileConfirmation !== "RESET USER DEBATE PROFILE"}
                  className="rounded-md bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isProfileResetting ? "Resetting..." : "Confirm Reset"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setProfileResetOpen(false);
                    setProfileConfirmation("");
                    setProfileResetError(null);
                  }}
                  className="rounded-md border  px-4 py-2 text-sm font-semibold text-zinc-800 hover:sm-card"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {profileNotice ? <p className="mt-3 text-sm ">{profileNotice}</p> : null}
        </Panel>
      </div>
    </section>
  );
}

function RecordList({
  records,
  emptyText,
  limit = 6
}: {
  records: DebateIntelligenceRecord[];
  emptyText: string;
  limit?: number;
}) {
  if (records.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <svg className="mb-3 opacity-20" width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <rect x="4" y="4" width="24" height="24" rx="3"/>
          <line x1="10" y1="12" x2="22" y2="12"/>
          <line x1="10" y1="17" x2="18" y2="17"/>
          <line x1="10" y1="22" x2="15" y2="22"/>
        </svg>
        <p className="text-xs" style={{ color: 'var(--sm-text-muted)' }}>{emptyText}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {records.slice(-limit).reverse().map((record) => (
        <RecordCard key={record.id} record={record} />
      ))}
      {records.length > limit ? (
        <p className="text-xs ">Showing latest {limit} of {records.length} record(s).</p>
      ) : null}
    </div>
  );
}

function RecordCard({ record }: { record: DebateIntelligenceRecord }) {
  const team = record.team ? `${record.team.toUpperCase()} · ` : "";
  const role = record.role ? formatAgentLabel(record.role) : "System";
  return (
    <article className="rounded-md sm-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded  px-2 py-1 text-xs font-semibold ">
          {formatRecordType(record.record_type)}
        </span>
        <span className="rounded  px-2 py-1 text-xs ">{team}{role}</span>
        {record.status ? (
          <span className="rounded  px-2 py-1 text-xs ">{record.status}</span>
        ) : null}
        <span className="rounded  px-2 py-1 text-xs ">
          confidence {Math.round((record.confidence || 0) * 100)}%
        </span>
      </div>
      <p className="mt-2 text-sm font-semibold ">{record.title}</p>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-6 ">{record.content}</p>
      <p className="mt-2 text-xs ">
        Basis: {Array.isArray(record.basis) ? record.basis.length : 0} trace item(s). Updated {new Date(record.updated_at).toLocaleString()}.
      </p>
    </article>
  );
}

function ExperienceList({
  experiences,
  emptyText = "No reliable experience recorded yet."
}: {
  experiences: AgentExperienceRecord[];
  emptyText?: string;
}) {
  if (experiences.length === 0) {
    return <p className="text-sm ">{emptyText}</p>;
  }
  return (
    <div className="mt-3 space-y-2">
      {experiences.slice(0, 8).map((experience) => (
        <div key={experience.id} className="rounded-md sm-card p-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <span className="rounded  px-2 py-1 text-xs font-semibold ">
              {formatAgentLabel(experience.agent_id)}
            </span>
            <span className="rounded  px-2 py-1 text-xs ">{experience.scope}</span>
            <span className="rounded  px-2 py-1 text-xs ">
              confidence {experience.confidence}
            </span>
          </div>
          <p className="mt-2 leading-6 ">{experience.lesson}</p>
          <p className="mt-1 text-xs ">
            Basis: {Array.isArray(experience.basis) ? experience.basis.length : 0} trace item(s). Used {experience.use_count} time(s).
          </p>
        </div>
      ))}
    </div>
  );
}

function FeedbackQuestionsPanel({
  questions,
  resetKey,
  onFeedbackSubmit
}: {
  questions: DebateIntelligence["feedback_questions"];
  resetKey: string;
  onFeedbackSubmit: (questionKey: string, answer: string) => Promise<void>;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [otherAnswers, setOtherAnswers] = useState<Record<string, string>>({});
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAnswers({});
    setOtherAnswers({});
    setSent({});
    setSavingKey(null);
    setError(null);
  }, [resetKey]);

  if (questions.length === 0) {
    return null;
  }

  const submit = async (key: string) => {
    const selected = answers[key] ?? "";
    const answer = selected === "Other..." ? otherAnswers[key] ?? "" : selected;
    if (!answer.trim()) {
      return;
    }
    setSavingKey(key);
    setError(null);
    try {
      await onFeedbackSubmit(key, answer.trim());
      setSent((current) => ({ ...current, [key]: true }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save feedback.");
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <Panel title="Post-debate user feedback">
      <p className="mb-3 text-sm ">
        Optional feedback teaches the council through saved records. You can skip everything; new debates refresh these questions.
      </p>
      <div className="space-y-3">
        {questions.map((question) => {
          const selected = answers[question.key] ?? "";
          const freeText = otherAnswers[question.key] ?? "";
          const answer = selected === "Other..." ? freeText : selected;
          return (
            <div key={question.key} className="rounded-md sm-card p-3">
              <p className="text-sm font-semibold ">{question.question}</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {question.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      setAnswers((current) => ({ ...current, [question.key]: option }));
                      setSent((current) => ({ ...current, [question.key]: false }));
                    }}
                    className={`rounded-md border px-3 py-2 text-left text-sm ${
                      selected === option
                        ? "border-zinc-950  text-white"
                        : "  hover:sm-card"
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
              {selected === "Other..." ? (
                <textarea
                  value={freeText}
                  onChange={(event) => {
                    setOtherAnswers((current) => ({ ...current, [question.key]: event.target.value }));
                    setSent((current) => ({ ...current, [question.key]: false }));
                  }}
                  rows={2}
                  className="mt-2 w-full resize-none rounded-md border  px-3 py-2 text-sm"
                  placeholder="Write your own feedback."
                />
              ) : null}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => submit(question.key)}
                  disabled={savingKey === question.key || !answer.trim() || sent[question.key]}
                  className="rounded-md  px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sent[question.key] ? "Saved" : savingKey === question.key ? "Saving..." : "Save Feedback"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAnswers((current) => ({ ...current, [question.key]: "" }));
                    setOtherAnswers((current) => ({ ...current, [question.key]: "" }));
                    setSent((current) => ({ ...current, [question.key]: false }));
                  }}
                  className="rounded-md border  px-3 py-2 text-sm font-semibold  hover:sm-card"
                >
                  Skip
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
    </Panel>
  );
}

function formatRecordType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatAgentLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function SettingsPanel({
  session,
  settings,
  practiceState,
  models,
  messages,
  analytics,
  intelligence,
  selectedDebateId,
  selectedModelName,
  isRenaming,
  isRunning,
  debates,
  onModelChange,
  onSettingsChange,
  onRename,
  onRenameDebate,
  onDeleteRequest,
  onDeleteDebateRequest,
  onClearRequest
}: {
  session: ChatSession | null;
  settings: SessionSettings | null;
  practiceState: PracticeState | null;
  models: ModelsResponse | null;
  messages: DebateMessage[];
  analytics: DebateAnalytics | null;
  intelligence: DebateIntelligence | null;
  selectedDebateId: string;
  selectedModelName: string;
  isRenaming: boolean;
  isRunning: boolean;
  debates: DebateRecord[];
  onModelChange: (modelName: string) => void;
  onSettingsChange: (updates: Partial<SessionSettings>) => void;
  onRename: (session: ChatSession, name: string) => Promise<boolean>;
  onRenameDebate: (debate: DebateRecord, name: string) => Promise<boolean>;
  onDeleteRequest: (session: ChatSession) => void;
  onDeleteDebateRequest: (session: ChatSession, debate: DebateRecord) => void;
  onClearRequest: (session: ChatSession, mode: "history" | "memory") => void;
}) {
  const [title, setTitle] = useState(session?.name ?? "");
  const [renameNotice, setRenameNotice] = useState<string | null>(null);
  const unlockedModels = models?.models ?? [];

  useEffect(() => {
    setTitle(session?.name ?? "");
    setRenameNotice(null);
  }, [session?.id, session?.name]);

  if (!session || !settings) {
    return (
      <section className="min-h-0 flex-1 overflow-y-auto p-6">
        <p className="">Select a chat to edit settings.</p>
      </section>
    );
  }

  const handleRenameClick = async () => {
    setRenameNotice(null);
    const saved = await onRename(session, title);
    if (saved) {
      setTitle(title.trim());
      setRenameNotice("Chat title updated.");
    }
  };

  const updateAgentSetting = (
    roleKey: string,
    updates: Partial<SessionSettings["agent_settings"][string]>
  ) => {
    const currentAgent = settings.agent_settings[roleKey] ?? {
      model: "",
      temperature: settings.temperature,
      max_tokens: settings.max_tokens,
      response_length: settings.response_length,
      web_search: false,
      always_on: false
    };
    onSettingsChange({
      agent_settings: {
        ...settings.agent_settings,
        [roleKey]: { ...currentAgent, ...updates }
      }
    });
  };

  const handleExport = () => {
    const debate = debates.find((item) => item.id === selectedDebateId) ?? debates[0] ?? null;
    const scopedMessages = debate
      ? messages.filter((message) => message.debate_id === debate.id)
      : messages;
    const payload = {
      exported_at: new Date().toISOString(),
      chat: session,
      debate,
      settings: {
        export_format: settings.export_format,
        debate_tone: settings.debate_tone,
        language: settings.language,
        judge_mode: settings.judge_mode,
        evidence_strictness: settings.evidence_strictness
      },
      analytics,
      intelligence: intelligence
        ? {
            claims: intelligence.claims,
            challenges: intelligence.challenges,
            evidence: intelligence.evidence,
            scorecards: intelligence.scorecards,
            values: intelligence.values,
            reviews: intelligence.reviews
          }
        : null,
      messages: scopedMessages
    };
    const format = settings.export_format;
    if (format === "JSON") {
      downloadTextFile(
        `${safeFileStem(session.name)}-${debate ? safeFileStem(debate.name) : "chat"}.json`,
        JSON.stringify(payload, null, 2),
      "application/json"
      );
      return;
    }
    const markdown = exportAsMarkdown(payload);
    if (format === "PDF") {
      const opened = exportPrintablePdf(markdown, `${session.name}${debate ? ` - ${debate.name}` : ""}`);
      if (!opened) {
        downloadTextFile(
          `${safeFileStem(session.name)}-${debate ? safeFileStem(debate.name) : "chat"}.md`,
          markdown,
        "text/markdown"
        );
      }
      return;
    }
    downloadTextFile(
      `${safeFileStem(session.name)}-${debate ? safeFileStem(debate.name) : "chat"}.md`,
      markdown,
    "text/markdown"
    );
  };

  const visibleTeamRoles = teamRoleSettings.filter(
    (role) => role.minDebaters <= settings.debaters_per_team
  );
  const visibleNeutralRoles = neutralRoleSettings.filter(
    (role) => role.key !== "judge_assistant" || settings.judge_assistant_enabled
  );

  const isRESTSession = Boolean(session.ai_a_model);

  return (
    <section className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-5xl space-y-4">
        <h2 className="text-2xl font-semibold ">Chat Settings</h2>

        {isRESTSession ? (
          <Panel title="Strategic State Machine Selections">
            <div 
              className="rounded-xl border p-4 mb-4" 
              style={{ 
                borderColor: 'var(--sm-border-accent)', 
                background: 'linear-gradient(135deg, rgba(99,102,241,0.05), rgba(6,182,212,0.03))' 
              }}
            >
              <p className="text-xs font-bold uppercase tracking-wider text-cyan-400">Node Orchestration</p>
              <p className="text-xs mt-1" style={{ color: 'var(--sm-text-secondary)' }}>
                These are the assigned cognitive models and rounds allocated for this state machine. To prevent state bleeding, changing these parameters is locked during active rounds.
              </p>
            </div>
            
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl p-3.5 border bg-white/[0.02]" style={{ borderColor: 'var(--sm-border)' }}>
                <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block">AI A / Opponent Node</span>
                <span className="text-sm font-semibold mt-1 block" style={{ color: 'var(--sm-text-primary)' }}>{session.ai_a_model}</span>
              </div>
              
              {session.mode === "ai_vs_ai" ? (
                <div className="rounded-xl p-3.5 border bg-white/[0.02]" style={{ borderColor: 'var(--sm-border)' }}>
                  <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider block">AI B Node</span>
                  <span className="text-sm font-semibold mt-1 block" style={{ color: 'var(--sm-text-primary)' }}>{session.ai_b_model}</span>
                </div>
              ) : null}

              <div className="rounded-xl p-3.5 border bg-white/[0.02]" style={{ borderColor: 'var(--sm-border)' }}>
                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">Adjudicator Node</span>
                <span className="text-sm font-semibold mt-1 block" style={{ color: 'var(--sm-text-primary)' }}>{session.judge_model}</span>
              </div>

              <div className="rounded-xl p-3.5 border bg-white/[0.02]" style={{ borderColor: 'var(--sm-border)' }}>
                <span className="text-xs font-bold uppercase tracking-wider block" style={{ color: 'var(--sm-text-secondary)' }}>Total Rounds</span>
                <span className="text-sm font-semibold mt-1 block" style={{ color: 'var(--sm-text-primary)' }}>{session.rounds} Rounds</span>
              </div>
            </div>
          </Panel>
        ) : null}

        <Panel title="Chat meta">
          <label className="block text-sm font-medium " htmlFor="chat-title">
            Chat title
          </label>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <input
              id="chat-title"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setRenameNotice(null);
              }}
              className="h-11 flex-1 rounded-md border  px-3"
            />
            <button
              type="button"
              onClick={handleRenameClick}
              disabled={isRenaming || !title.trim() || title.trim() === session.name}
              className="rounded-md  px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isRenaming ? "Renaming..." : "Rename Chat"}
            </button>
            <button
              type="button"
              onClick={() => onDeleteRequest(session)}
              className="rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
            >
              Delete Chat
            </button>
          </div>
          {renameNotice ? <p className="mt-2 text-sm ">{renameNotice}</p> : null}
        </Panel>

        <Panel title="History & memory">
          <p className="text-sm ">
            Clear Chat History hides the visible transcript and graphs, but keeps the hidden memory
            available for follow-up questions. Clear Chat Memory removes both visible history and
            saved memory for this chat.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => onClearRequest(session, "history")}
              disabled={isRunning}
              className="rounded-md border  px-4 py-2 text-sm font-semibold text-zinc-800 hover:sm-card disabled:cursor-not-allowed disabled:sm-card disabled:"
            >
              Clear Chat History
            </button>
            <button
              type="button"
              onClick={() => onClearRequest(session, "memory")}
              disabled={isRunning}
              className="rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled: disabled:sm-card disabled:"
            >
              Clear Chat Memory (Also History)
            </button>
          </div>
          {isRunning ? (
            <p className="mt-2 text-sm ">
              Clearing is disabled while this chat is working.
            </p>
          ) : null}
        </Panel>

        <Panel title="Sessions In Chat">
          {debates.length === 0 ? (
            <p className="text-sm ">
              No saved strategy statistics yet. New sessions will appear here as Session #1, Session #2,
              and so on.
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-sm ">
                Rename or delete saved statistics for sessions in this chat. Deleting a session here
                removes only its graphs and statistics; the messages stay in Strategic Chats.
              </p>
              <div className=" border-y border-zinc-200">
                {debates.map((debate) => (
                  <DebateSettingsRow
                    key={debate.id}
                    debate={debate}
                    isRunning={isRunning}
                    onRename={onRenameDebate}
                    onDelete={() => onDeleteDebateRequest(session, debate)}
                  />
                ))}
              </div>
            </div>
          )}
        </Panel>

        {session.mode === "ai_vs_human" ? (
          <Panel title="Practice Training">
            <div className="grid gap-3 md:grid-cols-3">
              <SelectSetting
                label="Human side default"
                value={settings.practice_settings.human_side}
                options={["Auto", "Alpha", "Beta"]}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      human_side: value as SessionSettings["practice_settings"]["human_side"]
                    }
                  })
                }
              />
              <SelectSetting
                label="Practice flow"
                value={settings.practice_settings.practice_flow}
                options={["Free", "Structured"]}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      practice_flow: value as SessionSettings["practice_settings"]["practice_flow"]
                    }
                  })
                }
              />
              {settings.practice_settings.practice_flow === "Structured" ? (
                <NumberSetting
                  label="Structured rounds"
                  value={settings.practice_settings.structured_rounds}
                  min={1}
                  max={12}
                  onChange={(value) =>
                    onSettingsChange({
                      practice_settings: {
                        ...settings.practice_settings,
                        structured_rounds: value
                      }
                    })
                  }
                />
              ) : null}
              <SelectSetting
                label="Opponent difficulty"
                value={settings.practice_settings.opponent_difficulty}
                options={["Adaptive", "Beginner", "Normal", "Hard"]}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      opponent_difficulty: value as SessionSettings["practice_settings"]["opponent_difficulty"]
                    }
                  })
                }
              />
              <SelectSetting
                label="Training focus"
                value={settings.practice_settings.training_focus}
                options={["Full Debate", "Rebuttal", "Evidence", "Clarity", "Cross-Examination"]}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      training_focus: value as SessionSettings["practice_settings"]["training_focus"]
                    }
                  })
                }
              />
              <SelectSetting
                label="Trainer style"
                value={settings.practice_settings.trainer_style}
                options={["Coach", "Direct", "Gentle", "Examiner"]}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      trainer_style: value as SessionSettings["practice_settings"]["trainer_style"]
                    }
                  })
                }
              />
              <ToggleSetting
                label="Use User Debate Profile"
                value={settings.practice_settings.use_user_profile}
                onChange={(value) =>
                  onSettingsChange({
                    practice_settings: {
                      ...settings.practice_settings,
                      use_user_profile: value
                    }
                  })
                }
              />
            </div>
            {practiceState?.active ? (
              <p className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm ">
                Current practice debate: you are {(practiceState.human_side || "").toUpperCase()}.
                {practiceState.practice_flow === "Structured"
                  ? ` ${practiceState.rounds_left ?? 0} round(s) left.`
                  : " Free debate is active."}
              </p>
            ) : null}
          </Panel>
        ) : null}

        {session.mode !== "ai_vs_human" ? (
        <Panel title="Simulation Flow">
          <div className="grid gap-3 md:grid-cols-2">
            <SelectSetting
              label="Agents amount per cluster"
              value={String(settings.debaters_per_team)}
              options={["1", "2", "3", "4"]}
              onChange={(value) => onSettingsChange({ debaters_per_team: Number(value) })}
            />
            <NumberSetting
              label="Discussion Messages Per Team"
              value={settings.discussion_messages_per_team}
              min={1}
              max={4}
              onChange={(value) => onSettingsChange({ discussion_messages_per_team: value })}
            />
            <NumberSetting
              label="Simulation rounds"
              value={settings.debate_rounds}
              min={1}
              max={6}
              onChange={(value) => onSettingsChange({ debate_rounds: value })}
            />
          </div>
          <div className="mt-3 rounded-md sm-card p-3 text-sm ">
            <p className="font-semibold ">Flow preview</p>
            <p className="mt-1">{flowPreview(settings.debaters_per_team)}</p>
            <p className="mt-2 text-xs ">
              Discussion Time uses Advocates only. They speak for the whole team and use previous
              Researcher, Critic, and Examiner material when those roles are active. Simulation rounds
              controls how many advocate-led discussion phases are included.
            </p>
          </div>
        </Panel>
        ) : null}

        {session.mode !== "ai_vs_human" ? (
        <Panel title="Agents & Clusters">
          <div className="grid gap-3 md:grid-cols-2">
            <ToggleSetting
              label="Judge Assistant, highly recommended"
              value={settings.judge_assistant_enabled}
              onChange={(value) => onSettingsChange({ judge_assistant_enabled: value })}
            />
            <label className="text-sm font-medium  md:col-span-2">
              Overall model
              <select
                value={selectedModelName}
                onChange={(event) => onModelChange(event.target.value)}
                disabled={unlockedModels.length === 0}
                className="mt-1 h-11 w-full rounded-md sm-card px-3 disabled:cursor-not-allowed disabled:sm-card"
              >
                {unlockedModels.length === 0 ? <option value="">No unlocked models</option> : null}
                {unlockedModels.map((model) => (
                  <option key={model.name} value={model.name}>
                    {model.name}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs font-normal ">
                Used when an individual agent keeps model set to default.
              </span>
            </label>
          </div>

          <div className="mt-4 space-y-4">
            <div>
              <h4 className="text-sm font-semibold ">Shared team roles</h4>
              <p className="text-sm ">
                These settings apply equally to the Alpha and Beta version of each role.
              </p>
              <div className="mt-2  border-y border-zinc-200">
                {visibleTeamRoles.map((role) => (
                  <AgentSettingsRow
                    key={role.key}
                    roleKey={role.key}
                    label={role.label}
                    description={role.description}
                    settings={settings}
                    unlockedModels={unlockedModels}
                    selectedModelName={selectedModelName}
                    onChange={updateAgentSetting}
                    showWebSearch={role.key === "evidence_researcher"}
                  />
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold ">Neutral roles</h4>
              <p className="text-sm ">
                These settings affect only the single neutral agent shown here.
              </p>
              <div className="mt-2  border-y border-zinc-200">
                {visibleNeutralRoles.map((role) => (
                  <AgentSettingsRow
                    key={role.key}
                    roleKey={role.key}
                    label={role.label}
                    description={role.description}
                    settings={settings}
                    unlockedModels={unlockedModels}
                    selectedModelName={selectedModelName}
                    onChange={updateAgentSetting}
                  />
                ))}
              </div>
            </div>
          </div>
        </Panel>
        ) : (
          <Panel title="Practice Agents">
            <p className="mb-3 text-sm ">
              AI Strategist argues against you. Judge and Judge Assistant evaluate the debate, then Strategy Coach coaches you.
            </p>
            <div className=" border-y border-zinc-200">
              <AgentSettingsRow
                roleKey="practice_debater"
                label="AI Strategist"
                description="The AI opponent in Human Debate Training."
                settings={settings}
                unlockedModels={unlockedModels}
                selectedModelName={selectedModelName}
                onChange={updateAgentSetting}
              />
              <AgentSettingsRow
                roleKey="debate_trainer"
                label="Strategy Coach"
                description="The coach that reviews the debate after Judge gives a verdict."
                settings={settings}
                unlockedModels={unlockedModels}
                selectedModelName={selectedModelName}
                onChange={updateAgentSetting}
              />
              {visibleNeutralRoles.map((role) => (
                <AgentSettingsRow
                  key={role.key}
                  roleKey={role.key}
                  label={role.label}
                  description={role.description}
                  settings={settings}
                  unlockedModels={unlockedModels}
                  selectedModelName={selectedModelName}
                  onChange={updateAgentSetting}
                />
              ))}
            </div>
          </Panel>
        )}

        <Panel title="Council Assistant">
          <p className="mb-3 text-sm ">
            This is the normal chat agent. When Always On is off, the router decides whether the
            Council Assistant or the simulated agents should respond.
          </p>
          <AgentSettingsRow
            roleKey="council_assistant"
            label="Council Assistant"
            description="Answers normal chat messages and follow-up questions using this chat's memory."
            settings={settings}
            unlockedModels={unlockedModels}
            selectedModelName={selectedModelName}
            onChange={updateAgentSetting}
            showAlwaysOn
          />
        </Panel>

        <Panel title="Strategic Intelligence">
          <p className="mb-3 text-sm ">
            These settings decide how this chat uses real experience and how strict the Judge should be with the tracked debate objects.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <ToggleSetting
              label="Use Experience"
              value={settings.use_experience}
              onChange={(value) => onSettingsChange({ use_experience: value })}
            />
            <SelectSetting
              label="Judge Mode"
              value={settings.judge_mode}
              options={["Debate Performance", "Truth-Seeking", "Hybrid"]}
              onChange={(value) => onSettingsChange({ judge_mode: value })}
            />
            <SelectSetting
              label="Evidence Strictness"
              value={settings.evidence_strictness}
              options={["Relaxed", "Normal", "Strict"]}
              onChange={(value) => onSettingsChange({ evidence_strictness: value })}
            />
          </div>
          <p className="mt-3 text-xs ">
            Turning experience off only affects this chat. Universal experience scope is controlled from Council Settings.
          </p>
        </Panel>

        <Panel title="Judgment Quality">
          <p className="mb-3 text-sm ">
            Use a judge panel when verdict quality matters more than speed. Analytics weighting
            lets tracked claims, challenges, evidence, and stance signals slightly influence the final call.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <SelectSetting
              label="Judge Panel Size"
              value={String(settings.judging_settings.judge_panel_size)}
              options={["1", "3", "5"]}
              onChange={(value) =>
                onSettingsChange({
                  judging_settings: {
                    ...settings.judging_settings,
                    judge_panel_size: Number(value) as 1 | 3 | 5
                  }
                })
              }
            />
            <SelectSetting
              label="Analytics Weight"
              value={String(settings.judging_settings.analytics_weight)}
              options={["0", "0.15", "0.25", "0.4", "0.6", "0.75"]}
              onChange={(value) =>
                onSettingsChange({
                  judging_settings: {
                    ...settings.judging_settings,
                    analytics_weight: Number(value)
                  }
                })
              }
            />
            <ToggleSetting
              label="Allow Verdict Challenge / Override"
              value={settings.judging_settings.allow_user_verdict_challenge}
              onChange={(value) =>
                onSettingsChange({
                  judging_settings: {
                    ...settings.judging_settings,
                    allow_user_verdict_challenge: value
                  }
                })
              }
            />
          </div>
          <p className="mt-3 text-xs ">
            1 judge is fastest. 3 or 5 judges cost more because each panelist makes an independent model call.
          </p>
        </Panel>

        <Panel title="Prompt & tone">
          <div className="grid gap-3 md:grid-cols-2">
            <SelectSetting
              label="Reasoning tone"
              value={settings.debate_tone}
              options={["Academic", "Casual", "Formal", "Aggressive"]}
              onChange={(value) => onSettingsChange({ debate_tone: value })}
            />
            <SelectSetting
              label="Language"
              value={settings.language}
              options={["English", "Chinese", "Cantonese"]}
              onChange={(value) => onSettingsChange({ language: value })}
            />
          </div>
        </Panel>

        <VoiceSettingsSubPanel />

        <Panel title="Output & display">
          <div className="grid gap-3 md:grid-cols-3">
            <ToggleSetting
              label="Auto-scroll"
              value={settings.auto_scroll}
              onChange={(value) => onSettingsChange({ auto_scroll: value })}
            />
            <ToggleSetting
              label="Show timestamps"
              value={settings.show_timestamps}
              onChange={(value) => onSettingsChange({ show_timestamps: value })}
            />
            <ToggleSetting
              label="Show token count"
              value={settings.show_token_count}
              onChange={(value) => onSettingsChange({ show_token_count: value })}
            />
            <ToggleSetting
              label="Show money cost"
              value={settings.show_money_cost}
              onChange={(value) => onSettingsChange({ show_money_cost: value })}
            />
            {settings.show_money_cost ? (
              <>
                <SelectSetting
                  label="Dollar type"
                  value={settings.cost_currency}
                  options={costCurrencies}
                  onChange={(value) => onSettingsChange({ cost_currency: value })}
                />
                <ToggleSetting
                  label="Show cost of every model"
                  value={settings.show_model_costs}
                  onChange={(value) => onSettingsChange({ show_model_costs: value })}
                />
                <ToggleSetting
                  label="Show Every Message Cost In Simulation"
                  value={settings.show_every_message_cost_in_debate}
                  onChange={(value) =>
                    onSettingsChange({ show_every_message_cost_in_debate: value })
                  }
                />
              </>
            ) : null}
          </div>
        </Panel>

        <Panel title="Advanced">
          <div className="grid gap-3 md:grid-cols-3">
            <NumberSetting
              label="Context window"
              value={settings.context_window}
              min={0}
              max={6}
              onChange={(value) => onSettingsChange({ context_window: value })}
            />
            <SelectSetting
              label="Export format"
              value={settings.export_format}
              options={["Markdown", "PDF", "JSON"]}
              onChange={(value) => onSettingsChange({ export_format: value })}
            />
            <NumberSetting
              label="Auto-save interval"
              value={settings.auto_save_interval}
              min={5}
              max={300}
              onChange={(value) => onSettingsChange({ auto_save_interval: value })}
            />
            <ToggleSetting
              label="Fact-check mode"
              value={settings.fact_check_mode}
              onChange={(value) => onSettingsChange({ fact_check_mode: value })}
            />
          </div>
          <div className="mt-3">
            <button
              type="button"
              onClick={handleExport}
              className="rounded-md border  px-4 py-2 text-sm font-semibold text-zinc-800 hover:sm-card"
            >
              Export Current Debate
            </button>
          </div>
          <p className="mt-3 text-sm ">
            Fact-check mode is saved as a chat setting and reserved for provider/tool integration.
            Export uses the selected format: Markdown downloads directly, JSON downloads structured data,
            and PDF opens a print dialog you can save as PDF.
          </p>
        </Panel>
      </div>
    </section>
  );
}

function VoiceSettingsSubPanel() {
  const { settings, updateSettings, isLoaded } = useVoiceSettings();
  if (!isLoaded) return null;
  return (
    <Panel title="Voice Interaction">
      <p className="mb-3 text-sm">
        Configure the voice interaction system for hands-free reasoning and synthesis playback.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <ToggleSetting
          label="Enable Voice Input & Synthesis"
          value={settings.enabled}
          onChange={(value) => updateSettings({ enabled: value })}
        />
        <ToggleSetting
          label="Auto-Play AI Responses"
          value={settings.autoPlay}
          onChange={(value) => updateSettings({ autoPlay: value })}
        />
        <SelectSetting
          label="Provider"
          value={settings.provider}
          options={["browser", "google"]}
          onChange={(value) => updateSettings({ provider: value as "browser" | "google" })}
        />
        {settings.provider === "google" && (
          <SelectSetting
            label="Google Voice"
            value={settings.googleVoice}
            options={[
              "en-US-Journey-F",
              "en-US-Journey-D",
              "en-US-Journey-O",
              "en-US-Standard-A",
              "en-US-Standard-B",
              "en-US-Standard-C",
              "en-US-Standard-D",
              "en-US-Standard-E",
              "en-US-Standard-F",
              "en-US-Standard-G",
              "en-US-Standard-H",
              "en-US-Standard-I",
              "en-US-Standard-J"
            ]}
            onChange={(value) => updateSettings({ googleVoice: value })}
          />
        )}
        <SelectSetting
          label="Playback Speed"
          value={settings.playbackSpeed.toString()}
          options={["0.8", "1", "1.2", "1.5", "2"]}
          onChange={(value) => updateSettings({ playbackSpeed: parseFloat(value) })}
        />
      </div>
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      className="rounded-2xl p-6"
      style={{
        background: 'var(--sm-bg-secondary)',
        border: '1px solid var(--sm-border)',
      }}
    >
      <h3
        className="mb-4 text-xs font-bold uppercase tracking-widest"
        style={{ color: 'var(--sm-text-muted)' }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function flowPreview(debaters_per_team: number) {
  if (debaters_per_team <= 1) {
    return "Constructives, cross-examination, answer + rebuttal turns, one Open Discussion with Alpha-open and Beta-open mini-rounds, closings, audit, verdict.";
  }
  if (debaters_per_team === 2) {
    return "Advocates build the cases, Critics cross-examine and rebut, Discussion Time 1 opens with Alpha Advocate, Discussion Time 2 opens with Beta Advocate, then closings, audit, verdict.";
  }
  if (debaters_per_team === 3) {
    return "Advocates frame the cases, Researchers add evidence, Critics rebut, two Advocate-led Discussion Time phases balance Alpha and Beta opening order, then closings, audit, verdict.";
  }
  return "Advocates open and close, Examiners pressure-test Advocates and Researchers, Researchers add evidence, Critics rebut, and two Advocate-led Discussion Time phases balance both teams.";
}

function DebateSettingsRow({
  debate,
  isRunning,
  onRename,
  onDelete
}: {
  debate: DebateRecord;
  isRunning: boolean;
  onRename: (debate: DebateRecord, name: string) => Promise<boolean>;
  onDelete: () => void;
}) {
  const [name, setName] = useState(debate.name);
  const [notice, setNotice] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);

  useEffect(() => {
    setName(debate.name);
    setNotice(null);
  }, [debate.id, debate.name]);

  const handleRename = async () => {
    setNotice(null);
    setIsRenaming(true);
    const saved = await onRename(debate, name);
    setIsRenaming(false);
    if (saved) {
      setNotice("Debate name updated.");
    }
  };

  return (
    <div className="py-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <input
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setNotice(null);
            }}
            className="h-10 w-full rounded-md border  px-3 text-sm"
            aria-label={`Rename ${debate.name}`}
          />
          <p className="mt-1 truncate text-xs " title={debate.topic}>
            {debate.topic}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRename}
          disabled={isRunning || isRenaming || !name.trim() || name.trim() === debate.name}
          className="rounded-md  px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRenaming ? "Renaming..." : "Rename"}
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={isRunning}
          className="rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled: disabled:sm-card disabled:"
        >
          Delete Statistics
        </button>
      </div>
      {notice ? <p className="mt-1 text-sm ">{notice}</p> : null}
    </div>
  );
}

function AgentSettingsRow({
  roleKey,
  label,
  description,
  settings,
  unlockedModels,
  selectedModelName,
  onChange,
  showWebSearch = false,
  showAlwaysOn = false
}: {
  roleKey: string;
  label: string;
  description: string;
  settings: SessionSettings;
  unlockedModels: SupportedModel[];
  selectedModelName: string;
  onChange: (
    roleKey: string,
    updates: Partial<SessionSettings["agent_settings"][string]>
  ) => void;
  showWebSearch?: boolean;
  showAlwaysOn?: boolean;
}) {
  const agent = settings.agent_settings[roleKey] ?? {
    model: "",
    temperature: settings.temperature,
    max_tokens: settings.max_tokens,
    response_length: settings.response_length,
    web_search: false,
    always_on: false
  };

  return (
    <div className="py-4">
      <div className="mb-3">
        <p className="font-semibold ">{label}</p>
        <p className="text-sm ">{description}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-medium ">
          Model
          <select
            value={agent.model}
            onChange={(event) => onChange(roleKey, { model: event.target.value })}
            className="mt-1 h-11 w-full rounded-md sm-card px-3"
          >
            <option value="">Use overall model ({selectedModelName || "none"})</option>
            {unlockedModels.map((model) => (
              <option key={model.name} value={model.name}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
        <SelectSetting
          label="Response length"
          value={agent.response_length}
          options={["Concise", "Normal", "Detailed"]}
          onChange={(value) => onChange(roleKey, { response_length: value })}
        />
        <RangeSetting
          label="Temperature"
          value={agent.temperature}
          min={0}
          max={1}
          step={0.05}
          onChange={(value) => onChange(roleKey, { temperature: value })}
        />
        <NumberSetting
          label="Max tokens"
          value={agent.max_tokens}
          min={120}
          max={2000}
          onChange={(value) => onChange(roleKey, { max_tokens: value })}
        />
        {showWebSearch ? (
          <ToggleSetting
            label="Web search for researchers"
            value={agent.web_search}
            onChange={(value) => onChange(roleKey, { web_search: value })}
          />
        ) : null}
        {showAlwaysOn ? (
          <div>
            <ToggleSetting
              label="Always On, off highly recommended"
              value={agent.always_on}
              onChange={(value) => onChange(roleKey, { always_on: value })}
            />
            <p className="mt-1 text-xs ">
              When on, this chat always uses the Council Assistant, even for debate-like messages.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl p-5"
      style={{ background: 'var(--sm-bg-secondary)', border: '1px solid var(--sm-border)' }}
    >
      <div
        className="absolute inset-x-0 top-0 h-0.5 rounded-full"
        style={{ background: 'linear-gradient(90deg, rgba(99,102,241,0.7), rgba(6,182,212,0.4))' }}
      />
      <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--sm-text-muted)' }}>
        {label}
      </p>
      <p className="mt-2 truncate text-lg font-bold" style={{ color: 'var(--sm-text-primary)' }}>
        {value}
      </p>
    </div>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  const width = `${Math.max(1, Math.min(100, value * 100))}%`;
  return (
    <div className="mb-3 group relative">
      <div className="mb-1.5 flex justify-between gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-400 group-hover:text-cyan-400 transition-colors">
        <span className="truncate">{label}</span>
        <span className="font-mono text-cyan-400">{toPercent(value)}</span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-white/5 border border-white/5 shadow-inner">
        <div 
          className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.5)] transition-all duration-1000 ease-out" 
          style={{ width }} 
        >
          <div className="absolute inset-0 bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.4)_50%,transparent_100%)] w-[200%] animate-[slide_2s_linear_infinite]" />
        </div>
      </div>
    </div>
  );
}

function ValueBar({
  label,
  value,
  max,
  formatted
}: {
  label: string;
  value: number;
  max: number;
  formatted: string;
}) {
  const width = `${Math.max(1, Math.min(100, (value / Math.max(max, 1e-9)) * 100))}%`;
  return (
    <div className="mb-3 group relative">
      <div className="mb-1.5 flex justify-between gap-2 text-[11px] font-bold uppercase tracking-widest text-slate-400 group-hover:text-cyan-400 transition-colors">
        <span className="truncate" title={label}>{label}</span>
        <span className="shrink-0 font-mono text-cyan-400">{formatted}</span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-white/5 border border-white/5 shadow-inner">
        <div 
          className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.5)] transition-all duration-1000 ease-out" 
          style={{ width }} 
        >
          <div className="absolute inset-0 bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.4)_50%,transparent_100%)] w-[200%] animate-[slide_2s_linear_infinite]" />
        </div>
      </div>
    </div>
  );
}

function PieChart({ values }: { values: Record<string, number> }) {
  const support = Math.round((values.support ?? 0) * 100);
  const oppose = Math.round((values.oppose ?? 0) * 100);
  const mixed = Math.max(0, 100 - support - oppose);
  const background = `conic-gradient(from 0deg, #22d3ee 0 ${support}%, #f43f5e ${support}% ${
    support + oppose
  }%, #6366f1 ${support + oppose}% 100%)`;
  
  return (
    <div className="flex flex-col sm:flex-row items-center gap-8 py-4">
      <div className="relative group perspective-1000">
        <div className="absolute inset-0 rounded-full bg-cyan-500/20 blur-xl group-hover:bg-cyan-400/30 transition-all duration-500 sm-animate-pulse-glow" />
        <div 
          className="relative h-40 w-40 rounded-full shadow-[inset_0_0_20px_rgba(0,0,0,0.5)] transition-transform duration-500 group-hover:scale-105 group-hover:rotate-3" 
          style={{ background, border: '4px solid rgba(255,255,255,0.05)' }} 
        >
          <div className="absolute inset-[15%] rounded-full bg-[var(--sm-bg-secondary)] shadow-[0_0_15px_rgba(0,0,0,0.6)] flex items-center justify-center">
            <span className="font-mono text-xl font-bold text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]">{support}%</span>
          </div>
        </div>
      </div>
      <div className="space-y-3 w-full sm:w-auto">
        <Legend color="bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.5)]" label="Alpha Resonance" value={support} />
        <Legend color="bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.5)]" label="Beta Friction" value={oppose} />
        <Legend color="bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.5)]" label="Neutral State" value={mixed} />
      </div>
    </div>
  );
}

function MultiPieChart({ entries, unit }: { entries: Array<[string, number]>; unit: string }) {
  const colors = ["#22d3ee", "#f43f5e", "#6366f1", "#f59e0b", "#94a3b8"];
  const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
  let cursor = 0;
  const stops = entries.map(([, value], index) => {
    const start = cursor;
    cursor += (value / total) * 100;
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  return (
    <div className="flex flex-col gap-6 sm:flex-row sm:items-center py-4">
      <div className="relative group">
        <div className="absolute inset-0 rounded-full bg-indigo-500/20 blur-xl transition-all duration-500 group-hover:blur-2xl" />
        <div 
          className="relative h-40 w-40 shrink-0 rounded-full shadow-[inset_0_0_20px_rgba(0,0,0,0.5)] transition-transform duration-500 group-hover:scale-105 group-hover:-rotate-3" 
          style={{ background: `conic-gradient(from 0deg, ${stops.join(", ")})`, border: '4px solid rgba(255,255,255,0.05)' }} 
        >
          <div className="absolute inset-[20%] rounded-full bg-[var(--sm-bg-secondary)] shadow-[0_0_15px_rgba(0,0,0,0.6)]" />
        </div>
      </div>
      <div className="space-y-3">
        {entries.map(([label, value], index) => (
          <div key={label} className="flex items-center gap-3 group">
            <span className="h-3 w-3 rounded-sm shadow-md transition-transform group-hover:scale-125" style={{ backgroundColor: colors[index % colors.length], boxShadow: `0 0 8px ${colors[index % colors.length]}` }} />
            <span className="font-mono text-xs uppercase tracking-wider text-slate-300 group-hover:text-white transition-colors">
              {label}: <strong className="text-cyan-400">{value}</strong> {unit}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Legend({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 group">
      <span className={`h-3 w-3 rounded-sm ${color} shadow-sm transition-transform group-hover:scale-125`} />
      <span className="font-mono text-xs uppercase tracking-widest text-slate-400 group-hover:text-white transition-colors">
        {label}: <strong className="text-cyan-400">{value}%</strong>
      </span>
    </div>
  );
}

function LineChart({ history }: { history: DebateAnalytics[] }) {
  const labels = ["support", "oppose", "mixed"] as const;
  const colors = { support: "#22d3ee", oppose: "#f43f5e", mixed: "#6366f1" };
  const width = 640;
  const height = 240;
  const padLeft = 44;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 36;
  const latest = history[history.length - 1];
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const tickStep = Math.max(1, Math.ceil(history.length / 8));
  const xTicks = history
    .map((_, index) => index)
    .filter(
      (index) =>
        index === 0 ||
        index === history.length - 1 ||
        (index + 1) % tickStep === 0
    );

  const pathFor = (label: (typeof labels)[number]) =>
    history
      .map((item, index) => {
        const x = padLeft + (index / Math.max(1, history.length - 1)) * plotWidth;
        const y = height - padBottom - (item.bayesian.probabilities[label] ?? 0) * plotHeight;
        if (index === 0) return `M${x.toFixed(1)},${y.toFixed(1)}`;
        const prevX = padLeft + ((index - 1) / Math.max(1, history.length - 1)) * plotWidth;
        const prevY = height - padBottom - (history[index - 1].bayesian.probabilities[label] ?? 0) * plotHeight;
        const cp1x = prevX + (x - prevX) * 0.5;
        return `C${cp1x.toFixed(1)},${prevY.toFixed(1)} ${cp1x.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  const areaFor = (label: (typeof labels)[number], path: string) => {
    return `${path} L${padLeft + plotWidth},${height - padBottom} L${padLeft},${height - padBottom} Z`;
  };

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 min-w-[520px]">
        <defs>
          <linearGradient id="support-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="oppose-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="mixed-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        {/* Grid Lines */}
        <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} stroke="rgba(255,255,255,0.2)" strokeWidth="2" />
        <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} stroke="rgba(255,255,255,0.1)" />
        
        {[0.25, 0.5, 0.75].map((tick) => (
          <g key={tick}>
            <line x1={padLeft} y1={height - padBottom - tick * plotHeight} x2={width - padRight} y2={height - padBottom - tick * plotHeight} stroke="rgba(255,255,255,0.05)" strokeDasharray="4 4" />
            <text x={padLeft - 10} y={height - padBottom - tick * plotHeight + 4} textAnchor="end" fontSize="9" fontFamily="monospace" fill="#94a3b8">
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}

        {xTicks.map((index) => {
          const tick = index + 1;
          const x = padLeft + (index / Math.max(1, history.length - 1)) * plotWidth;
          return (
            <g key={tick}>
              <line x1={x} y1={height - padBottom} x2={x} y2={height - padBottom + 4} stroke="rgba(255,255,255,0.2)" />
              <text x={x} y={height - padBottom + 16} textAnchor="middle" fontSize="9" fontFamily="monospace" fill="#94a3b8">
                {tick}
              </text>
            </g>
          );
        })}

        <text x={width / 2} y={height - 4} textAnchor="middle" fontSize="9" fontFamily="monospace" letterSpacing="0.1em" fill="#64748b">
          NEURAL MATRIX TICKS
        </text>
        <text x={12} y={height / 2} textAnchor="middle" fontSize="9" fontFamily="monospace" letterSpacing="0.1em" fill="#64748b" transform={`rotate(-90 12 ${height / 2})`}>
          LOGIC PROBABILITY
        </text>

        {/* Data Paths */}
        {labels.map((label) => {
          const pathStr = pathFor(label);
          return (
            <g key={label}>
              <path d={areaFor(label, pathStr)} fill={`url(#${label}-grad)`} />
              <path
                d={pathStr}
                fill="none"
                stroke={colors[label]}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                filter="url(#glow)"
                className="animate-[dash_2s_linear_forwards] [stroke-dasharray:1000] [stroke-dashoffset:1000]"
              />
              {/* Data points */}
              {history.map((item, index) => {
                const x = padLeft + (index / Math.max(1, history.length - 1)) * plotWidth;
                const y = height - padBottom - (item.bayesian.probabilities[label] ?? 0) * plotHeight;
                return (
                  <circle key={index} cx={x} cy={y} r="3" fill="var(--sm-bg-secondary)" stroke={colors[label]} strokeWidth="1.5" className="transition-all duration-300 hover:r-[5px] hover:stroke-[3px]" />
                );
              })}
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap justify-center gap-6">
        <Legend color="bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.5)]" label="Alpha Resonance" value={Math.round((latest?.bayesian.probabilities.support ?? 0) * 100)} />
        <Legend color="bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]" label="Beta Friction" value={Math.round((latest?.bayesian.probabilities.oppose ?? 0) * 100)} />
        <Legend color="bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]" label="Neutral State" value={Math.round((latest?.bayesian.probabilities.mixed ?? 0) * 100)} />
      </div>
    </div>
  );
}

function SelectSetting({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm font-medium ">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-11 w-full rounded-md sm-card px-3"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumberSetting({
  label,
  value,
  min,
  max,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commit = (raw: string) => {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(String(value));
      return;
    }
    const clamped = Math.max(min, Math.min(max, Math.round(parsed)));
    setDraft(String(clamped));
    if (clamped !== value) {
      onChange(clamped);
    }
  };

  return (
    <label className="text-sm font-medium ">
      {label}
      <input
        type="number"
        min={min}
        max={max}
        value={draft}
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          if (!next.trim() || next === "-" || next === "+") {
            return;
          }
          const parsed = Number(next);
          if (!Number.isFinite(parsed)) {
            return;
          }
          const rounded = Math.round(parsed);
          if (rounded >= min && rounded <= max && rounded !== value) {
            onChange(rounded);
          }
        }}
        onBlur={() => commit(draft)}
        className="mt-1 h-11 w-full rounded-md border  px-3"
      />
    </label>
  );
}

function RangeSetting({
  label,
  value,
  min,
  max,
  step,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-sm font-medium ">
      {label}: {value.toFixed(2)}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => {
          const parsed = Number(event.target.value);
          if (Number.isFinite(parsed)) {
            onChange(Math.max(min, Math.min(max, parsed)));
          }
        }}
        className="mt-3 w-full"
      />
    </label>
  );
}

function ToggleSetting({
  label,
  value,
  onChange
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-md border  px-3 py-3 text-sm font-medium ">
      {label}
      <input
        type="checkbox"
        checked={value}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5"
      />
    </label>
  );
}

export function MarkdownText({ text }: { text: string }) {
  const lines = text.split(/\n/);
  const elements: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  let ordered = false;

  const flushList = () => {
    if (listItems.length === 0) {
      return;
    }
    const ListTag = ordered ? "ol" : "ul";
    elements.push(
      <ListTag key={`list-${elements.length}`} className={`mt-3 ${ordered ? "list-decimal" : "list-disc"} pl-6 text-[15px] leading-relaxed text-[var(--sm-text-secondary)]`}>
        {listItems}
      </ListTag>
    );
    listItems = [];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushList();
      const size = heading[1].length === 1 ? "text-lg" : "text-base";
      elements.push(
        <h4 key={index} className={`mt-4 font-bold text-[var(--sm-text-primary)] ${size}`}>
          {renderInline(heading[2])}
        </h4>
      );
      return;
    }
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      if (listItems.length > 0 && ordered !== Boolean(numbered)) {
        flushList();
      }
      ordered = Boolean(numbered);
      listItems.push(<li key={index}>{renderInline((bullet ?? numbered)?.[1] ?? trimmed)}</li>);
      return;
    }
    flushList();
    elements.push(
      <p key={index} className="mt-3 whitespace-pre-wrap text-[15px] leading-relaxed text-[var(--sm-text-secondary)]">
        {renderInline(trimmed)}
      </p>
    );
  });
  flushList();

  return <div className="mt-3">{elements}</div>;
}

function renderInline(text: string) {
  const segments: ReactNode[] = [];
  const pattern = /(\*\*[^*]+?\*\*|\*(?!\s)[^*]+?\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(text.slice(lastIndex, match.index));
    }
    const value = match[0];
    if (value.startsWith("**") && value.endsWith("**")) {
      segments.push(<strong key={`strong-${index}`}>{value.slice(2, -2)}</strong>);
    } else if (value.startsWith("*") && value.endsWith("*")) {
      segments.push(<em key={`em-${index}`}>{value.slice(1, -1)}</em>);
    } else {
      segments.push(value);
    }
    lastIndex = match.index + value.length;
    index += 1;
  }
  if (lastIndex < text.length) {
    segments.push(text.slice(lastIndex));
  }
  return segments.length > 0 ? segments : text;
}

export function estimateTokens(text: string) {
  if (!text.trim()) {
    return 0;
  }
  const cjkPattern = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af\u{20000}-\u{2fa1f}]/gu;
  const cjkChars = (text.match(cjkPattern) ?? []).length;
  const withoutCjk = text.replace(cjkPattern, " ");
  const wordish = (withoutCjk.match(/[A-Za-z0-9_]+|[^\sA-Za-z0-9_]/g) ?? []).length;
  return Math.max(1, Math.ceil(cjkChars * 1.6 + wordish * 1.3));
}

function formatCost(value: number, currency: string) {
  const symbols: Record<string, string> = {
    USD: "$",
    CNY: "¥",
    HKD: "HK$",
    EUR: "€",
    JPY: "¥",
    GBP: "£",
    AUD: "A$",
    CAD: "C$",
    SGD: "S$"
  };
  const raw = (currency || "USD").toUpperCase();
  const normalized = raw === "SGP" ? "SGD" : raw in symbols ? raw : "USD";
  const decimals = normalized === "JPY" ? 0 : 6;
  return `${symbols[normalized]}${Number(value || 0).toFixed(decimals)} ${normalized}`;
}

function formatDuration(seconds: number) {
  if (seconds >= 60) {
    return `${(seconds / 60).toFixed(1)} min`;
  }
  return `${seconds.toFixed(1)} sec`;
}

function safeFileStem(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    || "debate-export";
}

function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportPrintablePdf(markdown: string, title: string) {
  const printWindow = window.open("", "_blank", "noopener,noreferrer,width=960,height=720");
  if (!printWindow) {
    return false;
  }
  const html = `
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>${escapeHtml(title)}</title>
        <style>
          body { font-family: Arial, sans-serif; line-height: 1.6; padding: 32px; color: #18181b; }
          pre { white-space: pre-wrap; word-break: break-word; }
        </style>
      </head>
      <body>
        <h1>${escapeHtml(title)}</h1>
        <pre>${escapeHtml(markdown)}</pre>
      </body>
    </html>
  `;
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
  return true;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function exportAsMarkdown(payload: {
  exported_at: string;
  chat: ChatSession;
  debate: DebateRecord | null;
  settings: Record<string, unknown>;
  analytics: DebateAnalytics | null;
  intelligence: Record<string, unknown> | null;
  messages: DebateMessage[];
}) {
  const lines = [
    `# ${payload.chat.name}`,
  "",
    `Exported at: ${payload.exported_at}`,
    `Debate: ${payload.debate?.name ?? "Current chat"}`,
    `Topic: ${payload.debate?.topic ?? "N/A"}`,
  "",
  "## Settings",
  "```json",
    JSON.stringify(payload.settings, null, 2),
  "```",
  "",
  "## Messages",
  ];
  payload.messages.forEach((message) => {
    lines.push(
      `### ${message.speaker} (${message.role})`,
    "",
      message.content,
    ""
    );
  });
  if (payload.analytics) {
    lines.push("## Analytics", "```json", JSON.stringify(payload.analytics, null, 2), "```", "");
  }
  if (payload.intelligence) {
    lines.push(
    "## Strategic Intelligence",
    "```json",
      JSON.stringify(payload.intelligence, null, 2),
    "```",
    ""
    );
  }
  return lines.join("\n");
}

function toPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}
