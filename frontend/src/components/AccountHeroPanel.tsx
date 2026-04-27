import { Wallet, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/utils2";
import type { AccountSummary } from "@/types";

interface AccountHeroPanelProps {
  account: AccountSummary | null;
  loading: boolean;
}

export function AccountHeroPanel({ account, loading }: AccountHeroPanelProps) {
  if (!account) {
    return (
      <div className="flex items-center justify-center h-24 rounded-xl border border-white/8 bg-white/[0.02] text-sm text-muted-foreground">
        {loading ? "Loading account..." : "No account data"}
      </div>
    );
  }

  const hasErrors = account.errors && account.errors.length > 0;

  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border bg-white/[0.02] p-6 backdrop-blur transition-colors",
      hasErrors ? "border-red-500/20" : "border-white/8"
    )}>
      {/* Background glow based on PnL or Errors - assuming PnL > 0 for now */}
      <div className="absolute top-0 right-0 -mr-16 -mt-16 h-32 w-32 rounded-full bg-emerald-500/10 blur-3xl"></div>

      <div className="relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-1">
            <Wallet className="h-4 w-4" />
            <span>Balance Disponible</span>
          </div>
          <div className="text-4xl font-extrabold tracking-tight text-foreground">
            ${formatNumber(account.available || 0, 2)}
          </div>
        </div>

        {hasErrors && (
          <div className="flex items-start gap-2 max-w-sm rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="flex flex-col">
              <span className="font-semibold">{account.errors[0].source}</span>
              <span>{account.errors[0].message}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
