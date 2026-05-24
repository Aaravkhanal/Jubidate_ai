"use client";

type DebateRoundHeaderProps = {
  title: string;
  subtitle?: string;
};

export function DebateRoundHeader({
  title,
  subtitle
}: DebateRoundHeaderProps) {
  return (
    <div className="flex flex-col items-center justify-center my-8 relative py-4 w-full">
      <div className="absolute inset-0 flex items-center" aria-hidden="true">
        <div className="w-full border-t border-indigo-500/10"></div>
      </div>
      <div className="relative flex flex-col items-center bg-[var(--sm-bg-primary)] px-6 text-center z-10">
        <span className="text-xs font-mono font-bold tracking-[0.25em] uppercase text-cyan-400 sm-badge sm-badge-cyan bg-cyan-950/40 border border-cyan-500/20 px-4 py-1.5 rounded-full shadow-[0_0_15px_rgba(6,182,212,0.15)]">
          {title}
        </span>
        {subtitle && (
          <span className="mt-2 text-[10px] font-mono tracking-widest text-slate-400 uppercase">
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
}
