"use client";

import { useEffect } from "react";
import type { DebateMessage, SessionSettings } from "@/types";
import { MarkdownText, estimateTokens, MessageCosts } from "@/components/DebateRoom";
import { useVoiceSettings, useVoiceSynthesis } from "@/hooks/useVoice";

type JudgeMessageCardProps = {
  message: DebateMessage;
  settings: SessionSettings | null;
  pending?: boolean;
};

export function JudgeMessageCard({
  message,
  settings,
  pending = false
}: JudgeMessageCardProps) {
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
      className={`relative mb-6 mx-auto max-w-4xl overflow-hidden rounded-2xl p-6 transition-all duration-500 border border-amber-500/30 bg-gradient-to-br from-amber-500/10 to-yellow-600/5 shadow-[0_0_35px_rgba(245,158,11,0.12)] hover:border-amber-400/50 hover:shadow-[0_0_45px_rgba(245,158,11,0.18)] ${
        pending ? "shadow-[0_0_40px_rgba(245,158,11,0.2)] ring-1 ring-amber-500/30 animate-pulse" : ""
      }`}
      style={{
        transform: pending ? 'translateY(-4px)' : 'translateY(0)',
      }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4 text-left">
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono text-[10px] font-bold shadow-lg bg-[linear-gradient(135deg,#f59e0b,#b45309)] text-white border border-amber-400/30">
            JDG
            {pending && (
              <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-amber-400 sm-animate-pulse-glow" />
            )}
          </div>
          <div>
            <h3 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-amber-400 flex items-center gap-2">
              {message.speaker}
              {pending && <span className="sm-typing-indicator ml-2"><span/><span/><span/></span>}
            </h3>
            <p className="font-mono text-[10px] tracking-[0.15em] mt-1 text-slate-400">
              SUPREME ADJUDICATOR
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[10px] font-medium">
          {settings?.show_timestamps && (
            <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 font-mono text-amber-300/80">
              {new Date(message.created_at || Date.now()).toLocaleTimeString()}
            </span>
          )}
          {settings?.show_token_count && (
            <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 font-mono text-amber-300/80">
              {estimateTokens(message.content)} tokens
            </span>
          )}
          {voiceSettings.enabled && !pending && (
            <button
              onClick={() => isSpeaking ? stop() : speak(message.content)}
              className={`flex items-center gap-1.5 rounded-md border border-amber-500/20 px-2 py-1 transition-all ${
                isSpeaking 
                  ? "bg-amber-500/20 text-amber-400 sm-animate-pulse-glow" 
                  : "bg-amber-500/10 text-amber-300 hover:bg-amber-500/25 hover:text-white"
              }`}
              title={isSpeaking ? "Stop Synthesis" : "Synthesize Response"}
            >
              {isSpeaking ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              )}
              {isSpeaking ? "Adjudicating" : "Listen Verdict"}
            </button>
          )}
          {pending && (
            <span className="sm-badge sm-badge-pro sm-animate-pulse-glow flex items-center gap-1.5 px-2.5 py-1 text-amber-300 border-amber-500/40">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              Verdict Synthesis Active
            </span>
          )}
        </div>
      </div>

      {pending && (
        <div className="absolute top-0 left-0 right-0 sm-streaming-bar bg-gradient-to-r from-amber-400 via-yellow-500 to-amber-600" />
      )}

      <div className={`text-[15px] leading-relaxed text-slate-200 text-left ${pending ? 'sm-streaming-cursor' : ''}`}>
        <MarkdownText text={message.content || "Evaluating debate arguments and constructing supreme logic verdict..."} />
      </div>
      
      {!pending && (
        <div className="text-left">
          <MessageCosts message={message} settings={settings} />
        </div>
      )}
    </article>
  );
}
