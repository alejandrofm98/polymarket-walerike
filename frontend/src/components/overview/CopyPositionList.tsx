import { Activity } from "lucide-react";
import { AssetBadge, EmptyState } from "@/components/shared";
import { formatMarketWindow, formatNumber, formatSide, sideClass } from "@/lib/utils2";
import { cn } from "@/lib/utils";
import type { CopyTradeItem } from "@/types";

interface CopyPositionListProps {
  positions: CopyTradeItem[];
}

export function CopyPositionList({ positions }: CopyPositionListProps) {
  if (!positions.length) {
    return <EmptyState icon={<Activity className="h-4 w-4" />}>No copied positions open</EmptyState>;
  }

  return (
    <div className="space-y-2">
      {positions.map((position) => {
        const key = position.trade_id || `${position.market}-${position.asset}-${position.opened_at}`;
        const metadata = position.metadata || {};
        return (
          <div key={key} className="rounded-xl border border-white/8 bg-white/[0.03] p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <AssetBadge asset={position.asset || position.market} />
                  <span className={cn("text-sm font-semibold", sideClass(position.side))}>{formatSide(position.side) || "-"}</span>
                  <span className="text-xs text-muted-foreground">{metadata.timeframe || "-"}</span>
                </div>
                <div className="text-xs text-muted-foreground">{formatMarketWindow(metadata)}</div>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-right text-xs sm:grid-cols-3">
                <Stat label="Size" value={formatNumber(position.size, 2) || "-"} />
                <Stat label="Entry" value={formatNumber(position.entry_price, 3) || "-"} />
                <Stat label="Leader" value={shortWallet(metadata.leader_wallet)} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground/55">{label}</div>
      <div className="font-mono text-sm text-foreground">{value}</div>
    </div>
  );
}

function shortWallet(value?: string) {
  if (!value) return "-";
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}
