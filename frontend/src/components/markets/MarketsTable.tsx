import React, { memo } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { AssetBadge, EmptyState } from "@/components/shared";
import { formatNumber, formatBidAsk, getMarketKey, formatMarketWindow } from "@/lib/utils2";
import type { Market } from "@/types";

interface MarketsTableProps {
  markets: Market[];
}

export const MarketsTable = memo(function MarketsTable({ markets }: MarketsTableProps) {
  if (!markets.length) {
    return <EmptyState>No markets loaded</EmptyState>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/8">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/8 bg-white/[0.02]">
            <Th>Asset</Th>
            <Th>TF</Th>
            <Th>Market</Th>
            <Th>Target</Th>
            <Th>Current</Th>
            <Th>Diff</Th>
            <Th>
              <span className="text-emerald-400">YES</span>
              {" / "}
              <span className="text-red-400">NO</span>
            </Th>
            <Th>Net Edge</Th>
            <Th>Left</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {markets.map((market) => {
            const slug = market.event_slug || market.slug || "";
            const diff = market.price_diff;
            const diffPct = market.price_diff_pct;
            const isAccepting = market.accepting_orders !== false && market.closed !== true;
            const edge = Number(market.net_edge ?? market.edge);
            const upAsk = Number(market.best_ask_up ?? 0);
            const downAsk = Number(market.best_ask_down ?? 0);
            const total = upAsk + downAsk;
            const upPct = total > 0 ? (upAsk / total) * 100 : 50;
            const isBelowTarget =
              market.price_to_beat != null &&
              market.current_price != null &&
              market.current_price < market.price_to_beat;

            return (
              <tr
                key={getMarketKey(market)}
                className="group transition-colors hover:bg-white/[0.025]"
              >
                {/* Asset */}
                <td className="px-3 py-3">
                  <AssetBadge asset={market.asset} />
                </td>

                {/* TF */}
                <td className="px-3 py-3">
                  <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs font-mono font-medium text-muted-foreground">
                    {market.timeframe}
                  </span>
                </td>

                {/* Slug */}
                <td className="max-w-[180px] px-3 py-3">
                  {slug ? (
                    <a
                      href={`https://polymarket.com/event/${slug}`}
                      target="_blank"
                      rel="noreferrer"
                      title={slug}
                      className="flex items-center gap-1 truncate text-xs text-primary/80 underline-offset-4 hover:text-primary hover:underline"
                    >
                      <span className="truncate">
                        {formatMarketWindow({
                          timeframe: market.timeframe,
                          window_start_timestamp: market.window_start_timestamp,
                          end_date: market.end_date,
                          market_slug: market.slug || market.event_slug || market.market_slug,
                        }) || slug}
                      </span>
                      <ExternalLink className="h-2.5 w-2.5 flex-shrink-0 opacity-60" />
                    </a>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </td>

                {/* Target */}
                <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                  {formatNumber(market.price_to_beat, 2) || "—"}
                </td>

                {/* Current */}
                <td className={cn("px-3 py-3 font-mono text-xs font-semibold", isBelowTarget ? "text-orange-400" : "text-sky-300")}>
                  {formatNumber(market.current_price, 2) || "—"}
                </td>

                {/* Diff */}
                <td className="px-3 py-3">
                  {diff != null ? (
                    <div className={cn("flex flex-col", diff >= 0 ? "text-emerald-400" : "text-red-400")}>
                      <span className="text-xs font-bold">
                        {diff >= 0 ? "+" : ""}${diff.toFixed(2)}
                      </span>
                      <span className="text-[10px] opacity-70">
                        {diffPct != null ? `${diffPct >= 0 ? "+" : ""}${diffPct.toFixed(2)}%` : ""}
                      </span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </td>

                {/* YES/NO bar */}
                <td className="px-3 py-3">
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px]">
                      <span className="font-mono font-semibold text-emerald-400">
                        {formatBidAsk(market.best_bid_up, market.best_ask_up)}
                      </span>
                      <span className="font-mono font-semibold text-red-400">
                        {formatBidAsk(market.best_bid_down, market.best_ask_down)}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-red-500/70">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400"
                        style={{ width: `${upPct}%` }}
                      />
                    </div>
                  </div>
                </td>

                {/* Edge */}
                <td className="px-3 py-3">
                  {Number.isFinite(edge) && edge > 0 ? (
                    <span className="inline-flex items-center rounded-md bg-emerald-500/15 px-2 py-0.5 text-xs font-bold text-emerald-400">
                      +{edge.toFixed(4)}
                    </span>
                  ) : Number.isFinite(edge) && edge < 0 ? (
                    <span className="inline-flex items-center rounded-md bg-red-500/10 px-2 py-0.5 text-xs font-bold text-red-400">
                      {edge.toFixed(4)}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground/40">—</span>
                  )}
                </td>

                {/* Time left */}
                <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                  {market.seconds_left != null ? (
                    <span className={market.seconds_left < 300 ? "text-orange-400" : ""}>
                      {`${Math.floor(market.seconds_left / 60)}:${String(market.seconds_left % 60).padStart(2, "0")}`}
                    </span>
                  ) : "—"}
                </td>

                {/* Status */}
                <td className="px-3 py-3">
                  <div className="flex items-center gap-1.5">
                    <span className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      isAccepting ? "bg-emerald-400" : "bg-slate-500"
                    )} />
                    <span className={cn("text-xs font-medium", isAccepting ? "text-emerald-400" : "text-muted-foreground")}>
                      {isAccepting ? "Open" : "Closed"}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
      {children}
    </th>
  );
}
