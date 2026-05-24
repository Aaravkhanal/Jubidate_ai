import React from "react";
import type { ModelsResponse } from "@/types";
import { ModelSelector } from "./ModelSelector";

interface JudgeSelectorProps {
  value: string;
  models: ModelsResponse | null;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function JudgeSelector({
  value,
  models,
  onChange,
  disabled = false
}: JudgeSelectorProps) {
  return (
    <div
      className="rounded-xl border p-4.5 transition-all duration-300 bg-gradient-to-br from-amber-500/5 via-white/[0.01] to-transparent w-full"
      style={{
        borderColor: "rgba(245, 158, 11, 0.15)",
        boxShadow: "0 0 15px rgba(245, 158, 11, 0.03)"
      }}
    >
      <ModelSelector
        label="Isolated Judge AI"
        value={value}
        models={models}
        onChange={onChange}
        role="judge"
        disabled={disabled}
      />
      <div className="mt-3 flex items-start gap-2">
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-amber-500/10 text-amber-400 text-xs font-bold border border-amber-500/20">
          ⚖️
        </div>
        <p className="text-[11px] leading-relaxed text-slate-400">
          The Judge AI independently evaluates reasoning structures, scores debate performance, analyzes cognitive clusters, and declares a winner. It runs in a strict logical sandbox.
        </p>
      </div>
    </div>
  );
}
