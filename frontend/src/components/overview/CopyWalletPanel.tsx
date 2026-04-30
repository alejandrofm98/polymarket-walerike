import { CopyPositionList } from "@/components/overview/CopyPositionList";
import { CopyTradeHistory } from "@/components/overview/CopyTradeHistory";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/utils2";
import type { CopyWalletOverview } from "@/types";

interface CopyWalletPanelProps {
  wallet: CopyWalletOverview;
}

export function CopyWalletPanel({ wallet }: CopyWalletPanelProps) {
  const balance = wallet.tracked_balance;
  const config = wallet.configured;
  const realizedPnl = Number(wallet.stats.realized_pnl || 0);

  return (
    <Card className="editorial-panel rounded-[1.25rem] shadow-[0_20px_70px_rgba(0,0,0,0.22)]">
      <CardHeader className="space-y-4 border-b editorial-divider bg-gradient-to-r from-white/[0.04] to-transparent">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="editorial-kicker">Copy Wallet</div>
            <CardTitle className="editorial-title text-xl text-foreground">Leader mirror overview</CardTitle>
            <div className="font-mono text-xs text-muted-foreground/70 sm:text-sm">{wallet.address}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="border-white/10 bg-white/[0.04] text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              {config.enabled ? "Enabled" : "Disabled"}
            </Badge>
            {config.sizing_mode && (
              <Badge variant="outline" className="border-white/10 bg-white/[0.04] text-muted-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                {config.sizing_mode === "fixed" ? `Fixed $${formatNumber(config.fixed_amount, 2) || "0.00"}` : "Leader %"}
              </Badge>
            )}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <InfoTile label="Leader Balance" value={formatMoney(balance?.total)} />
          <InfoTile label="Leader Cash" value={formatMoney(balance?.cash)} />
          <InfoTile label="Open Positions" value={String(wallet.open_positions.length)} />
          <InfoTile label="Closed PnL" value={signedMoney(realizedPnl)} valueClass={realizedPnl >= 0 ? "text-emerald-400" : "text-red-400"} />
        </div>

        {balance?.error && <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">{balance.error}</div>}
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        <section className="editorial-subpanel overflow-hidden">
          <div className="border-b editorial-divider px-4 py-4">
            <div className="editorial-kicker">Exposure</div>
            <div className="flex items-center justify-between gap-2">
              <h3 className="editorial-title text-xl text-foreground">Open Copied Positions</h3>
              <span className="text-xs text-muted-foreground/60">{wallet.open_positions.length} active</span>
            </div>
          </div>
          <div className="p-4">
            <CopyPositionList positions={wallet.open_positions} />
          </div>
        </section>

        <section className="editorial-subpanel overflow-hidden">
          <div className="border-b editorial-divider px-4 py-4">
            <div className="editorial-kicker">Archive</div>
            <div className="flex items-center justify-between gap-2">
              <h3 className="editorial-title text-xl text-foreground">Closed Copied History</h3>
              <span className="text-xs text-muted-foreground/60">{wallet.stats.closed_count} closed</span>
            </div>
          </div>
          <div className="p-4">
            <CopyTradeHistory trades={wallet.closed_trades} />
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

function InfoTile({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="editorial-subpanel px-4 py-3">
      <div className="editorial-kicker">{label}</div>
      <div className={`mt-2 font-mono text-sm ${valueClass || "text-foreground"}`}>{value}</div>
    </div>
  );
}

function formatMoney(value?: number) {
  if (value == null) return "-";
  return `$${formatNumber(value, 2) || "0.00"}`;
}

function signedMoney(value: number) {
  return `${value >= 0 ? "+" : ""}$${formatNumber(value, 2) || "0.00"}`;
}
