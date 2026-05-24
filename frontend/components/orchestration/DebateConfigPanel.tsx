import React, { useState } from "react";
import type { ModelsResponse } from "@/types";
import { ModelSelector } from "./ModelSelector";
import { JudgeSelector } from "./JudgeSelector";

interface DebateConfigPanelProps {
  mode: "ai_vs_ai" | "ai_vs_human";
  models: ModelsResponse | null;
  aiA: string;
  aiB: string;
  judge: string;
  rounds: number;
  topic: string;
  onAiAChange: (val: string) => void;
  onAiBChange: (val: string) => void;
  onJudgeChange: (val: string) => void;
  onRoundsChange: (val: number) => void;
  onTopicChange: (val: string) => void;
  onBack: () => void;
  onSubmit: () => void;
  isCreating: boolean;
}

export function DebateConfigPanel({
  mode,
  models,
  aiA,
  aiB,
  judge,
  rounds,
  topic,
  onAiAChange,
  onAiBChange,
  onJudgeChange,
  onRoundsChange,
  onTopicChange,
  onBack,
  onSubmit,
  isCreating
}: DebateConfigPanelProps) {
  const [step, setStep] = useState<1 | 2>(1);

  const sampleTopics = [
    "Python vs Java",
    "Remote work is better",
    "AI will replace programmers"
  ];

  // Conflict validation checks
  const isAiVsAi = mode === "ai_vs_ai";
  const hasConflict = Boolean(
    isAiVsAi
      ? (
          (aiA && judge && aiA.toLowerCase() === judge.toLowerCase()) ||
          (aiB && judge && aiB.toLowerCase() === judge.toLowerCase()) ||
          (aiA && aiB && aiA.toLowerCase() === aiB.toLowerCase())
        )
      : (aiA && judge && aiA.toLowerCase() === judge.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* ── Step Indicator ── */}
      <div className="flex items-center justify-between border-b border-white/5 pb-4">
        <div className="flex gap-2">
          <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${step === 1 ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30" : "bg-white/5 text-slate-500"}`}>
            STEP 1: TOPIC
          </span>
          <span className="text-slate-600">→</span>
          <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${step === 2 ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30" : "bg-white/5 text-slate-500"}`}>
            STEP 2: MODELS
          </span>
        </div>
        <p className="text-xs text-slate-500 font-mono">
          {mode === "ai_vs_ai" ? "Autonomous Orchestration" : "Human-AI Alignment"}
        </p>
      </div>

      {step === 1 ? (
        <div className="space-y-5 animate-fadeIn">
          <div>
            <label htmlFor="debate-topic-input" className="mb-2 block text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">
              Debate Topic / Strategic Question
            </label>
            <input
              id="debate-topic-input"
              type="text"
              value={topic}
              onChange={(e) => onTopicChange(e.target.value)}
              placeholder="Enter your debate topic or question..."
              className="h-12 w-full rounded-xl bg-white/[0.04] border border-white/10 px-4 text-sm text-white font-medium placeholder:text-slate-500 transition-all outline-none focus:border-indigo-500 focus:shadow-[0_0_15px_rgba(99,102,241,0.25)]"
            />
          </div>

          <div>
            <p className="mb-2 text-xs font-mono font-semibold uppercase tracking-wider text-slate-500">
              Recommended Hot Topics
            </p>
            <div className="flex flex-wrap gap-2.5">
              {sampleTopics.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => onTopicChange(item)}
                  className="rounded-full bg-white/5 border border-white/5 px-4 py-2 text-xs font-medium text-slate-300 transition-all hover:bg-white/10 hover:border-white/20 hover:text-white"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-white/5">
            <button
              type="button"
              onClick={onBack}
              className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-slate-300 transition-all hover:bg-white/5"
            >
              Back
            </button>
            <button
              type="button"
              disabled={!topic.trim()}
              onClick={() => setStep(2)}
              className="rounded-xl bg-indigo-500 px-5 py-2.5 text-xs font-semibold text-white shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next: Select Models
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-5 animate-fadeIn">
          {/* Models Grid */}
          <div className="grid gap-4 md:grid-cols-2">
            <ModelSelector
              label={isAiVsAi ? "PRO Side (AI A)" : "AI Opponent (AI A)"}
              value={aiA}
              models={models}
              onChange={onAiAChange}
              role={isAiVsAi ? "pro" : "opponent"}
            />

            {isAiVsAi && (
              <ModelSelector
                label="CON Side (AI B)"
                value={aiB}
                models={models}
                onChange={onAiBChange}
                role="con"
              />
            )}

            <div className="md:col-span-2">
              <JudgeSelector
                value={judge}
                models={models}
                onChange={onJudgeChange}
              />
            </div>

            <div className="md:col-span-2">
              <label htmlFor="rounds-select" className="mb-2 block text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">
                Strategic Rounds
              </label>
              <div className="relative">
                <select
                  id="rounds-select"
                  value={rounds}
                  onChange={(e) => onRoundsChange(Number(e.target.value))}
                  className="h-11 w-full rounded-xl bg-white/[0.03] border border-white/10 px-4 text-sm text-white outline-none focus:border-indigo-500 appearance-none cursor-pointer"
                >
                  {[1, 2, 3, 4, 5, 6].map((num) => (
                    <option key={num} value={num} className="bg-zinc-950 text-white">
                      {num} {num === 1 ? "Round" : "Rounds"}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-slate-400">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </div>
            </div>
          </div>

          {/* Conflict Warnings */}
          {hasConflict && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4.5 transition-all">
              <p className="text-xs font-bold uppercase tracking-wider text-amber-400">⚠️ Logical Isolation Error</p>
              <p className="text-[11px] mt-1 leading-relaxed text-slate-400">
                {isAiVsAi
                  ? "Conflict detected. The Judge model must be logically isolated from both AI A and AI B, and AI A must be different from AI B."
                  : "Conflict detected. The Opponent model and the Judge model must be different models to maintain judicial isolation."
                }
              </p>
            </div>
          )}

          <div className="flex justify-between items-center pt-4 border-t border-white/5">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-slate-300 transition-all hover:bg-white/5"
            >
              Back to Topic
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onBack}
                className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-slate-300 transition-all hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isCreating || hasConflict}
                onClick={onSubmit}
                className="rounded-xl bg-gradient-to-r from-indigo-500 to-cyan-500 px-6 py-2.5 text-xs font-bold text-white shadow-[0_0_20px_rgba(99,102,241,0.3)] hover:shadow-[0_0_25px_rgba(6,182,212,0.5)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCreating ? "Initializing..." : "Launch Simulation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
