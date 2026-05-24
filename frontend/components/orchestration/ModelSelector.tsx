import React from "react";
import type { ModelsResponse } from "@/types";

interface ModelSelectorProps {
  label: string;
  value: string;
  models: ModelsResponse | null;
  onChange: (value: string) => void;
  role: "pro" | "con" | "judge" | "opponent";
  disabled?: boolean;
}

export function ModelSelector({
  label,
  value,
  models,
  onChange,
  role,
  disabled = false
}: ModelSelectorProps) {
  const list = models?.models ?? [];

  // Accent colors based on model role
  const borderFocusColor = 
    role === "pro" || role === "opponent"
      ? "focus:border-indigo-500 focus:shadow-[0_0_15px_rgba(99,102,241,0.25)]"
      : role === "con"
      ? "focus:border-rose-500 focus:shadow-[0_0_15px_rgba(244,63,94,0.25)]"
      : "focus:border-amber-500 focus:shadow-[0_0_15px_rgba(245,158,11,0.25)]";

  const badgeBg = 
    role === "pro" || role === "opponent"
      ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/20"
      : role === "con"
      ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
      : "bg-amber-500/10 text-amber-400 border-amber-500/20";

  const providerGroups = list.reduce((acc, model) => {
    const provider = model.provider_label || "Other Providers";
    if (!acc[provider]) acc[provider] = [];
    acc[provider].push(model);
    return acc;
  }, {} as Record<string, typeof list>);

  return (
    <div className="flex flex-col gap-1.5 w-full">
      <div className="flex items-center justify-between">
        <label className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">
          {label}
        </label>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${badgeBg}`}>
          {role === "judge" ? "Adjudicator" : role === "pro" ? "Pro Team" : role === "con" ? "Con Team" : "AI Opponent"}
        </span>
      </div>
      <div className="relative">
        <select
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={`h-11 w-full rounded-xl bg-[#09090b] border border-white/10 px-4 text-sm text-white font-medium transition-all appearance-none cursor-pointer outline-none ${borderFocusColor} disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {list.length === 0 && <option value="">No verified models available</option>}
          {Object.entries(providerGroups).map(([provider, providerModels]) => (
            <optgroup key={provider} label={provider} className="bg-zinc-950 text-slate-300">
              {providerModels.map((model) => (
                <option key={model.name} value={model.name} className="bg-zinc-950 text-white">
                  {model.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-slate-400">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>
    </div>
  );
}
