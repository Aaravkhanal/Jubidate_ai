import React from "react";

interface ModeSelectionCardProps {
  title: string;
  description: string;
  active: boolean;
  icon: React.ReactNode;
  onClick: () => void;
}

export function ModeSelectionCard({
  title,
  description,
  active,
  icon,
  onClick
}: ModeSelectionCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex flex-col justify-between rounded-xl border p-6 text-left transition-all duration-300 cursor-pointer pointer-events-auto focus:outline-none focus:ring-2 focus:ring-indigo-500/50 w-full ${
        active
          ? "border-indigo-500 bg-indigo-500/10 shadow-[0_0_25px_rgba(99,102,241,0.2)]"
          : "border-white/5 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04] hover:shadow-[0_0_15px_rgba(255,255,255,0.05)]"
      }`}
    >
      <div className="absolute top-5 right-5 flex h-6 w-6 items-center justify-center rounded-full border border-white/20 transition-all group-hover:border-white/40">
        {active && <span className="h-3 w-3 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]" />}
      </div>
      <div>
        <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl transition-all duration-300 ${
          active ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30" : "bg-white/5 text-slate-400 group-hover:text-white border border-white/5 group-hover:border-white/10"
        }`}>
          {icon}
        </div>
        <h3 className="font-display text-lg font-bold text-white transition-colors group-hover:text-indigo-300">
          {title}
        </h3>
        <p className="mt-2 text-xs leading-relaxed text-slate-400">
          {description}
        </p>
      </div>
    </button>
  );
}
