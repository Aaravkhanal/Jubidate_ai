import React from "react";

interface ConfirmDialogProps {
  title: string;
  body: string;
  confirmLabel: string;
  suppressLabel?: string;
  isWorking?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (suppress?: boolean) => void;
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  suppressLabel,
  isWorking,
  error,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const [suppress, setSuppress] = React.useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onCancel} />
      <div className="relative w-full max-w-md bg-zinc-950 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-hidden">
        <h2 className="text-xl font-bold text-white mb-2">{title}</h2>
        <p className="text-sm text-slate-400 mb-6">{body}</p>
        
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
            {error}
          </div>
        )}

        {suppressLabel && (
          <label className="flex items-center gap-2 mb-6 cursor-pointer group">
            <input
              type="checkbox"
              className="w-4 h-4 rounded border-white/20 bg-white/5 text-blue-500 focus:ring-0 focus:ring-offset-0"
              checked={suppress}
              onChange={(e) => setSuppress(e.target.checked)}
            />
            <span className="text-sm text-slate-400 group-hover:text-slate-300 transition-colors">
              {suppressLabel}
            </span>
          </label>
        )}

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isWorking}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-slate-300 transition-all hover:bg-white/5 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(suppress)}
            disabled={isWorking}
            className="rounded-xl bg-red-500/10 text-red-500 border border-red-500/20 px-4 py-2 text-sm font-semibold hover:bg-red-500/20 transition-all disabled:opacity-50 flex items-center gap-2"
          >
            {isWorking ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Working...
              </>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
