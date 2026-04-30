import assert from "node:assert/strict";
import type { CopyWalletConfig } from "../src/types.ts";
import { getTrackedWalletBalancesKey } from "../src/lib/trackedWalletBalances.ts";

const baseWallets: CopyWalletConfig[] = [
  { address: "0xabc", enabled: true, sizing_mode: "leader_percent", fixed_amount: 10 },
  { address: "0xdef", enabled: false, sizing_mode: "fixed", fixed_amount: 25 },
];

assert.equal(
  getTrackedWalletBalancesKey(baseWallets),
  getTrackedWalletBalancesKey(baseWallets.map((wallet) => ({ ...wallet }))),
);

assert.notEqual(
  getTrackedWalletBalancesKey(baseWallets),
  getTrackedWalletBalancesKey([{ ...baseWallets[0], address: "0x999" }, baseWallets[1]]),
);

assert.equal(getTrackedWalletBalancesKey([]), "");
