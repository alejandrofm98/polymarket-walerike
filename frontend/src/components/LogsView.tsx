import { Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/shared";

interface LogsViewProps {
  logs: string[];
  onClear: () => void;
}

export function LogsView({ logs, onClear }: LogsViewProps) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
      <div className="flex items-center justify-between border-b border-white/5 px-5 py-4">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-muted-foreground/60" />
          <div>
            <h2 className="text-sm font-semibold text-foreground">Realtime Log</h2>
            <p className="mt-0.5 text-xs text-muted-foreground/60">WebSocket events and UI errors · last 80 entries</p>
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
        <ScrollArea className="h-[520px] rounded-xl border border-white/8 bg-[#080b11] p-4">
          {logs.length ? (
            <ol className="space-y-1.5">
              {logs.map((entry, index) => {
                const [time, ...rest] = entry.split(" ");
                const message = rest.join(" ");
                const isError = message.toLowerCase().includes("error") || message.toLowerCase().includes("failed");
                const isConnected = message.toLowerCase().includes("connected");
                return (
                  <li key={`${entry}-${index}`} className="flex items-start gap-2.5 font-mono text-xs">
                    <span className="mt-px shrink-0 text-muted-foreground/40">{time}</span>
                    <span className={
                      isError ? "text-red-400" :
                      isConnected ? "text-emerald-400" :
                      "text-muted-foreground/80"
                    }>
                      {message}
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
