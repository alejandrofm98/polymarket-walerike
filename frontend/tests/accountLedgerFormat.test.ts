import assert from "node:assert/strict";
import { formatLedgerRow, relativeLedgerTime } from "../src/lib/accountLedgerFormat.ts";

const trade = {
  id: "0xabc",
  market: "0xmarket",
  side: "BUY",
  outcome: "Up",
  size: 5,
  price: 0.48,
  timestamp: 1777320000,
  raw: {
    eventTitle: "Bitcoin Up or Down - Apr 29, 8:45AM-8:50AM ET",
  },
};

const row = formatLedgerRow(trade, "trade");

assert.equal(row.title, "Bitcoin Up or Down - Apr 29, 8:45AM-8:50AM ET");
assert.equal(row.activity, "Comprar");
assert.equal(row.outcome, "Up");
assert.equal(row.badge, "Up 48c");
assert.equal(row.shares, "5.00");
assert.equal(row.value, "-$2.40");
assert.equal(row.time, "Apr 27, 2026, 8:00 PM");
assert.equal(relativeLedgerTime(1777320000, 1777406400), "1d hace");

const position = formatLedgerRow({ market_slug: "bitcoin-up-or-down-apr-29-845am-850am-et", side: "DOWN", size: 2.3, avg_price: 0.4 }, "position");

assert.equal(position.title, "Bitcoin Up Or Down Apr 29 845am 850am Et");
assert.equal(position.activity, "Posición");
assert.equal(position.outcome, "Down");
assert.equal(position.badge, "Down 40c");
assert.equal(position.shares, "2.30");
assert.equal(position.value, "-");

const accountPosition = formatLedgerRow({ asset: "BTC", side: "YES", size: 1.5, avg_price: 0.52 }, "position");

assert.equal(accountPosition.outcome, "Up");
assert.equal(accountPosition.badge, "Up 52c");

const rawOutcomeTrade = formatLedgerRow({ side: "BUY", size: 3, price: 0.31, raw: { outcome: "Down" } }, "trade");

assert.equal(rawOutcomeTrade.outcome, "Down");
assert.equal(rawOutcomeTrade.badge, "Down 31c");
