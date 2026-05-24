"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { ChatSession } from "@/types";

export type SidebarWorkspaceView =
  | "session"
  | "aiExperiences"
  | "userProfile"
  | "councilSettings";

type SidebarProps = {
  sessions: ChatSession[];
  selectedId: string | null;
  maxSessions: number;
  workspaceView: SidebarWorkspaceView;
  onNew: () => void;
  onDeleteAll: () => void;
  onSelect: (id: string) => void;
  onHome: () => void;
  onAiExperiences: () => void;
  onUserProfile: () => void;
  onCouncilSettings: () => void;
};

export function Sidebar({
  sessions,
  selectedId,
  maxSessions,
  workspaceView,
  onNew,
  onDeleteAll,
  onSelect,
  onHome,
  onAiExperiences,
  onUserProfile,
  onCouncilSettings,
}: SidebarProps) {
  const limitReached = sessions.length >= maxSessions;
  const aiSessions = sessions.filter((session) => session.mode !== "ai_vs_human");
  const practiceSessions = sessions.filter((session) => session.mode === "ai_vs_human");

  return (
    <aside
      className="flex h-full w-full flex-col md:w-80"
      style={{
        background: "var(--sm-bg-secondary)",
        borderRight: "1px solid var(--sm-border)"
      }}
    >
      {/* ── Brand Header ── */}
      <div className="electron-drag p-5 relative overflow-hidden" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-cyan-500/5 pointer-events-none" />
        <div className="relative z-10 flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 border border-indigo-500/30">
              <span className="sm-orb h-2 w-2" />
            </div>
            <div>
              <h1 className="font-display text-lg font-black tracking-wider text-white">
                JUBIDATE
              </h1>
              <p className="text-[9px] font-mono tracking-widest text-indigo-400 uppercase">Strategic OS</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex items-center justify-between gap-3">
          <p className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
            {sessions.length}/{maxSessions} Active Nodes
          </p>
          <button
            type="button"
            onClick={onNew}
            disabled={limitReached}
            className="group relative flex items-center gap-2 rounded-md bg-white/5 border border-white/10 px-3 py-1.5 text-xs font-medium text-white transition-all hover:bg-white/10 disabled:opacity-50"
          >
            <span className="absolute -inset-1 rounded-md bg-gradient-to-r from-indigo-500/20 to-cyan-500/20 opacity-0 blur transition group-hover:opacity-100" />
            <svg className="relative z-10" width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="7" y1="2" x2="7" y2="12" /><line x1="2" y1="7" x2="12" y2="7" />
            </svg>
            <span className="relative z-10 font-mono tracking-wider">INITIALIZE</span>
          </button>
        </div>
        {sessions.length > 0 ? (
          <button
            type="button"
            onClick={onDeleteAll}
            className="group mt-4 flex w-full items-center gap-2 rounded-md bg-red-500/5 border border-red-500/10 px-3 py-2 text-[10px] font-mono uppercase tracking-widest text-red-400 transition-all hover:bg-red-500/10 hover:border-red-500/30"
          >
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M2 3h8M4.5 3V2a.5.5 0 01.5-.5h2a.5.5 0 01.5.5v1M9.5 3l-.4 6.5a1 1 0 01-1 .9H3.9a1 1 0 01-1-.9L2.5 3" />
            </svg>
            Purge All Nodes
          </button>
        ) : null}
      </div>

      {/* ── Session List ── */}
      <nav className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="mb-4">
          <SidebarNavButton
            label="Matrix Overview"
            icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M2.5 7.5L8 2.5l5.5 5v6H10v-4H6v4H2.5z" /></svg>}
            active={workspaceView === "session" && selectedId === null}
            onClick={onHome}
          />
        </div>

        {sessions.length === 0 && workspaceView === "session" && selectedId !== null ? (
          <p className="px-2 py-6 text-center text-sm" style={{ color: "var(--sm-text-muted)" }}>
            Create a session to begin.
          </p>
        ) : null}

        <SessionGroup
          title="Multi-Agent Simulation"
          icon="⚡"
          sessions={aiSessions}
          selectedId={workspaceView === "session" ? selectedId : null}
          onSelect={onSelect}
        />
        <SessionGroup
          title="Human-AI Alignment"
          icon="🎯"
          sessions={practiceSessions}
          selectedId={workspaceView === "session" ? selectedId : null}
          onSelect={onSelect}
        />

        <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--sm-border)" }}>
          <p
            className="mb-2 px-2 text-[10px] font-bold uppercase tracking-[0.15em]"
            style={{ color: "var(--sm-text-muted)" }}
          >
            System Core
          </p>
          <div className="space-y-1">
            <SidebarNavButton
              label="Agent Memory"
              icon={<NeuronIcon />}
              active={workspaceView === "aiExperiences"}
              onClick={onAiExperiences}
            />
            <SidebarNavButton
              label="Performance Matrix"
              icon={<ChartIcon />}
              active={workspaceView === "userProfile"}
              onClick={onUserProfile}
            />
          </div>
        </div>
      </nav>

      {/* ── Settings Footer ── */}
      <div className="p-3" style={{ borderTop: "1px solid var(--sm-border)" }}>
        <SidebarNavButton
          label="Command Center"
          icon={<GearIcon />}
          active={workspaceView === "councilSettings"}
          onClick={onCouncilSettings}
        />
      </div>
    </aside>
  );
}

/* ─── Sub-components ─── */

function SidebarNavButton({
  label,
  icon,
  active,
  onClick
}: {
  label: string;
  icon: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex w-full items-center gap-3 overflow-hidden rounded-md px-3 py-2.5 text-left transition-all duration-300 ${active
          ? 'bg-indigo-500/10 border border-indigo-500/20 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]'
          : 'bg-transparent border border-transparent hover:bg-white/[0.02] hover:border-white/[0.05]'
        }`}
    >
      {active && (
        <div className="absolute left-0 top-0 h-full w-[2px] bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
      )}
      <div className={`flex h-6 w-6 items-center justify-center rounded-md transition-all duration-300 ${active
          ? 'bg-indigo-500/20 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.2)]'
          : 'bg-white/5 text-slate-400 group-hover:text-slate-200 group-hover:bg-white/10'
        }`}>
        {icon}
      </div>
      <span className={`font-mono text-xs uppercase tracking-widest transition-colors duration-300 ${active ? 'text-white font-bold' : 'text-slate-400 group-hover:text-slate-200'
        }`}>
        {label}
      </span>
      {active && (
        <span className="ml-auto flex h-2 w-2 items-center justify-center">
          <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-cyan-400 opacity-75"></span>
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500"></span>
        </span>
      )}
    </button>
  );
}

function SessionGroup({
  title,
  icon,
  sessions,
  selectedId,
  onSelect
}: {
  title: string;
  icon: string;
  sessions: ChatSession[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (sessions.length === 0) {
    return null;
  }
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2 px-2">
        <span className="text-xs opacity-70">{icon}</span>
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-slate-500">
          {title}
        </p>
        <div className="ml-2 h-px flex-1 bg-white/5" />
      </div>
      <div className="space-y-1 px-1">
        <AnimatePresence mode="popLayout">
          {sessions.map((session) => {
            const selected = selectedId === session.id;
            return (
              <motion.div
                key={session.id}
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2 }}
              >
                <button
                  type="button"
                  onClick={() => onSelect(session.id)}
                  className={`group relative flex w-full items-center gap-2 overflow-hidden rounded-md px-3 py-2 text-left transition-all duration-300 ${selected
                      ? 'bg-white/10 border border-white/20'
                      : 'bg-transparent border border-transparent hover:bg-white/5'
                    }`}
                  title={session.name}
                >
                  <div className={`h-1.5 w-1.5 rounded-full transition-all duration-300 ${selected ? 'bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]' : 'bg-slate-600 group-hover:bg-slate-400'
                    }`} />
                  <span className={`truncate font-mono text-[11px] transition-colors duration-300 ${selected ? 'text-white font-bold tracking-wide' : 'text-slate-400 group-hover:text-slate-300'
                    }`}>
                    {session.name}
                  </span>
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ─── Icons ─── */

function NeuronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="3" />
      <line x1="8" y1="1" x2="8" y2="5" />
      <line x1="8" y1="11" x2="8" y2="15" />
      <line x1="1" y1="8" x2="5" y2="8" />
      <line x1="11" y1="8" x2="15" y2="8" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="4" y1="14" x2="4" y2="8" />
      <line x1="8" y1="14" x2="8" y2="4" />
      <line x1="12" y1="14" x2="12" y2="6" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="2.5" />
      <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M3.2 12.8l1.4-1.4M11.4 4.6l1.4-1.4" />
    </svg>
  );
}
