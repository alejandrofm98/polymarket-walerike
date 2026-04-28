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
      <div className="flex items-center gap-2.5 h-24 rounded-2xl border border-white/8 bg-white/[0.02] px-5 text-sm text-muted-foreground">
        <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
        {loading ? "Cargando cuenta…" : "Sin datos de cuenta"}
      </div>
    );
  }

  const hasErrors = account.errors && account.errors.length > 0;
  const balance = calculateAccountBalance(account);
  const pnl = account.realized_pnl ?? 0;
  const isPositive = pnl >= 0;

  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border bg-background p-6 transition-colors",
      hasErrors ? "border-red-500/20" : "border-white/8"
    )}>
      {/* Ambient glow */}
      <div className={cn(
        "pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full blur-3xl",
        isPositive ? "bg-emerald-500/10" : "bg-red-500/10"
      )} />

      <div className="relative">
        {/* Header row */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] font-medium tracking-widest uppercase text-muted-foreground">
                Balance disponible
              </span>
            </div>
            <div className="text-[36px] font-mono font-medium tracking-tight leading-none text-foreground">
              <span className="text-xl text-muted-foreground align-super mr-0.5">$</span>
              {formatNumber(balance.total, 2)}
            </div>
          </div>

          {/* PnL badge */}
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
            <span className="text-[11px] text-muted-foreground/60 font-mono">PnL realizado</span>
          </div>
        </div>

        {/* Sub stats */}
        <div className="mt-5 pt-4 border-t border-white/6 flex gap-0">
          {[
            { label: "Efectivo", value: `$${formatNumber(balance.cash, 2)}` },
            { label: "Cartera", value: `$${formatNumber(balance.portfolio, 2)}` },
          ].map((stat, i) => (
            <div key={i} className={cn(
              "flex flex-col gap-0.5 flex-1",
              i > 0 && "border-l border-white/6 pl-5 ml-5"
            )}>
              <span className="text-[10px] font-medium tracking-widest uppercase text-muted-foreground/60">
                {stat.label}
              </span>
              <span className="font-mono text-[15px] font-medium text-foreground">
                {stat.value}
              </span>
            </div>
          ))}
        </div>

        {/* Errors */}
        {hasErrors && (
          <div className="mt-4 pt-4 border-t border-white/6 flex flex-col gap-2">
            {account.errors!.map((error, idx) => (
              <div key={idx} className="flex items-start gap-2.5 rounded-xl border border-red-500/15 bg-red-500/8 px-3 py-2.5">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-red-400" />
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] font-semibold text-red-300">{error.source}</span>
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