import { RefreshCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { EmptyState, AssetBadge } from "@/components/shared";
import { MarketsBentoGrid } from "@/components/markets/MarketsBentoGrid";
import { LogsView } from "@/components/LogsView";
import { formatSide, sideClass, formatMarketWindow } from "@/lib/utils2";
import type { Market, Trade, Position } from "@/types";

interface MarketsViewProps {
  markets: Market[];
  trades: Trade[];
  positions: Position[];
  logs: string[];
  loadingMarkets: boolean;
  onRefresh: () => void;
  onClearLogs: () => void;
  onClearPositions: () => void;
  onClearTradeHistory: () => void;
}

export function MarketsView({
  markets,
  trades,
  positions,
  logs,
  loadingMarkets,
  onRefresh,
  onClearLogs,
  onClearPositions,
  onClearTradeHistory,
}: MarketsViewProps) {
  const closedTrades = trades.filter((t) => t.status !== "OPEN");
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_460px] 2xl:grid-cols-[minmax(0,1fr)_560px]">
      <div className="min-w-0 space-y-4">
        {/* Live Markets */}
        <Section
          title="Live Markets"
          description="CLOB prices, edge and market status in real time"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              disabled={loadingMarkets}
              className="border-white/10 bg-white/[0.03] hover:bg-white/8"
            >
              <RefreshCcw className={cn("h-3.5 w-3.5", loadingMarkets && "animate-spin")} />
              Refresh
            </Button>
          }
        >
          <MarketsBentoGrid markets={markets} />
        </Section>

        {/* Positions */}
        <Section title="Open Positions" description={`${positions.length} position${positions.length !== 1 ? "s" : ""}`}>
          {positions.length ? (
            <div className="grid gap-2">
              {positions.map((position, index) => (
                <PositionRow key={`${position.market}-${index}`} position={position} markets={markets} />
              ))}
            </div>
          ) : (
            <EmptyState>No open positions</EmptyState>
          )}
        </Section>

        {/* Trade History (Closed) */}
        <Section
          title="Trade History"
          description={`${closedTrades.length} closed trade${closedTrades.length !== 1 ? "s" : ""}`}
          action={
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onClearPositions}
                className="border-white/10 bg-white/[0.03] text-xs hover:bg-white/8"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear Positions
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onClearTradeHistory}
                disabled={!closedTrades.length}
                className="border-red-500/30 bg-red-500/5 text-red-400 hover:bg-red-500/15 hover:text-red-300 text-xs"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear All
              </Button>
            </div>
          }
        >
          <TradesTable trades={closedTrades} markets={markets} />
        </Section>
      </div>

      <aside className="min-w-0 xl:sticky xl:top-[128px] xl:self-start">
        <LogsView logs={logs} onClear={onClearLogs} />
      </aside>
    </div>
  );
}

function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
      <div className="flex items-start justify-between gap-4 border-b border-white/5 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-muted-foreground/60">{description}</p>}
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function PositionRow({ position, markets }: { position: Position; markets: Market[] }) {
  const side = formatSide(position.side);
  const shares = Number(position.size || 0);
  const avg = Number(position.avg_price || position.price || 0);
  const cost = shares * avg;

  const market = markets.find((m) =>
    m.asset === position.asset &&
    (m.market_id === position.market || m.condition_id === position.market || m.slug === position.market)
  );
  const marketLabel = formatMarketWindow({
    timeframe: position.timeframe || market?.timeframe,
    window_start_timestamp: position.window_start_timestamp || market?.window_start_timestamp,
    end_date: position.end_date || market?.end_date || market?.end_date,
    market_slug: position.market_slug || market?.slug || market?.event_slug || market?.market_slug,
  });
  const timeframe = position.timeframe || market?.timeframe;
  const exitPrice =
    position.side?.toUpperCase() === "YES"
      ? market?.best_bid_up
      : position.side?.toUpperCase() === "NO"
        ? market?.best_bid_down
        : null;

  const recover = exitPrice != null ? shares * exitPrice : null;
  const pnl = recover != null ? recover - cost : null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/8 bg-white/[0.02] px-4 py-3">
      <div className="flex items-center gap-2">
        {marketLabel && (
          <span className="text-xs text-muted-foreground/60">{marketLabel}</span>
        )}
        {timeframe && (
          <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs font-mono font-medium text-muted-foreground">
            {timeframe}
          </span>
        )}
        <AssetBadge asset={position.asset} />
        <span className={cn("text-sm font-bold", sideClass(position.side))}>{side}</span>
      </div>
      <div className="flex gap-4 font-mono text-xs text-muted-foreground">
        <span>
          <span className="text-muted-foreground/50">shares </span>
          <span className="text-foreground">{shares.toFixed(2)}</span>
        </span>
        <span>
          <span className="text-muted-foreground/50">avg </span>
          <span className="text-foreground">{avg.toFixed(3)}</span>
        </span>
        <span>
          <span className="text-muted-foreground/50">cost </span>
          <span className="text-foreground">${cost.toFixed(2)}</span>
        </span>
        <span>
          <span className="text-muted-foreground/50">recover </span>
          <span className="text-foreground">
            {recover != null ? `$${recover.toFixed(2)}` : "—"}
          </span>
        </span>
        <span>
          <span className="text-muted-foreground/50">pnl </span>
          <span className={cn(pnl != null ? (pnl >= 0 ? "text-emerald-400" : "text-red-400") : "text-muted-foreground/50")}>
            {pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}` : "—"}
          </span>
        </span>
      </div>
      <span className="hidden">{position.market || ""}</span>
    </div>
  );
}

function TradesTable({ trades, markets }: { trades: Trade[]; markets: Market[] }) {
  if (!trades.length) return <EmptyState>No closed trades</EmptyState>;

  const formatDate = (ts?: number) => {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  };

  const getMarketLabel = (trade: Trade) => {
    const meta = trade.metadata;
    const market = markets.find((m) =>
      m.market_id === trade.market || m.condition_id === trade.market || m.slug === trade.market
    );
    return formatMarketWindow({
      timeframe: meta?.timeframe || market?.timeframe,
      window_start_timestamp: meta?.window_start_timestamp || market?.window_start_timestamp,
      end_date: meta?.end_date || market?.end_date,
      market_slug: meta?.market_slug || market?.slug || market?.event_slug || market?.market_slug,
    });
  };

  const getMarketSlug = (trade: Trade) => {
    const meta = trade.metadata;
    const market = markets.find((m) =>
      m.market_id === trade.market || m.condition_id === trade.market || m.slug === trade.market
    );
    return meta?.market_slug || market?.slug || market?.event_slug || market?.market_slug || trade.market || "";
  };

  const getTimeframe = (trade: Trade) => {
    const meta = trade.metadata;
    const market = markets.find((m) =>
      m.market_id === trade.market || m.condition_id === trade.market || m.slug === trade.market
    );
    return meta?.timeframe || market?.timeframe || "";
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-white/8">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/8 bg-white/[0.02]">
            {["Market", "TF", "Asset", "Side", "Entry", "Exit", "Size", "Status", "Opened", "Closed", "PnL"].map((h) => (
              <th key={h} className="px-2 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {trades.map((trade, index) => {
            const pnl = Number(trade.pnl || 0);
            const marketLabel = getMarketLabel(trade);
            const marketSlug = getMarketSlug(trade);
            const timeframe = getTimeframe(trade);
            return (
              <tr key={`${trade.trade_id}-${index}`} className="hover:bg-white/[0.02]">
                <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground/60 max-w-[120px] truncate">
                  {marketLabel ? (
                    <a
                      href={`https://polymarket.com/event/${marketSlug}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary/80 hover:text-primary hover:underline"
                    >
                      {marketLabel}
                    </a>
                  ) : (
                    trade.market || "—"
                  )}
                </td>
                <td className="px-2 py-2.5">
                  {timeframe ? (
                    <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs font-mono font-medium text-muted-foreground">
                      {timeframe}
                    </span>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </td>
                <td className="px-2 py-2.5"><AssetBadge asset={trade.asset || ""} /></td>
                <td className={cn("px-2 py-2.5 text-xs font-bold", sideClass(trade.side))}>{formatSide(trade.side)}</td>
                <td className="px-2 py-2.5 font-mono text-xs">{(trade.entry_price ?? 0).toFixed(3)}</td>
                <td className="px-2 py-2.5 font-mono text-xs">{(trade.exit_price ?? 0).toFixed(3)}</td>
                <td className="px-2 py-2.5 font-mono text-xs">{trade.size}</td>
                <td className="px-2 py-2.5">
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                    trade.status === "OPEN" ? "bg-sky-500/15 text-sky-400" : "bg-white/5 text-muted-foreground"
                  )}>
                    {trade.status}
                  </span>
                </td>
                <td className="px-2 py-2.5 text-xs text-muted-foreground/60">{formatDate(trade.opened_at)}</td>
                <td className="px-2 py-2.5 text-xs text-muted-foreground/60">{formatDate(trade.closed_at)}</td>
                <td className={cn("px-2 py-2.5 font-mono text-xs font-bold", pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
