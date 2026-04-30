import type { CopyOverviewPayload, WsEvent } from "@/types";

const COPY_OVERVIEW_POLL_MS = 5000;

export function getHeaderMetrics(overview: CopyOverviewPayload | null) {
  return {
    trackedWallets: overview?.summary.wallet_count ?? 0,
    openPositions: overview?.summary.open_positions ?? 0,
    totalPnl: overview?.summary.realized_pnl ?? 0,
  };
}

export function getCopyOverviewPollMs(socketOnline: boolean): number | null {
  return socketOnline ? null : COPY_OVERVIEW_POLL_MS;
}

export function getOverviewRuntime(overview: CopyOverviewPayload | null) {
  return overview?.runtime ?? null;
}

export function shouldRefreshCopyOverview(event: WsEvent): boolean {
  if (
    event.type === "positions"
    || event.type === "order_placed"
    || event.type === "market_resolved"
    || event.type === "trade_resolved"
    || event.type === "bot_status"
  ) {
    return true;
  }

  if (event.type !== "log") {
    return false;
  }

  const message = String(event.payload.message || "").toLowerCase();
  return message.includes("[copy_") || message.startsWith("copy bot ") || message.startsWith("copy wallet ");
}
