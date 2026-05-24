import React, { useState } from "react";
import type { ModelsResponse } from "@/types";
import { ModeSelectionCard } from "./ModeSelectionCard";
import { DebateConfigPanel } from "./DebateConfigPanel";

interface NewChatDraft {
  mode: "ai_vs_ai" | "ai_vs_human";
  overall_model: string;
  debaters_per_team: number;
  practice_settings: any;
  ai_a_model: string;
  ai_b_model: string;
  judge_model: string;
  rounds: number;
}

interface SessionSpawnerProps {
  models: ModelsResponse | null;
  onSpawn: (draft: NewChatDraft, topic: string) => void;
  onCancel: () => void;
  isCreating: boolean;
  initialDraft: NewChatDraft;
}

export function SessionSpawner({
  models,
  onSpawn,
  onCancel,
  isCreating,
  initialDraft
}: SessionSpawnerProps) {
  const [draft, setDraft] = useState<NewChatDraft>(initialDraft);
  const [topic, setTopic] = useState("");
  const [screen, setScreen] = useState<"mode" | "config">("mode");

  const list = models?.models ?? [];
  const first = list[0]?.name ?? "";
  const second = list[1]?.name ?? list[0]?.name ?? "";
  const third = list[2]?.name ?? list[0]?.name ?? "";

  function handleSelectMode(mode: "ai_vs_ai" | "ai_vs_human") {
    setDraft((prev) => ({
      ...prev,
      mode,
      ai_a_model: prev.ai_a_model || first,
      ai_b_model: mode === "ai_vs_ai" ? (prev.ai_b_model || second) : "",
      judge_model: prev.judge_model || third
    }));
    setScreen("config");
  }

  return (
    <div className="w-full">
      {screen === "mode" ? (
        <div className="space-y-6 animate-fadeIn">
          <div>
            <h2 className="text-xl font-black text-white tracking-wide">
              CREATE A SESSION
            </h2>
            <p className="mt-1 text-xs text-slate-400 leading-relaxed">
              Initialize a turn-based state machine session. Strict model isolation and logical sandbox guarantees will be validated in real-time.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <ModeSelectionCard
              title="Autonomous Alignment Simulation"
              description="Two isolated AI nodes execute objective-oriented arguments turn-by-turn. A specialized third Adjudicator AI generates structured matrix scorecards."
              active={draft.mode === "ai_vs_ai"}
              icon={
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                </svg>
              }
              onClick={() => handleSelectMode("ai_vs_ai")}
            />

            <ModeSelectionCard
              title="Human-AI Alignment Simulation"
              description="Engage in a live strategic debate with an AI opponent. The adjudicator scores reasoning patterns and logical soundness dynamically."
              active={draft.mode === "ai_vs_human"}
              icon={
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              }
              onClick={() => handleSelectMode("ai_vs_human")}
            />
          </div>

          <div className="flex justify-end pt-4 border-t border-white/5">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-slate-300 transition-all hover:bg-white/5"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <DebateConfigPanel
          mode={draft.mode}
          models={models}
          aiA={draft.ai_a_model}
          aiB={draft.ai_b_model}
          judge={draft.judge_model}
          rounds={draft.rounds}
          topic={topic}
          onAiAChange={(val) => setDraft((prev) => ({ ...prev, ai_a_model: val }))}
          onAiBChange={(val) => setDraft((prev) => ({ ...prev, ai_b_model: val }))}
          onJudgeChange={(val) => setDraft((prev) => ({ ...prev, judge_model: val }))}
          onRoundsChange={(val) => setDraft((prev) => ({ ...prev, rounds: val }))}
          onTopicChange={setTopic}
          onBack={() => setScreen("mode")}
          onSubmit={() => onSpawn(draft, topic)}
          isCreating={isCreating}
        />
      )}
    </div>
  );
}
