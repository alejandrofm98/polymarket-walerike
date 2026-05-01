export type View = "overview" | "account" | "settings";

export type Runtime = {
  status?: string;
  running?: boolean;
  paused?: boolean;
};

export type Config = {
  copy_wallets: CopyWalletConfig[];
  poll_interval_seconds: number;
  solo_log?: boolean;
};

export type CopyWalletConfig = {
  address: string;
  enabled: boolean;
  sizing_mode: "leader_percent" | "fixed";
  fixed_amount: number;
};

export type CopyTradeMetadata = {
  copy_trade?: boolean;
  leader_wallet?: string;
  leader_event_id?: string;
  leader_price?: number;
  leader_size?: number;
  leader_notional?: number;
  leader_portfolio_value?: number | null;
  sizing_mode?: CopyWalletConfig["sizing_mode"];
  fixed_amount?: number;
  market_slug?: string;
  timeframe?: string;
  asset?: string;
  [key: string]: unknown;
};

export type CopyTradeItem = Omit<Trade, "metadata"> & {
  metadata?: Trade["metadata"] & CopyTradeMetadata;
};

export type CopyWalletOverviewStats = {
  realized_pnl: number;
  closed_count: number;
};

export type CopyWalletOverviewConfig = Pick<CopyWalletConfig, "address" | "enabled" | "fixed_amount"> & {
  sizing_mode: CopyWalletConfig["sizing_mode"] | null;
};

export type CopyWalletOverview = {
  address: string;
  configured: CopyWalletOverviewConfig;
  tracked_balance?: TrackedWalletBalance;
  open_positions: CopyTradeItem[];
  closed_trades: CopyTradeItem[];
  stats: CopyWalletOverviewStats;
};

export type CopyOverviewPayload = {
  runtime: Runtime;
  summary: {
    wallet_count: number;
    open_positions: number;
    closed_trades: number;
    realized_pnl: number;
  };
  wallets: CopyWalletOverview[];
};

export type TrackedWalletBalance = {
  address: string;
  enabled: boolean;
  cash?: number;
  positions_value?: number;
  total?: number;
  pusd_balance?: number | null;
  error?: string;
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
  reason?: string | null;
  cash_balance?: number | null;
  allowance?: number | null;
  portfolio_value?: number | null;
  total_balance?: number | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
  positions: AccountPosition[];
  trades: AccountTrade[];
  errors: AccountError[];
};
