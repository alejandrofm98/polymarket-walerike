import React, { memo } from "react";
import {
  Activity,
  Bot,
  Download,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { NavTab, PulsingDot } from "@/components/shared";
import type { View, Runtime } from "@/types";

interface HeaderProps {
  activeView: View;
  onViewChange: (view: View) => void;
  runtime: Runtime;
  socketOnline: boolean;
  onExport: () => void;
  totalPnl: number;
  openPositions: number;
  trackedWallets: number;
}

export const Header = memo(function Header({
  activeView,
  onViewChange,
  runtime,
  socketOnline,
  onExport,
  totalPnl,
  openPositions,
  trackedWallets,
}: HeaderProps) {
  const isRunning = runtime.running && !runtime.paused;

  return (
    <header className="sticky top-0 z-30 border-b border-white/8 bg-[#080b11]/90 backdrop-blur-2xl">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4 px-4 py-3 lg:px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-primary/30 bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
            {isRunning && (
              <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
              </span>
            )}
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-foreground">Walerike</h1>
            <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/60">
              Polymarket Hedge Bot
            </p>
          </div>
        </div>

        {/* KPIs */}
        <div className="hidden gap-2 lg:flex">
          <KpiPill
            label="PnL"
            value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`}
            icon={totalPnl >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            valueClass={totalPnl >= 0 ? "text-emerald-400" : "text-red-400"}
          />
          <KpiPill
            label="Open"
            value={String(openPositions)}
            icon={<Activity className="h-3 w-3" />}
            valueClass="text-foreground"
          />
          <KpiPill
            label="Wallets"
            value={String(trackedWallets)}
            icon={<Wallet className="h-3 w-3" />}
            valueClass="text-sky-400"
          />
          <div className="flex items-center gap-1.5 rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1.5">
            <PulsingDot color={socketOnline ? "green" : "gray"} />
            <span className={cn("text-xs font-medium", socketOnline ? "text-emerald-400" : "text-muted-foreground")}>
              {socketOnline ? "Online" : "Offline"}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onExport}
            className="border-white/10 bg-white/[0.03] hover:bg-white/8"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">CSV</span>
          </Button>
        </div>
      </div>

      {/* Nav tabs */}
      <div className="flex items-center gap-1 border-t border-white/5 px-4 lg:px-6">
        <NavTab active={activeView === "overview"} onClick={() => onViewChange("overview")}>
          Overview
        </NavTab>
        <NavTab active={activeView === "account"} onClick={() => onViewChange("account")}>
          Account
        </NavTab>
        <NavTab active={activeView === "settings"} onClick={() => onViewChange("settings")}>
          Settings
        </NavTab>
      </div>
    </header>
  );
});

function KpiPill({
  label,
  value,
  icon,
  valueClass,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1.5">
      <span className="text-muted-foreground/60">{icon}</span>
      <div>
        <div className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/50">{label}</div>
        <div className={cn("text-sm font-bold leading-none", valueClass)}>{value}</div>
      </div>
    </div>
  );
}
