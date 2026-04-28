import assert from "node:assert/strict";
import { calculateAccountBalance, formatMarketWindow, formatTimeRemaining } from "../src/lib/utils2.ts";

assert.equal(
  formatMarketWindow({ timeframe: "5m", market_slug: "btc-updown-5m-1777360200" }),
  "April 28, 3:10-3:15AM ET",
);

assert.deepEqual(
  calculateAccountBalance({ cash_balance: 12.5, portfolio_value: 4.5 }),
  { cash: 12.5, portfolio: 4.5, total: 17 },
);

assert.deepEqual(
  calculateAccountBalance({ cash_balance: null, portfolio_value: 4.5 }),
  { cash: 0, portfolio: 4.5, total: 4.5 },
);

assert.equal(formatTimeRemaining(272), "04:32");
assert.equal(formatTimeRemaining(65), "01:05");
assert.equal(formatTimeRemaining(0), "00:00");
assert.equal(formatTimeRemaining(-4), "00:00");
assert.equal(formatTimeRemaining(null), "");
