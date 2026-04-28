export type View = "markets" | "account" | "settings";

export type Runtime = {
  status?: string;
  running?: boolean;
  paused?: boolean;
  paper_mode?: boolean;
  requested_paper_mode?: boolean;
  live_trading?: boolean;
  live_sdk_available?: boolean;
  can_live_trade?: boolean;
  live_blocked?: boolean;
  live_block_reason?: string | null;
  mode_label?: string;
};

export type Config = {
  capital_per_trade: number;
  min_margin_for_arbitrage: number;
  entry_threshold: number;
  max_sum_avg: number;
  max_buys_per_side: number;
  paper_mode: boolean;
  enabled_markets: Record<string, string[]>;
  strategy_groups: Record<string, StrategyGroupConfig>;
  strategies: Record<string, StrategyConfig>;
};

export type StrategyGroupConfig = {
  enabled: boolean;
  max_orders_per_tick: number;
  capital_fraction: number;
};

export type StrategyConfig = {
  enabled: boolean;
  group: string;
  assets: string[];
  timeframes: string[];
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

export type AccountError = {
  source: string;
  message: string;
};

export type AccountPosition = Record<string, any> & {
  market?: string;
  asset?: string;
  side?: string;
  size?: number;
  avg_price?: number;
  avgPrice?: number;
  currentValue?: number;
  current_value?: number;
  value?: number;
  cashPnl?: number;
  unrealized_pnl?: number;
  pnl?: number;
};

export type AccountTrade = Record<string, any> & {
  id?: string;
  market?: string;
  side?: string;
  size?: number;
  price?: number;
  fee?: number;
  timestamp?: number;
  realized_pnl?: number;
  pnl?: number;
};

export type AccountSummary = {
  available: boolean;
  mode: "paper" | "live" | "unavailable";
  reason?: string | null;
  cash_balance?: number | null;
  allowance?: number | null;
  portfolio_value?: number | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
  positions: AccountPosition[];
  trades: AccountTrade[];
  errors: AccountError[];
};
