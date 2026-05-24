import React from "react";

interface AlphaClusterPanelProps {
  data: {
    dominant_arguments?: string[];
    strongest_reasoning_chains?: number;
    aggressive_strategies?: number;
    logical_pressure_points?: string[];
  } | null;
}

export function AlphaClusterPanel({ data }: AlphaClusterPanelProps) {
  if (!data) {
    return (
      <div className="sm-glass-card p-6 flex flex-col items-center justify-center min-h-[250px] text-slate-400">
        <p className="text-sm font-mono tracking-widest uppercase">No Alpha Cluster Data</p>
      </div>
    );
  }

  return (
    <div className="sm-glass-card p-6 space-y-6 bg-gradient-to-br from-indigo-500/5 to-transparent border-indigo-500/10">
      <div className="flex items-center justify-between border-b border-indigo-500/20 pb-4">
        <div>
          <h3 className="text-sm font-mono font-bold tracking-widest text-indigo-400 uppercase">Alpha Cluster</h3>
          <p className="text-xs text-slate-400 mt-1">Dominance & Strategic Offensive</p>
        </div>
        <div className="flex gap-4">
          <div className="text-right">
            <p className="text-[10px] uppercase font-mono text-slate-500">Aggressive Moves</p>
            <p className="text-lg font-mono font-bold text-indigo-300">{data.aggressive_strategies || 0}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase font-mono text-slate-500">Support Chains</p>
            <p className="text-lg font-mono font-bold text-cyan-300">{data.strongest_reasoning_chains || 0}</p>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <h4 className="text-xs font-mono font-semibold text-slate-400 mb-2 uppercase tracking-wider">Dominant Arguments</h4>
          <div className="space-y-2">
            {(data.dominant_arguments || []).length > 0 ? (
              data.dominant_arguments!.map((arg, idx) => (
                <div key={idx} className="p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-sm text-indigo-100 shadow-[0_0_10px_rgba(99,102,241,0.1)]">
                  {arg}
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500 italic">No dominant arguments established yet.</p>
            )}
          </div>
        </div>

        <div>
          <h4 className="text-xs font-mono font-semibold text-slate-400 mb-2 uppercase tracking-wider">Logical Pressure Points</h4>
          <div className="flex flex-wrap gap-2">
            {(data.logical_pressure_points || []).length > 0 ? (
              data.logical_pressure_points!.map((term, idx) => (
                <span key={idx} className="px-2.5 py-1 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-xs font-mono font-medium">
                  {term}
                </span>
              ))
            ) : (
              <p className="text-xs text-slate-500 italic">No pressure points identified.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
