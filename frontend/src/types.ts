export type View = "markets" | "settings" | "logs";

export type Runtime = {
  status?: string;
  running?: boolean;
  paused?: boolean;
  paper_mode?: boolean;
};

export type Config = {
  capital_per_trade: number;
  min_margin_for_arbitrage: number;
  entry_threshold: number;
  max_sum_avg: number;
  max_buys_per_side: number;
  shares_per_order: number;
  paper_mode: boolean;
  enabled_markets: Record<string, string[]>;
};

export type Market = {
  asset?: string;
  timeframe?: string;
  event_slug?: string;
  slug?: string;
  market_id?: string;
  condition_id?: string;
  market_slug?: string;
  window_start_timestamp?: number;
  price_to_beat?: number | null;
  current_price?: number | null;
  price_diff?: number | null;
  price_diff_pct?: number | null;
  best_bid_up?: number | null;
  best_ask_up?: number | null;
  best_bid_down?: number | null;
  best_ask_down?: number | null;
  edge?: number | null;
  net_edge?: number | null;
  seconds_left?: number | null;
  accepting_orders?: boolean;
  closed?: boolean;
  target_price_source?: string;
  end_date?: string;
};

export type Trade = {
  trade_id?: string;
  market?: string;
  asset?: string;
  side?: string;
  size?: number;
  status?: string;
  pnl?: number;
  entry_price?: number;
  exit_price?: number;
  opened_at?: number;
  closed_at?: number;
  metadata?: {
    timeframe?: string;
    market_slug?: string;
    end_date?: string;
    window_start_timestamp?: number;
  };
};

export type Position = {
  asset?: string;
  side?: string;
  size?: number;
  avg_price?: number;
  price?: number;
  market?: string;
  cost?: number;
  timeframe?: string;
  market_slug?: string;
  end_date?: string;
  window_start_timestamp?: number;
};

export type WsEvent = {
  type: string;
  payload: Record<string, any>;
};
