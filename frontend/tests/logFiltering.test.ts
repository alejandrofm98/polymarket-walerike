import assert from "node:assert/strict";
import { shouldShowRealtimeLog } from "../src/lib/logFiltering.ts";

assert.equal(shouldShowRealtimeLog("[BET_SKIP] strategy=late_window_discount_hedge reason=risk_rejected"), true);
assert.equal(shouldShowRealtimeLog("[BET_EVAL] mode=PAPER strategies=0"), true);
assert.equal(shouldShowRealtimeLog("[ORDER_ATTEMPT] attempt=1"), true);
assert.equal(shouldShowRealtimeLog("market tick only"), false);
