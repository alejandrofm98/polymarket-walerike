import { History } from "lucide-react";
import { AssetBadge, EmptyState } from "@/components/shared";
import { formatMarketWindow, formatNumber, formatSide, sideClass } from "@/lib/utils2";
import { cn } from "@/lib/utils";
import type { CopyTradeItem } from "@/types";

interface CopyTradeHistoryProps {
  trades: CopyTradeItem[];
}

export function CopyTradeHistory({ trades }: CopyTradeHistoryProps) {
  if (!trades.length) {
    return <EmptyState icon={<History className="h-4 w-4" />}>No copied trades closed</EmptyState>;
  }

  return (
    <div className="space-y-2">
      {trades.map((trade) => {
        const key = trade.trade_id || `${trade.market}-${trade.asset}-${trade.closed_at}`;
        const pnl = Number(trade.pnl || 0);
        const metadata = trade.metadata || {};
        return (
          <div key={key} className="rounded-xl border border-white/8 bg-white/[0.03] p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <AssetBadge asset={trade.asset || trade.market} />
                  <span className={cn("text-sm font-semibold", sideClass(trade.side))}>{formatSide(trade.side) || "-"}</span>
                  <span className="text-xs text-muted-foreground">{metadata.timeframe || "-"}</span>
                </div>
                <div className="text-xs text-muted-foreground">{formatMarketWindow(metadata)}</div>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-right text-xs sm:grid-cols-4">
                <Stat label="Size" value={formatNumber(trade.size, 2) || "-"} />
                <Stat label="Entry" value={formatNumber(trade.entry_price, 3) || "-"} />
                <Stat label="Exit" value={formatNumber(trade.exit_price, 3) || "-"} />
                <Stat label="PnL" value={`${pnl >= 0 ? "+" : ""}${formatNumber(pnl, 2) || "0.00"}`} valueClass={pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground/55">{label}</div>
      <div className={cn("font-mono text-sm text-foreground", valueClass)}>{value}</div>
    </div>
  );
}
