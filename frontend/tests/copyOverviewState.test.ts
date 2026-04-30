import assert from "node:assert/strict";
import {
  getCopyOverviewPollMs,
  getHeaderMetrics,
  getOverviewRuntime,
  shouldRefreshCopyOverview,
} from "../src/lib/copyOverviewState.ts";
import type { CopyOverviewPayload, WsEvent } from "../src/types";

const overview: CopyOverviewPayload = {
  runtime: { running: true, paused: false, paper_mode: true },
  summary: {
    wallet_count: 2,
    open_positions: 3,
    closed_trades: 4,
    realized_pnl: 18.75,
  },
  wallets: [],
};

assert.deepEqual(getHeaderMetrics(null), {
  trackedWallets: 0,
  openPositions: 0,
  totalPnl: 0,
});

assert.deepEqual(getHeaderMetrics(overview), {
  trackedWallets: 2,
  openPositions: 3,
  totalPnl: 18.75,
});

assert.equal(getCopyOverviewPollMs(true), null);
assert.equal(getCopyOverviewPollMs(false), 5000);
assert.deepEqual(getOverviewRuntime(null), null);
assert.deepEqual(getOverviewRuntime(overview), overview.runtime);

assert.equal(shouldRefreshCopyOverview({ type: "positions", payload: { positions: [] } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "order_placed", payload: {} } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "trade_resolved", payload: {} } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "bot_status", payload: { running: true, ticks: 12 } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "log", payload: { message: "[COPY_TRADE] action=buy" } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "log", payload: { message: "copy bot started" } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "log", payload: { message: "copy wallet poll complete wallet=0x1 total=150" } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "log", payload: { message: "copy wallet poll failed wallet=0x1" } } as WsEvent), true);
assert.equal(shouldRefreshCopyOverview({ type: "log", payload: { message: "market tick only" } } as WsEvent), false);
assert.equal(shouldRefreshCopyOverview({ type: "market_tick", payload: { markets: [] } } as WsEvent), false);
