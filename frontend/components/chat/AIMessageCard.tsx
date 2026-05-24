"use client";

import { useEffect } from "react";
import type { DebateMessage, SessionSettings } from "@/types";
import { MarkdownText, estimateTokens, MessageCosts } from "@/components/DebateRoom";
import { useVoiceSettings, useVoiceSynthesis } from "@/hooks/useVoice";

type AIMessageCardProps = {
  message: DebateMessage;
  settings: SessionSettings | null;
  pending?: boolean;
};

export function AIMessageCard({
  message,
  settings,
  pending = false
}: AIMessageCardProps) {
  const { settings: voiceSettings } = useVoiceSettings();
  const { speak, stop, isSpeaking } = useVoiceSynthesis(voiceSettings);

  const isUser = message.role === "user" || message.role === "practice_user";

  useEffect(() => {
    if (!isUser && !pending && voiceSettings.autoPlay && voiceSettings.enabled) {
      speak(message.content);
    }
  }, [pending, isUser, voiceSettings.autoPlay, voiceSettings.enabled, message.content, speak]);

  return (
    <article
      className={`relative mb-6 mr-auto max-w-4xl sm-glass-card overflow-hidden rounded-2xl p-6 transition-all duration-500 border border-indigo-500/20 shadow-[0_0_30px_rgba(99,102,241,0.1)] hover:border-indigo-400/40 hover:shadow-[0_0_40px_rgba(99,102,241,0.15)] ${
        pending ? "shadow-[0_0_40px_rgba(99,102,241,0.15)] ring-1 ring-indigo-500/30" : ""
      }`}
      style={{
        transform: pending ? 'translateY(-4px)' : 'translateY(0)',
      }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono text-[10px] font-bold shadow-lg bg-[linear-gradient(135deg,var(--sm-accent-indigo),var(--sm-accent-cyan))] text-white">
            SYS
            {pending && (
              <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-cyan-400 sm-animate-pulse-glow" />
            )}
          </div>
          <div>
            <h3 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-white flex items-center gap-2">
              {message.speaker}
              {pending && <span className="sm-typing-indicator ml-2"><span/><span/><span/></span>}
            </h3>
            {message.model && (
              <p className="font-mono text-[10px] tracking-[0.15em] mt-1 text-cyan-400">
                {message.model}
              </p>
            )}
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
          {voiceSettings.enabled && !pending && (
            <button
              onClick={() => isSpeaking ? stop() : speak(message.content)}
              className={`flex items-center gap-1.5 rounded-md border border-white/10 px-2 py-1 transition-all ${
                isSpeaking 
                  ? "bg-cyan-500/20 text-cyan-400 sm-animate-pulse-glow" 
                  : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white"
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
      
      {!pending && (
        <MessageCosts message={message} settings={settings} />
      )}
    </article>
  );
}
