import React from "react";

interface CognitiveMatrixPanelProps {
  data: {
    reasoning_strength?: number;
    persuasion_score?: number;
    contradiction_density?: number;
    factual_confidence?: number;
    strategic_pressure?: number;
    adaptation_score?: number;
  } | null;
}

export function CognitiveMatrixPanel({ data }: CognitiveMatrixPanelProps) {
  if (!data) {
    return (
      <div className="sm-glass-card p-6 flex flex-col items-center justify-center min-h-[300px] text-slate-400">
        <div className="sm-typing-indicator mb-3">
          <span />
          <span />
          <span />
        </div>
        <p className="text-sm font-mono tracking-widest uppercase">Initializing Cognitive Matrix</p>
      </div>
    );
  }

  const metrics = [
    { label: "Reasoning Strength", value: data.reasoning_strength || 0, color: "bg-indigo-500", shadow: "shadow-[0_0_15px_rgba(99,102,241,0.5)]" },
    { label: "Persuasion Score", value: data.persuasion_score || 0, color: "bg-cyan-500", shadow: "shadow-[0_0_15px_rgba(6,182,212,0.5)]" },
    { label: "Factual Confidence", value: data.factual_confidence || 0, color: "bg-emerald-500", shadow: "shadow-[0_0_15px_rgba(16,185,129,0.5)]" },
    { label: "Strategic Pressure", value: data.strategic_pressure || 0, color: "bg-amber-500", shadow: "shadow-[0_0_15px_rgba(245,158,11,0.5)]" },
    { label: "Adaptation Score", value: data.adaptation_score || 0, color: "bg-violet-500", shadow: "shadow-[0_0_15px_rgba(139,92,246,0.5)]" },
    { label: "Contradiction Density", value: data.contradiction_density || 0, color: "bg-rose-500", shadow: "shadow-[0_0_15px_rgba(244,63,94,0.5)]", inverse: true },
  ];

  return (
    <div className="sm-glass-card p-6 space-y-6">
      <div className="flex items-center justify-between border-b border-white/5 pb-4">
        <div>
          <h3 className="text-sm font-mono font-bold tracking-widest text-indigo-300 uppercase">Cognitive Matrix</h3>
          <p className="text-xs text-slate-400 mt-1">Real-time analytical telemetry</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-indigo-500/10 rounded-full border border-indigo-500/20">
          <span className="sm-orb" />
          <span className="text-[10px] font-mono text-indigo-300 uppercase tracking-wider font-bold">Live</span>
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6">
        {metrics.map((metric) => {
          // Normalize percentage (assume values generally range 0 to 1, or multiply by 100)
          const percentage = Math.min(100, Math.max(0, metric.value * 100));
          const isCritical = metric.inverse ? percentage > 70 : percentage < 30;

          return (
            <div key={metric.label} className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-medium text-slate-300">{metric.label}</span>
                <span className={`text-xs font-mono font-bold ${isCritical ? (metric.inverse ? "text-rose-400" : "text-amber-400") : "text-white"}`}>
                  {percentage.toFixed(1)}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full transition-all duration-1000 ease-out ${metric.color} ${metric.shadow}`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
