import { Wallet, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { calculateAccountBalance, formatNumber } from "@/lib/utils2";
import type { AccountSummary } from "@/types";

interface AccountHeroPanelProps {
  account: AccountSummary | null;
  loading: boolean;
}

export function AccountHeroPanel({ account, loading }: AccountHeroPanelProps) {
  if (!account) {
    return (
      <div className="editorial-panel flex min-h-24 items-center gap-2.5 px-5 py-5 text-sm text-muted-foreground/70">
        <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
        {loading ? "Loading account ledger..." : "No account data loaded."}
      </div>
    );
  }

  const hasErrors = account.errors && account.errors.length > 0;
  const balance = calculateAccountBalance(account);
  const pnl = account.realized_pnl ?? 0;
  const isPositive = pnl >= 0;

  return (
    <div className={cn(
      "editorial-panel noise p-6 transition-colors",
      hasErrors && "border-red-500/20"
    )}>
      <div className={cn(
        "pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full blur-3xl",
        isPositive ? "bg-emerald-500/10" : "bg-red-500/10"
      )} />

      <div className="relative">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <Wallet className="h-3.5 w-3.5 text-primary" />
              <span className="editorial-kicker">
                Account Ledger
              </span>
            </div>
            <h2 className="editorial-title text-[28px] leading-none text-foreground sm:text-[36px]">
              Account balance
            </h2>
            <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground/65">
              Live wallet cash, marked portfolio value, and realized performance from connected Polymarket account.
            </p>
            <div className="mt-4 text-[36px] font-mono font-medium leading-none tracking-tight text-foreground">
              <span className="mr-0.5 align-super text-xl text-muted-foreground">$</span>
              {formatNumber(balance.total, 2)}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1">
            <span className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-mono font-medium border",
              isPositive
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border-red-500/20"
            )}>
              {isPositive
                ? <TrendingUp className="h-3 w-3" />
                : <TrendingDown className="h-3 w-3" />
              }
              {isPositive ? "+" : ""}{formatNumber(pnl, 2)}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground/60">Realized PnL</span>
          </div>
        </div>

        <div className="mt-5 flex gap-0 border-t editorial-divider pt-4">
          {[
            { label: "Cash", value: `$${formatNumber(balance.cash, 2)}` },
            { label: "Portfolio", value: `$${formatNumber(balance.portfolio, 2)}` },
          ].map((stat, i) => (
            <div key={i} className={cn(
              "flex flex-col gap-0.5 flex-1",
              i > 0 && "ml-5 border-l editorial-divider pl-5"
            )}>
              <span className="editorial-kicker">
                {stat.label}
              </span>
              <span className="font-mono text-[15px] font-medium text-foreground">
                {stat.value}
              </span>
            </div>
          ))}
        </div>

        {hasErrors && (
          <div className="mt-4 flex flex-col gap-2 border-t editorial-divider pt-4">
            {account.errors!.map((error, idx) => (
              <div key={idx} className="flex items-start gap-2.5 rounded-xl border border-red-500/15 bg-red-500/8 px-3 py-2.5">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-red-400" />
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-red-300">{error.source}</span>
                  <span className="text-xs text-red-400/80">{error.message}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
