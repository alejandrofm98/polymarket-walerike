import { ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/shared";
import { getLogPresentation, tokenizeLogMessage, type LogTone, type LogTokenKind } from "@/lib/logPresentation";
import { parseLogEntry } from "@/lib/logEntry";
import { cn } from "@/lib/utils";

interface LogsViewProps {
  logs: string[];
  onClear: () => void;
  compact?: boolean;
}

export function LogsView({ logs, onClear, compact = false }: LogsViewProps) {
  return (
    <div className={cn("editorial-panel", compact && "opacity-90")}>
      <div className="relative flex items-center justify-between border-b editorial-divider bg-gradient-to-r from-white/[0.04] to-transparent px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2 text-muted-foreground/80">
            <ScrollText className="h-4 w-4" />
          </div>
          <div>
            <div className="editorial-kicker">Support Feed</div>
            <h2 className="editorial-title mt-1 text-xl text-foreground">Operational notes</h2>
            <p className="mt-0.5 text-xs text-muted-foreground/60">
              WebSocket events, copied trades, and runtime errors. Latest {compact ? "40" : "80"} entries.
            </p>
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
      <div className="relative p-4">
        <ScrollArea className={cn(
          "rounded-2xl border border-white/10 bg-[linear-gradient(180deg,_rgba(7,10,14,0.96)_0%,_rgba(6,8,12,0.98)_100%)] p-3",
          compact ? "h-[320px]" : "h-[640px]"
        )}>
          {logs.length ? (
            <ol className="space-y-2">
              {(compact ? logs.slice(0, 40) : logs).map((entry, index) => {
                const { time, message } = parseLogEntry(entry);
                const presentation = getLogPresentation(message);
                const tokens = tokenizeLogMessage(message);
                return (
                  <li
                    key={`${entry}-${index}`}
                    className={cn(
                      "group grid items-start gap-2 rounded-2xl border px-3 py-2.5 font-mono text-[11px] leading-relaxed transition-colors",
                      compact ? "grid-cols-[58px_64px_minmax(0,1fr)]" : "grid-cols-[64px_74px_minmax(0,1fr)]",
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
  info: "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]",
  connected: "border-emerald-400/12 bg-emerald-400/[0.04] hover:bg-emerald-400/[0.06]",
  error: "border-red-400/16 bg-red-500/[0.05] hover:bg-red-500/[0.08]",
  trade: "border-orange-300/16 bg-orange-400/[0.045] hover:bg-orange-400/[0.07]",
  decision: "border-sky-300/15 bg-sky-400/[0.04] hover:bg-sky-400/[0.065]",
  skip: "border-amber-300/14 bg-amber-300/[0.04] hover:bg-amber-300/[0.06]",
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
  field: "text-white/70",
};
