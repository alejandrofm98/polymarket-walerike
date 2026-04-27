import assert from "node:assert/strict";
import { mergeMarketTick } from "../src/lib/marketMerge.js";

const previous = [{
  asset: "BTC",
  timeframe: "5m",
  event_slug: "btc-up-or-down",
  current_price: 100,
  price_to_beat: 95,
  price_diff: 5,
  price_diff_pct: 5.26,
  target_price_source: "crypto-price-api",
}];

const incoming = [{
  asset: "BTC",
  timeframe: "5m",
  event_slug: "btc-up-or-down",
  current_price: 101,
  price_to_beat: null,
  price_diff: null,
  price_diff_pct: null,
}];

assert.deepEqual(mergeMarketTick(previous, incoming), [{
  ...incoming[0],
  price_to_beat: 95,
  target_price_source: "crypto-price-api",
  price_diff: 6,
  price_diff_pct: 6.32,
}]);
