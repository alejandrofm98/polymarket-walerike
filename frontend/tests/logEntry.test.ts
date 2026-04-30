import assert from "node:assert/strict";
import { formatLogEntry, parseLogEntry } from "../src/lib/logEntry.ts";

const roundTrip = parseLogEntry(formatLogEntry("settings saved", new Date("2024-01-01T13:23:45")));
assert.equal(roundTrip.message, "settings saved");
assert.notEqual(roundTrip.time, "");

assert.deepEqual(
  parseLogEntry("1:23:45 PM copied trade approved"),
  { time: "1:23:45 PM", message: "copied trade approved" },
);

assert.deepEqual(
  parseLogEntry("13:23:45 copied trade approved"),
  { time: "13:23:45", message: "copied trade approved" },
);

assert.deepEqual(
  parseLogEntry("ws connected"),
  { time: "", message: "ws connected" },
);
