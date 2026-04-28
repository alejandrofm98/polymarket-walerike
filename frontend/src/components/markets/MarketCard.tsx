import { memo, useEffect, useState } from "react";
import { formatMarketWindow, formatTimeRemaining } from "@/lib/utils2";
import type { Market } from "@/types";

function formatCurrency2(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function getMarketUrl(market: Market) {
  const slug = market.slug || market.event_slug || market.market_slug;
  return slug ? `https://polymarket.com/event/${slug}` : null;
}

export const MarketCard = memo(function MarketCard({ market }: { market: Market }) {
  const edge = Number(market.net_edge ?? market.edge);
  const upAsk = Number(market.best_ask_up ?? 0);
  const downAsk = Number(market.best_ask_down ?? 0);
  const total = upAsk + downAsk;
  const upPct = total > 0 ? (upAsk / total) * 100 : 50;
  const downPct = 100 - upPct;

  const targetPrice = market.price_to_beat;
  const currentPrice = market.current_price;
  const hasPriceDistance = targetPrice != null && currentPrice != null && Number(targetPrice) !== 0;
  const signedDistance = hasPriceDistance ? Number(currentPrice) - Number(targetPrice) : 0;
  const distancePct = hasPriceDistance ? Math.abs((signedDistance / Number(targetPrice)) * 100) : 0;
  const isAboveTarget = signedDistance >= 0;
  const marketUrl = getMarketUrl(market);

  const secondsLeftFromMarket = Number(market.seconds_left);
  const initialSecondsLeft = Number.isFinite(secondsLeftFromMarket) ? Math.max(0, secondsLeftFromMarket) : null;
  const [secondsLeft, setSecondsLeft] = useState<number | null>(initialSecondsLeft);

  useEffect(() => {
    setSecondsLeft(initialSecondsLeft);
  }, [initialSecondsLeft]);

  useEffect(() => {
    if (secondsLeft == null || secondsLeft <= 0) return;

    const intervalId = window.setInterval(() => {
      setSecondsLeft((current) => (current == null ? current : Math.max(0, current - 1)));
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [secondsLeft]);

  const isGoodEdge = edge > 1.5;
  const timeRemaining = formatTimeRemaining(secondsLeft);
  const timeRemainingClass =
    secondsLeft === 0
      ? "text-red-400"
      : secondsLeft != null && secondsLeft < 60
        ? "text-amber-300"
        : "text-neutral-500";
  const marketWindow = formatMarketWindow({
    timeframe: market.timeframe,
    window_start_timestamp: market.window_start_timestamp,
    end_date: market.end_date,
    market_slug: market.slug || market.event_slug || market.market_slug,
  });

  const CardRoot = marketUrl ? "a" : "div";

  return (
    <CardRoot
      className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-neutral-900 p-5 no-underline transition-colors hover:border-white/20"
      href={marketUrl || undefined}
      target={marketUrl ? "_blank" : undefined}
      rel={marketUrl ? "noreferrer" : undefined}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-medium text-neutral-400">
          {market.asset} · {market.timeframe}
        </span>
        <span
          className={
            isGoodEdge
              ? "rounded-full bg-green-900/40 px-2.5 py-0.5 text-[11px] font-medium text-green-400"
              : "rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-medium text-neutral-500"
          }
        >
          {isGoodEdge ? "Buen edge" : "Bajo edge"}
        </span>
      </div>

      {timeRemaining && (
        <div className={`-mt-2 text-right text-[11px] font-medium tabular-nums ${timeRemainingClass}`}>
          Cierra en {timeRemaining}
        </div>
      )}

      {/* Title */}
      <p className="text-sm font-medium leading-snug text-neutral-100 line-clamp-2">
        {marketWindow || "Market"}
      </p>

      {/* Divider */}
      <div className="h-px bg-white/8" />

      {/* Price boxes */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-white/5 p-3">
          <div className="text-[11px] text-neutral-500">Price to beat</div>
          <div className="mt-1 font-mono text-sm font-medium text-neutral-100">
            {formatCurrency2(targetPrice)}
          </div>
        </div>
        <div className="rounded-xl bg-white/5 p-3">
          <div className="text-[11px] text-neutral-500">Current price</div>
          <div className="mt-1 font-mono text-sm font-medium text-neutral-100">
            {formatCurrency2(currentPrice)}
          </div>
        </div>
      </div>

      {/* Price diff */}
      {hasPriceDistance && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-neutral-500">Price diff</span>
          <span
            className={
              isAboveTarget
                ? "font-mono font-medium text-green-400"
                : "font-mono font-medium text-red-400"
            }
          >
            {isAboveTarget ? "↑" : "↓"} {formatCurrency2(Math.abs(signedDistance))} · {distancePct.toFixed(2)}%
          </span>
        </div>
      )}

      {/* Probability */}
      <div className="flex flex-col gap-2">
        <div className="flex justify-between text-xs">
          <span className="font-medium text-green-400">UP ({upPct.toFixed(1)}%)</span>
          <span className="font-medium text-red-400">DOWN ({downPct.toFixed(1)}%)</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-red-500">
          <div
            className="h-full rounded-full bg-green-500 transition-all duration-500 ease-out"
            style={{ width: `${Math.max(5, Math.min(95, upPct))}%` }}
          />
        </div>
      </div>
    </CardRoot>
  );
});
