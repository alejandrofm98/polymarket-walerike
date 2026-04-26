import React, { memo } from "react";
import { Activity, AlertTriangle, FlaskConical, TrendingDown, TrendingUp, Wallet, Wifi, WifiOff, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { PulsingDot } from "@/components/shared";
import type { Runtime } from "@/types";

interface SidebarProps {
  runtime: Runtime;
  socketOnline: boolean;
  open: number;
  closed: number;
  pnl: number;
}

export const Sidebar = memo(function Sidebar({ runtime, socketOnline, open, closed, pnl }: SidebarProps) {
  const isRunning = runtime.running && !runtime.paused;
  const isPaper = runtime.paper_mode !== false;
  const liveBlocked = runtime.live_blocked === true;
  const modeLabel = liveBlocked ? "Live blocked" : isPaper ? "Paper simulation" : "Live trading";
  const modeDetail = liveBlocked
    ? runtime.live_block_reason || "Live requirements missing"
    : isPaper
      ? "Orders are simulated"
      : "Real CLOB orders enabled";
  const ModeIcon = liveBlocked ? AlertTriangle : isPaper ? FlaskConical : Zap;

  return (
    <aside className="space-y-3">
      {/* Status card */}
      <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 backdrop-blur">
        <div className="mb-4 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
            <Activity className="h-3 w-3" />
            Status
          </span>
          <div className="flex items-center gap-1.5">
            <PulsingDot color={isRunning ? "green" : "gray"} />
            <span className={cn("text-xs font-semibold", isRunning ? "text-emerald-400" : "text-muted-foreground")}>
              {runtime.status || "stopped"}
            </span>
          </div>
        </div>

        <div className="space-y-3">
          {/* Mode pill */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground/70">Mode</span>
            <span className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide",
              liveBlocked
                ? "bg-red-500/15 text-red-300"
                : isPaper
                ? "bg-amber-500/15 text-amber-400"
                : "bg-emerald-500/15 text-emerald-300"
            )}>
              <ModeIcon className="h-3 w-3" />
              {modeLabel}
            </span>
          </div>

          <div className={cn(
            "rounded-lg border px-3 py-2 text-xs",
            liveBlocked
              ? "border-red-500/20 bg-red-500/10 text-red-200"
              : isPaper
                ? "border-amber-500/20 bg-amber-500/10 text-amber-200"
                : "border-emerald-500/20 bg-emerald-500/10 text-emerald-200"
          )}>
            {modeDetail}
          </div>

          {/* Socket */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground/70">WebSocket</span>
            <div className={cn(
              "flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
              socketOnline
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-white/5 text-muted-foreground"
            )}>
              {socketOnline ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {socketOnline ? "Online" : "Offline"}
            </div>
          </div>
        </div>
      </div>

      {/* Account card */}
      <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 backdrop-blur">
        <div className="mb-4 flex items-center gap-1.5">
          <Wallet className="h-3 w-3 text-muted-foreground/60" />
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">Account</span>
        </div>

        {/* PnL big */}
        <div className="mb-4 rounded-lg bg-white/[0.03] px-4 py-3 text-center">
          <div className="mb-0.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50">
            Total PnL
          </div>
          <div className={cn("flex items-center justify-center gap-1 text-3xl font-bold tracking-tight", pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
            {pnl >= 0 ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
            {pnl >= 0 ? "+" : ""}${Math.abs(pnl).toFixed(2)}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <StatTile label="Open" value={String(open)} valueClass="text-sky-400" />
          <StatTile label="Closed" value={String(closed)} valueClass="text-muted-foreground" />
        </div>
      </div>
    </aside>
  );
});

function StatTile({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-3 py-2.5 text-center">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">{label}</div>
      <div className={cn("mt-0.5 text-lg font-bold", valueClass)}>{value}</div>
    </div>
  );
}
