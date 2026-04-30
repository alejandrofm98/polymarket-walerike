import type { CopyWalletConfig } from "../types";

export function getTrackedWalletBalancesKey(copyWallets: CopyWalletConfig[] | undefined): string {
  if (!copyWallets?.length) return "";

  return JSON.stringify(copyWallets.map(({ address, enabled, sizing_mode, fixed_amount }) => ({
    address,
    enabled,
    sizing_mode,
    fixed_amount,
  })));
}
