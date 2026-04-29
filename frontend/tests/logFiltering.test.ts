import assert from "node:assert/strict";
import { shouldShowRealtimeLog } from "../src/lib/logFiltering.ts";

assert.equal(shouldShowRealtimeLog("[BET_SKIP] strategy=late_window_discount_hedge reason=risk_rejected"), true);
assert.equal(shouldShowRealtimeLog("[ORDER_ATTEMPT] attempt=1"), true);
assert.equal(shouldShowRealtimeLog("market tick only"), false);
assert.equal(
  shouldShowRealtimeLog("[BET_SKIP] strategy=late_window_discount_hedge reason=risk_rejected", {
    strategy_groups: { conservative_btc_5m: { enabled: true, max_orders_per_tick: 2, capital_fraction: 1 } },
    strategies: {
      late_window_discount_hedge: { enabled: false, group: "conservative_btc_5m", assets: ["BTC"], timeframes: ["5m"] },
    },
  }),
  false,
);
assert.equal(
  shouldShowRealtimeLog("[BET_SKIP] strategy=late_window_discount_hedge reason=risk_rejected", {
    strategy_groups: { conservative_btc_5m: { enabled: true, max_orders_per_tick: 2, capital_fraction: 1 } },
    strategies: {
      late_window_discount_hedge: { enabled: true, group: "conservative_btc_5m", assets: ["BTC"], timeframes: ["5m"] },
    },
  }),
  true,
);
assert.equal(
  shouldShowRealtimeLog("[BET_SKIP] strategy=late_window_discount_hedge reason=risk_rejected", {
    strategy_groups: { conservative_btc_5m: { enabled: false, max_orders_per_tick: 2, capital_fraction: 1 } },
    strategies: {
      late_window_discount_hedge: { enabled: true, group: "conservative_btc_5m", assets: ["BTC"], timeframes: ["5m"] },
    },
  }),
  false,
);
