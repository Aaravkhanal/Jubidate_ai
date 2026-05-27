import React from "react";

interface PracticeStartDialogProps {
  side: "Auto" | "Pro" | "Con";
  onSideChange: (side: "Auto" | "Pro" | "Con") => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function PracticeStartDialog({
  side,
  onSideChange,
  onCancel,
  onConfirm,
}: PracticeStartDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onCancel} />
      <div className="relative w-full max-w-md bg-zinc-950 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-hidden">
        <h2 className="text-xl font-bold text-white mb-2">Start Practice Debate</h2>
        <p className="text-sm text-slate-400 mb-6">Choose your side for this practice session.</p>

        <div className="flex gap-3 mb-8">
          {(["Auto", "Pro", "Con"] as const).map((opt) => (
            <button
              key={opt}
              onClick={() => onSideChange(opt)}
              className={`flex-1 py-2 px-4 rounded-xl border text-sm font-semibold transition-all ${
                side === opt
                  ? "bg-blue-500/20 border-blue-500/50 text-blue-400"
                  : "bg-white/5 border-white/10 text-slate-400 hover:bg-white/10"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-slate-300 transition-all hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-xl bg-white text-black px-4 py-2 text-sm font-bold hover:bg-slate-200 transition-all"
          >
            Start
          </button>
        </div>
      </div>
    </div>
  );
}
