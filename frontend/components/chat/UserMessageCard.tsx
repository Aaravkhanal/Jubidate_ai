"use client";

import type { DebateMessage, SessionSettings } from "@/types";
import { MarkdownText, estimateTokens } from "@/components/DebateRoom";

type UserMessageCardProps = {
  message: DebateMessage;
  settings: SessionSettings | null;
  pending?: boolean;
};

export function UserMessageCard({
  message,
  settings,
  pending = false
}: UserMessageCardProps) {
  return (
    <article
      className={`relative mb-6 ml-auto max-w-3xl sm-glass-card overflow-hidden rounded-2xl p-6 transition-all duration-500 border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 to-purple-500/5 shadow-[0_0_25px_rgba(6,182,212,0.08)] hover:border-cyan-400/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] ${
        pending ? "shadow-[0_0_40px_rgba(34,211,238,0.2)] ring-1 ring-cyan-500/30" : ""
      }`}
      style={{
        transform: pending ? 'translateY(-4px)' : 'translateY(0)',
      }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono text-[10px] font-bold shadow-lg bg-[linear-gradient(135deg,rgba(6,182,212,0.2),rgba(147,51,234,0.1))] text-white border border-cyan-500/30">
            HMN
            {pending && (
              <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-cyan-400 sm-animate-pulse-glow" />
            )}
          </div>
          <div>
            <h3 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-white flex items-center gap-2">
              {message.speaker || "You"}
              {pending && <span className="sm-typing-indicator ml-2"><span/><span/><span/></span>}
            </h3>
            <p className="font-mono text-[10px] tracking-[0.15em] mt-1 text-cyan-400">
              HUMAN OPERATOR
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[10px] font-medium">
          {settings?.show_timestamps && (
            <span className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-slate-400">
              {new Date(message.created_at || Date.now()).toLocaleTimeString()}
            </span>
          )}
          {settings?.show_token_count && (
            <span className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-slate-400">
              {estimateTokens(message.content)} tokens
            </span>
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
        <div className="absolute top-0 left-0 right-0 sm-streaming-bar bg-gradient-to-r from-cyan-400 to-purple-500" />
      )}

      <div className={`text-[15px] leading-relaxed text-slate-200 ${pending ? 'sm-streaming-cursor' : ''}`}>
        <MarkdownText text={message.content || "Defending logic node..."} />
      </div>
    </article>
  );
}
