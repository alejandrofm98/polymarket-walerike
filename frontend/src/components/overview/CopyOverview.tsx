import { CopyWalletPanel } from "@/components/overview/CopyWalletPanel";
import { LogsView } from "@/components/LogsView";
import { EmptyState, KpiCard } from "@/components/shared";
import { formatNumber } from "@/lib/utils2";
import type { CopyOverviewPayload } from "@/types";

interface CopyOverviewProps {
  overview: CopyOverviewPayload | null;
  loading?: boolean;
  logs: string[];
  onClearLogs: () => void;
}

export function CopyOverview({ overview, loading = false, logs, onClearLogs }: CopyOverviewProps) {
  if (!overview) {
    return <EmptyState>{loading ? "Loading copy overview..." : "Copy overview unavailable"}</EmptyState>;
  }

  const { summary, wallets } = overview;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Wallets" value={String(summary.wallet_count)} sublabel="Configured or active leaders" glow="blue" />
        <KpiCard label="Open Positions" value={String(summary.open_positions)} sublabel="Copied positions still open" glow="amber" />
        <KpiCard label="Closed Trades" value={String(summary.closed_trades)} sublabel="Copied trades resolved" glow="blue" />
        <KpiCard
          label="Realized PnL"
          value={`${summary.realized_pnl >= 0 ? "+" : ""}$${formatNumber(summary.realized_pnl, 2) || "0.00"}`}
          valueClassName={summary.realized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}
          sublabel="Aggregate across copy wallets"
          glow={summary.realized_pnl >= 0 ? "green" : "red"}
        />
      </section>

      <section className="grid gap-4">
        {wallets.length ? wallets.map((wallet) => <CopyWalletPanel key={wallet.address} wallet={wallet} />) : <EmptyState>No copy wallets configured yet</EmptyState>}
      </section>

      <section>
        <LogsView logs={logs} onClear={onClearLogs} compact />
      </section>
    </div>
  );
}
