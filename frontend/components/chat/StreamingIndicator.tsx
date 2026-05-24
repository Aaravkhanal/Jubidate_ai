"use client";

type StreamingIndicatorProps = {
  speaker?: string;
  statusText?: string;
};

export function StreamingIndicator({
  speaker = "Council Assistant",
  statusText = "Synthesizing synaptic response..."
}: StreamingIndicatorProps) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-xl border border-cyan-500/10 bg-cyan-950/10 max-w-sm mr-auto animate-pulse">
      <div className="flex space-x-1.5 items-center">
        <span className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
      <div className="flex flex-col">
        <span className="text-[11px] font-bold text-white uppercase tracking-wider">{speaker}</span>
        <span className="text-[10px] text-slate-400 font-mono italic mt-0.5">{statusText}</span>
      </div>
    </div>
  );
}
