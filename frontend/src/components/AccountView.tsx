import type { ReactNode } from "react";
import { AlertTriangle, RefreshCcw, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared";
import { cn } from "@/lib/utils";
import type { AccountPosition, AccountSummary, AccountTrade } from "@/types";

export function AccountView({ account, loading, onRefresh }: { account: AccountSummary | null; loading: boolean; onRefresh: () => void }) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
        <div className="flex items-start justify-between gap-4 border-b border-white/5 px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Wallet className="h-4 w-4 text-primary" />
              Real Polymarket Account
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground/60">
              Live wallet, positions, trades, and PnL. Paper bot data remains separate.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="border-white/10 bg-white/[0.03] hover:bg-white/8">
            <RefreshCcw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
        <div className="p-4">
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
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {account.reason || "Real account data unavailable"}
        </div>
      )}
      {account.errors.length > 0 && (
        <div className="space-y-2">
          {account.errors.map((error) => (
            <div key={`${error.source}-${error.message}`} className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-200">
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
    <div className="rounded-lg border border-white/8 bg-white/[0.03] px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">{label}</div>
      <div className={cn("mt-1 font-mono text-2xl font-bold", tone === "good" && "text-emerald-400", tone === "bad" && "text-red-400")}>{value}</div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02]">
      <div className="border-b border-white/5 px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground/60">{count} row{count === 1 ? "" : "s"}</p>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function PositionsTable({ positions }: { positions: AccountPosition[] }) {
  if (!positions.length) return <EmptyState>No real positions</EmptyState>;
  return (
    <div className="overflow-x-auto rounded-xl border border-white/8">
      <table className="w-full text-sm">
        <thead className="border-b border-white/8 bg-white/[0.02] text-[10px] uppercase tracking-widest text-muted-foreground/60">
          <tr>{["Market", "Asset", "Side", "Size", "Avg", "Value", "PnL"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {positions.map((position, index) => {
            const value = num(position.currentValue ?? position.current_value ?? position.value);
            const pnl = num(position.cashPnl ?? position.unrealized_pnl ?? position.pnl);
            return (
              <tr key={`${position.market}-${index}`} className="hover:bg-white/[0.02]">
                <td className="max-w-[220px] truncate px-3 py-2 font-mono text-xs text-muted-foreground/70">{String(position.market || "-")}</td>
                <td className="px-3 py-2 font-semibold">{position.asset || "-"}</td>
                <td className="px-3 py-2 font-semibold">{position.side || "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{num(position.size)?.toFixed(2) ?? "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{num(position.avg_price ?? position.avgPrice)?.toFixed(3) ?? "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{money(value)}</td>
                <td className={cn("px-3 py-2 font-mono text-xs font-bold", pnl != null && (pnl >= 0 ? "text-emerald-400" : "text-red-400"))}>{money(pnl, true)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({ trades }: { trades: AccountTrade[] }) {
  if (!trades.length) return <EmptyState>No real trades</EmptyState>;
  return (
    <div className="overflow-x-auto rounded-xl border border-white/8">
      <table className="w-full text-sm">
        <thead className="border-b border-white/8 bg-white/[0.02] text-[10px] uppercase tracking-widest text-muted-foreground/60">
          <tr>{["ID", "Market", "Side", "Size", "Price", "Fee", "Time", "PnL"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {trades.map((trade, index) => {
            const pnl = num(trade.realized_pnl ?? trade.pnl);
            return (
              <tr key={`${trade.id}-${index}`} className="hover:bg-white/[0.02]">
                <td className="max-w-[120px] truncate px-3 py-2 font-mono text-xs text-muted-foreground/70">{trade.id || "-"}</td>
                <td className="max-w-[220px] truncate px-3 py-2 font-mono text-xs text-muted-foreground/70">{trade.market || "-"}</td>
                <td className="px-3 py-2 font-semibold">{trade.side || "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{num(trade.size)?.toFixed(2) ?? "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{num(trade.price)?.toFixed(3) ?? "-"}</td>
                <td className="px-3 py-2 font-mono text-xs">{money(num(trade.fee))}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground/70">{date(trade.timestamp)}</td>
                <td className={cn("px-3 py-2 font-mono text-xs font-bold", pnl != null && (pnl >= 0 ? "text-emerald-400" : "text-red-400"))}>{money(pnl, true)}</td>
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

function date(value: unknown): string {
  const parsed = num(value);
  if (parsed == null) return "-";
  const millis = parsed > 10_000_000_000 ? parsed : parsed * 1000;
  return new Date(millis).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
