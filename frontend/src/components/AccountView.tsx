import type { ReactNode } from "react";
import { AlertTriangle, RefreshCcw, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared";
import { formatLedgerRow } from "@/lib/accountLedgerFormat";
import { cn } from "@/lib/utils";
import type { AccountPosition, AccountSummary, AccountTrade } from "@/types";

export function AccountView({ account, loading, onRefresh }: { account: AccountSummary | null; loading: boolean; onRefresh: () => void }) {
  return (
    <div className="space-y-4">
      <div className="editorial-panel">
        <div className="relative flex items-start justify-between gap-4 border-b editorial-divider px-5 py-5">
          <div>
            <div className="editorial-kicker">Account Ledger</div>
            <h2 className="editorial-title mt-2 flex items-center gap-2 text-2xl text-foreground">
              <Wallet className="h-4 w-4 text-primary" />
              Real Polymarket Account
            </h2>
            <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground/70">
              Wallet, positions, trades, and PnL from Polymarket.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="border-white/10 bg-white/[0.03] hover:bg-white/8">
            <RefreshCcw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
        <div className="relative p-4">
          {!account ? <EmptyState>{loading ? "Loading account" : "No account data loaded"}</EmptyState> : <AccountContent account={account} />}
        </div>
      </div>
    </div>
  );
}

function AccountContent({ account }: { account: AccountSummary }) {
  return (
    <div className="space-y-4">
      {!account.available && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {account.reason || "Real account data unavailable"}
        </div>
      )}
      {account.errors.length > 0 && (
        <div className="space-y-2">
          {account.errors.map((error) => (
            <div key={`${error.source}-${error.message}`} className="flex items-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-200">
              <AlertTriangle className="h-4 w-4" />
              <span className="font-semibold">{error.source}</span>
              <span>{error.message}</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-5">
        <Kpi label="Total" value={money(account.total_balance)} />
        <Kpi label="Cash" value={money(account.cash_balance)} />
        <Kpi label="Portfolio" value={money(account.portfolio_value)} />
        <Kpi label="Realized PnL" value={money(account.realized_pnl, true)} tone={tone(account.realized_pnl)} />
        <Kpi label="Unrealized PnL" value={money(account.unrealized_pnl, true)} tone={tone(account.unrealized_pnl)} />
      </div>
      <Section title="Open Real Positions" count={account.positions.length}>
        <PositionsTable positions={account.positions} />
      </Section>
      <Section title="Real Trades" count={account.trades.length}>
        <TradesTable trades={account.trades} />
      </Section>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" | "neutral" }) {
  return (
    <div className="editorial-subpanel px-4 py-3">
      <div className="editorial-kicker">{label}</div>
      <div className={cn("mt-2 font-mono text-2xl font-bold", tone === "good" && "text-emerald-400", tone === "bad" && "text-red-400")}>{value}</div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <div className="editorial-subpanel overflow-hidden">
      <div className="border-b editorial-divider px-4 py-4">
        <div className="editorial-kicker">Account Detail</div>
        <h3 className="editorial-title mt-1 text-xl text-foreground">{title}</h3>
        <p className="mt-1 text-xs text-muted-foreground/60">{count} row{count === 1 ? "" : "s"}</p>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function PositionsTable({ positions }: { positions: AccountPosition[] }) {
  if (!positions.length) return <EmptyState>No real positions</EmptyState>;
  return (
    <LedgerTable items={positions} kind="position" />
  );
}

function TradesTable({ trades }: { trades: AccountTrade[] }) {
  if (!trades.length) return <EmptyState>No real trades</EmptyState>;
  return <LedgerTable items={trades} kind="trade" />;
}

function LedgerTable({ items, kind }: { items: Array<AccountPosition | AccountTrade>; kind: "position" | "trade" }) {
  return (
    <div className="editorial-table">
      <table>
        <thead>
          <tr>{["Actividad", "Mercado", "Shares", "Valor", "Fecha"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const row = formatLedgerRow(item, kind);
            return (
              <tr key={`${item.id || item.market || row.title}-${index}`} className="hover:bg-white/[0.025]">
                <td className="px-3 py-3 font-semibold text-foreground">{row.activity}</td>
                <td className="max-w-[520px] px-3 py-3">
                  <div className="truncate font-semibold text-foreground" title={row.title}>{row.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground/70">
                    <span className={cn("rounded-full px-2 py-0.5 font-bold", row.tone === "up" && "bg-emerald-400/15 text-emerald-300", row.tone === "down" && "bg-red-400/15 text-red-300", row.tone === "neutral" && "bg-white/10 text-muted-foreground")}>{row.badge}</span>
                    <span>{row.shares} shares</span>
                  </div>
                </td>
                <td className="px-3 py-3 font-mono text-xs text-foreground">{row.shares}</td>
                <td className={cn("px-3 py-3 font-mono text-xs font-bold", row.value.startsWith("+") && "text-emerald-400", row.value.startsWith("-") && row.value !== "-" && "text-red-400")}>{row.value}</td>
                <td className="px-3 py-3 text-xs text-muted-foreground/70">{row.time}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: unknown, signed = false): string {
  const parsed = num(value);
  if (parsed == null) return "-";
  const prefix = signed && parsed > 0 ? "+" : "";
  return `${prefix}$${parsed.toFixed(2)}`;
}

function tone(value: unknown): "good" | "bad" | "neutral" {
  const parsed = num(value);
  if (parsed == null || parsed === 0) return "neutral";
  return parsed > 0 ? "good" : "bad";
}
