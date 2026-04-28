import { Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/shared";
import { getLogPresentation, tokenizeLogMessage, type LogTone, type LogTokenKind } from "@/lib/logPresentation";
import { cn } from "@/lib/utils";

interface LogsViewProps {
  logs: string[];
  onClear: () => void;
}

export function LogsView({ logs, onClear }: LogsViewProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/8 bg-white/[0.02] shadow-[0_20px_70px_rgba(0,0,0,0.22)] backdrop-blur">
      <div className="flex items-center justify-between border-b border-white/5 bg-gradient-to-r from-white/[0.045] to-transparent px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 p-2 text-emerald-300">
            <Terminal className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">Realtime Log</h2>
            <p className="mt-0.5 text-xs text-muted-foreground/60">Eventos WebSocket, trades y errores · últimas 80 entradas</p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onClear}
          className="border-white/10 bg-white/[0.03] text-xs hover:bg-white/8"
        >
          Clear
        </Button>
      </div>
      <div className="p-4">
        <ScrollArea className="h-[640px] rounded-xl border border-white/8 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.08),_transparent_34%),linear-gradient(180deg,_#080b11_0%,_#05070c_100%)] p-3">
          {logs.length ? (
            <ol className="space-y-2">
              {logs.map((entry, index) => {
                const [time, ...rest] = entry.split(" ");
                const message = rest.join(" ");
                const presentation = getLogPresentation(message);
                const tokens = tokenizeLogMessage(message);
                return (
                  <li
                    key={`${entry}-${index}`}
                    className={cn(
                      "group grid grid-cols-[64px_74px_minmax(0,1fr)] items-start gap-2 rounded-lg border px-2.5 py-2 font-mono text-[11px] leading-relaxed transition-colors",
                      toneRowClass[presentation.tone]
                    )}
                  >
                    <span className="mt-px shrink-0 text-muted-foreground/45">{time}</span>
                    <span className={cn("rounded-md border px-1.5 py-0.5 text-center text-[9px] font-bold tracking-[0.14em]", toneBadgeClass[presentation.tone])}>
                      {presentation.label}
                    </span>
                    <span className={cn("min-w-0 break-words", toneTextClass[presentation.tone])}>
                      {tokens.map((token, tokenIndex) => (
                        <span
                          key={`${token.text}-${tokenIndex}`}
                          className={cn(
                            "mr-1.5 inline-block align-baseline",
                            tokenClass[token.kind],
                            token.colorClass
                          )}
                        >
                          {token.text}
                        </span>
                      ))}
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : (
            <EmptyState>No logs yet</EmptyState>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}

const toneRowClass: Record<LogTone, string> = {
  info: "border-white/[0.06] bg-white/[0.025] hover:bg-white/[0.045]",
  connected: "border-emerald-400/15 bg-emerald-400/[0.055] hover:bg-emerald-400/[0.085]",
  error: "border-red-400/20 bg-red-500/[0.075] hover:bg-red-500/[0.11]",
  trade: "border-orange-300/20 bg-orange-400/[0.07] hover:bg-orange-400/[0.105]",
  decision: "border-sky-300/18 bg-sky-400/[0.065] hover:bg-sky-400/[0.095]",
  skip: "border-amber-300/16 bg-amber-300/[0.055] hover:bg-amber-300/[0.085]",
};

const toneBadgeClass: Record<LogTone, string> = {
  info: "border-white/10 bg-white/[0.04] text-slate-300",
  connected: "border-emerald-300/20 bg-emerald-300/10 text-emerald-300",
  error: "border-red-300/25 bg-red-400/10 text-red-300",
  trade: "border-orange-200/25 bg-orange-300/10 text-orange-200",
  decision: "border-sky-200/25 bg-sky-300/10 text-sky-200",
  skip: "border-amber-200/25 bg-amber-300/10 text-amber-200",
};

const toneTextClass: Record<LogTone, string> = {
  info: "text-slate-300/80",
  connected: "text-emerald-200/90",
  error: "text-red-200/95",
  trade: "text-orange-100/95",
  decision: "text-sky-100/95",
  skip: "text-amber-100/90",
};

const tokenClass: Record<LogTokenKind, string> = {
  text: "text-current",
  tag: "font-bold text-white/90",
  market: "rounded border border-cyan-300/25 bg-cyan-300/10 px-1.5 py-0.5 font-semibold text-cyan-200",
  strategy: "rounded border px-1.5 py-0.5 font-semibold",
  field: "text-white/68",
};
