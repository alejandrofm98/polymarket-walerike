import assert from "node:assert/strict";
import { getLogPresentation, tokenizeLogMessage } from "../src/lib/logPresentation.ts";

assert.deepEqual(getLogPresentation("[TRADE] APPROVED: placing order"), {
  label: "TRADE",
  tone: "trade",
});

assert.deepEqual(getLogPresentation("[BET_DECISION] action=PAIR_SKIPPED reason=cap"), {
  label: "DECISION",
  tone: "decision",
});

assert.deepEqual(getLogPresentation("ws connected"), {
  label: "LIVE",
  tone: "connected",
});

assert.deepEqual(getLogPresentation("order failed: missing_order_id"), {
  label: "ERROR",
  tone: "error",
});

assert.deepEqual(getLogPresentation("settings saved"), {
  label: "INFO",
  tone: "info",
});

assert.deepEqual(
  tokenizeLogMessage("[BET_SKIP] market=BTC:5m strategy=fee_aware_pair_arbitrage reason=no_liquidity_too_low"),
  [
    { text: "[BET_SKIP]", kind: "tag" },
    { text: "market=BTC:5m", kind: "market" },
    { text: "strategy=fee_aware_pair_arbitrage", kind: "strategy", colorClass: "text-orange-200 border-orange-300/25 bg-orange-300/10" },
    { text: "reason=no_liquidity_too_low", kind: "field" },
  ]
);
