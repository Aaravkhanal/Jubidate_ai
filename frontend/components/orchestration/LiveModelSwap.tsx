import React, { useState } from "react";
import type { ModelsResponse } from "@/types";

interface LiveModelSwapProps {
  mode: "ai_vs_ai" | "ai_vs_human";
  aiA: string;
  aiB: string;
  judge: string;
  models: ModelsResponse | null;
  onSwap: (role: "ai_a" | "ai_b" | "judge", model: string) => Promise<boolean>;
}

export function LiveModelSwap({
  mode,
  aiA,
  aiB,
  judge,
  models,
  onSwap
}: LiveModelSwapProps) {
  const [activeTab, setActiveTab] = useState<"ai_a" | "ai_b" | "judge" | null>(null);
  const [isSwapping, setIsSwapping] = useState(false);
  const list = models?.models ?? [];
  const isAiVsAi = mode === "ai_vs_ai";

  // Check conflicts in real-time
  function checkConflict(selectedRole: "ai_a" | "ai_b" | "judge", selectedVal: string) {
    const nextAiA = selectedRole === "ai_a" ? selectedVal : aiA;
    const nextAiB = selectedRole === "ai_b" ? selectedVal : aiB;
    const nextJudge = selectedRole === "judge" ? selectedVal : judge;

    if (isAiVsAi) {
      return Boolean(
        (nextAiA && nextJudge && nextAiA.toLowerCase() === nextJudge.toLowerCase()) ||
        (nextAiB && nextJudge && nextAiB.toLowerCase() === nextJudge.toLowerCase()) ||
        (nextAiA && nextAiB && nextAiA.toLowerCase() === nextAiB.toLowerCase())
      );
    } else {
      return Boolean(nextAiA && nextJudge && nextAiA.toLowerCase() === nextJudge.toLowerCase());
    }
  }

  async function handleSelect(role: "ai_a" | "ai_b" | "judge", value: string) {
    if (checkConflict(role, value)) return;
    setIsSwapping(true);
    try {
      const ok = await onSwap(role, value);
      if (ok) {
        setActiveTab(null);
      }
    } catch (err) {
      console.error("Live model swap failed:", err);
    } finally {
      setIsSwapping(false);
    }
  }

  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.01] p-3 shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5 mb-2.5">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-slate-400">
            Live Strategy Node Switcher
          </span>
        </div>
        <p className="text-[10px] text-slate-500 font-mono">Real-time state safe</p>
      </div>

      <div className="grid gap-2.5 md:grid-cols-3">
        {/* Node 1: AI A */}
        <div className="relative">
          <button
            type="button"
            disabled={isSwapping}
            onClick={() => setActiveTab(activeTab === "ai_a" ? null : "ai_a")}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-all ${
              activeTab === "ai_a"
                ? "border-indigo-500/50 bg-indigo-500/10"
                : "border-white/5 bg-white/[0.02] hover:border-white/10"
            }`}
          >
            <div>
              <p className="text-[9px] font-mono text-indigo-400 uppercase tracking-wide">
                {isAiVsAi ? "Pro Node" : "Opponent Node"}
              </p>
              <p className="text-xs font-bold text-white truncate max-w-[120px]">
                {aiA || "Not selected"}
              </p>
            </div>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {activeTab === "ai_a" && (
            <div className="absolute top-full left-0 z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-white/10 bg-zinc-950 p-1 shadow-2xl">
              {list.map((m) => {
                const conflict = checkConflict("ai_a", m.name);
                return (
                  <button
                    key={m.name}
                    type="button"
                    disabled={conflict}
                    onClick={() => handleSelect("ai_a", m.name)}
                    className={`w-full rounded px-2.5 py-1.5 text-left text-xs transition-all ${
                      conflict 
                        ? "text-slate-600 cursor-not-allowed bg-transparent" 
                        : m.name === aiA
                        ? "bg-indigo-500/20 text-indigo-300 font-bold"
                        : "text-slate-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {m.name} {conflict && "⚠️"}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Node 2: AI B (conditionally visible) */}
        {isAiVsAi ? (
          <div className="relative">
            <button
              type="button"
              disabled={isSwapping}
              onClick={() => setActiveTab(activeTab === "ai_b" ? null : "ai_b")}
              className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-all ${
                activeTab === "ai_b"
                  ? "border-rose-500/50 bg-rose-500/10"
                  : "border-white/5 bg-white/[0.02] hover:border-white/10"
              }`}
            >
              <div>
                <p className="text-[9px] font-mono text-rose-400 uppercase tracking-wide">Con Node</p>
                <p className="text-xs font-bold text-white truncate max-w-[120px]">{aiB || "Not selected"}</p>
              </div>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {activeTab === "ai_b" && (
              <div className="absolute top-full left-0 z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-white/10 bg-zinc-950 p-1 shadow-2xl">
                {list.map((m) => {
                  const conflict = checkConflict("ai_b", m.name);
                  return (
                    <button
                      key={m.name}
                      type="button"
                      disabled={conflict}
                      onClick={() => handleSelect("ai_b", m.name)}
                      className={`w-full rounded px-2.5 py-1.5 text-left text-xs transition-all ${
                        conflict 
                          ? "text-slate-600 cursor-not-allowed bg-transparent" 
                          : m.name === aiB
                          ? "bg-rose-500/20 text-rose-300 font-bold"
                          : "text-slate-300 hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      {m.name} {conflict && "⚠️"}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center rounded-lg border border-white/5 bg-white/[0.01] px-3 py-2">
            <span className="text-[10px] font-mono text-slate-500">Operator is Active</span>
          </div>
        )}

        {/* Node 3: Judge */}
        <div className="relative">
          <button
            type="button"
            disabled={isSwapping}
            onClick={() => setActiveTab(activeTab === "judge" ? null : "judge")}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-all ${
              activeTab === "judge"
                ? "border-amber-500/50 bg-amber-500/10"
                : "border-white/5 bg-white/[0.02] hover:border-white/10"
            }`}
          >
            <div>
              <p className="text-[9px] font-mono text-amber-400 uppercase tracking-wide">Judge Node</p>
              <p className="text-xs font-bold text-white truncate max-w-[120px]">{judge || "Not selected"}</p>
            </div>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {activeTab === "judge" && (
            <div className="absolute top-full left-0 z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-white/10 bg-zinc-950 p-1 shadow-2xl">
              {list.map((m) => {
                const conflict = checkConflict("judge", m.name);
                return (
                  <button
                    key={m.name}
                    type="button"
                    disabled={conflict}
                    onClick={() => handleSelect("judge", m.name)}
                    className={`w-full rounded px-2.5 py-1.5 text-left text-xs transition-all ${
                      conflict 
                        ? "text-slate-600 cursor-not-allowed bg-transparent" 
                        : m.name === judge
                        ? "bg-amber-500/20 text-amber-300 font-bold"
                        : "text-slate-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {m.name} {conflict && "⚠️"}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
