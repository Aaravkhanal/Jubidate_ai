import React from "react";

interface BetaClusterPanelProps {
  data: {
    defensive_reasoning?: number;
    weak_arguments?: number;
    hesitation_patterns?: number;
    contradictions?: number;
    instability_markers?: number;
  } | null;
}

export function BetaClusterPanel({ data }: BetaClusterPanelProps) {
  if (!data) {
    return (
      <div className="sm-glass-card p-6 flex flex-col items-center justify-center min-h-[250px] text-slate-400">
        <p className="text-sm font-mono tracking-widest uppercase">No Beta Cluster Data</p>
      </div>
    );
  }

  const metrics = [
    { label: "Defensive Reasoning", value: data.defensive_reasoning || 0, threshold: 3 },
    { label: "Weak Arguments", value: data.weak_arguments || 0, threshold: 2 },
    { label: "Hesitation Patterns", value: data.hesitation_patterns || 0, threshold: 4 },
    { label: "Contradiction Edges", value: data.contradictions || 0, threshold: 2 },
  ];

  const instability = (data.instability_markers || 0) * 100;
  const isHighlyUnstable = instability > 50;

  return (
    <div className="sm-glass-card p-6 space-y-6 bg-gradient-to-br from-rose-500/5 to-transparent border-rose-500/10">
      <div className="flex items-center justify-between border-b border-rose-500/20 pb-4">
        <div>
          <h3 className="text-sm font-mono font-bold tracking-widest text-rose-400 uppercase">Beta Cluster</h3>
          <p className="text-xs text-slate-400 mt-1">Weaknesses & Systemic Instability</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase font-mono text-slate-500">Instability Score</span>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-lg font-mono font-bold ${isHighlyUnstable ? 'text-rose-400' : 'text-amber-400'}`}>
              {instability.toFixed(1)}%
            </span>
            {isHighlyUnstable && <span className="sm-orb bg-rose-500" />}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {metrics.map((metric) => {
          const isWarning = metric.value >= metric.threshold;
          return (
            <div key={metric.label} className={`p-4 rounded-xl border transition-all ${isWarning ? 'bg-rose-500/10 border-rose-500/30 shadow-[0_0_15px_rgba(244,63,94,0.15)]' : 'bg-white/[0.02] border-white/5'}`}>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">{metric.label}</span>
                <span className={`text-xl font-mono font-bold ${isWarning ? 'text-rose-400' : 'text-white'}`}>
                  {metric.value}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
