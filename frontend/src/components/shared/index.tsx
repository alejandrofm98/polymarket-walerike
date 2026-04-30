import React from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  children: React.ReactNode;
  icon?: React.ReactNode;
}

export function EmptyState({ children, icon }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
      {icon && <div className="text-muted-foreground/50">{icon}</div>}
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

interface KpiCardProps {
  label: string;
  value: string | React.ReactNode;
  valueClassName?: string;
  sublabel?: string;
  icon?: React.ReactNode;
  glow?: "green" | "red" | "amber" | "blue";
}

export function KpiCard({ label, value, valueClassName, sublabel, icon, glow }: KpiCardProps) {
  const glowMap = {
    green: "shadow-[0_0_24px_rgba(52,211,153,0.12)]",
    red: "shadow-[0_0_24px_rgba(248,113,113,0.12)]",
    amber: "shadow-[0_0_24px_rgba(251,191,36,0.12)]",
    blue: "shadow-[0_0_24px_rgba(96,165,250,0.12)]",
  };
  return (
    <div className={cn("editorial-subpanel relative overflow-hidden p-4", glow && glowMap[glow])}>
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="editorial-kicker mb-2 flex items-center gap-1.5 text-muted-foreground/70">
        {icon}
        {label}
      </div>
      <div className={cn("font-mono text-2xl font-bold tracking-tight text-foreground", valueClassName)}>{value}</div>
      {sublabel && <div className="mt-1 text-xs text-muted-foreground/60">{sublabel}</div>}
    </div>
  );
}

interface NavTabProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active: boolean;
}

export function NavTab({ active, className, children, ...props }: NavTabProps) {
  return (
    <button
      className={cn(
        "relative px-4 py-2 text-sm font-medium transition-all duration-200",
        "text-muted-foreground hover:text-foreground",
        active && "text-foreground",
        className,
      )}
      {...props}
    >
      {children}
      {active && (
        <span className="absolute inset-x-0 -bottom-[1px] h-[2px] rounded-full bg-primary" />
      )}
    </button>
  );
}

interface AssetBadgeProps {
  asset?: string;
  className?: string;
}

export function AssetBadge({ asset, className }: AssetBadgeProps) {
  const map: Record<string, string> = {
    BTC: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    ETH: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
    SOL: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  };
  const key = (asset || "").toUpperCase();
  const style = map[key] || "bg-white/10 text-white/60 border-white/10";
  return (
    <span className={cn("inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold tracking-wide", style, className)}>
      {asset || "—"}
    </span>
  );
}

interface PulsingDotProps {
  color?: "green" | "amber" | "red" | "gray";
}

export function PulsingDot({ color = "green" }: PulsingDotProps) {
  const colorMap = {
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-red-400",
    gray: "bg-slate-500",
  };
  return (
    <span className="relative flex h-2.5 w-2.5">
      {color !== "gray" && (
        <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", colorMap[color])} />
      )}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", colorMap[color])} />
    </span>
  );
}
