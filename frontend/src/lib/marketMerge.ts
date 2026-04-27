type MarketLike = {
  asset?: string;
  timeframe?: string;
  event_slug?: string;
  slug?: string;
  current_price?: number | null;
  price_to_beat?: number | null;
  price_diff?: number | null;
  price_diff_pct?: number | null;
  target_price_source?: string;
};

function getMergeKey(market: MarketLike) {
  return `${market.asset || "?"}:${market.timeframe || "?"}:${market.event_slug || market.slug || "?"}`;
}

export function mergeMarketTick<T extends MarketLike>(previous: MarketLike[], incoming: T[]): T[] {
  if (!previous.length) return incoming;

  const previousByKey = new Map(previous.map((market) => [getMergeKey(market), market]));
  return incoming.map((market) => {
    const previousMarket = previousByKey.get(getMergeKey(market));
    if (!previousMarket || market.price_to_beat != null || previousMarket.price_to_beat == null) {
      return market;
    }

    const merged = {
      ...market,
      price_to_beat: previousMarket.price_to_beat,
      target_price_source: previousMarket.target_price_source,
    };

    if (merged.current_price != null) {
      const diff = merged.current_price - previousMarket.price_to_beat;
      merged.price_diff = Math.round(diff * 100) / 100;
      merged.price_diff_pct = previousMarket.price_to_beat !== 0
        ? Math.round((diff / previousMarket.price_to_beat) * 10000) / 100
        : null;
    }

    return merged;
  });
}
