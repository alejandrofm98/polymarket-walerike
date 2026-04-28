import { FormEvent } from "react";
import { AlertTriangle, FlaskConical, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { Config, Runtime } from "@/types";

const assets = ["BTC", "ETH", "SOL"];
const timeframes = ["5m", "15m", "1h"];
const strategyLabels: Record<string, { title: string; description: string; risk: string }> = {
  fee_aware_pair_arbitrage: {
    title: "Fee-aware pair arbitrage",
    description: "Buys UP + DOWN only when fee-adjusted pair cost stays cheap.",
    risk: "Conservative",
  },
  late_window_discount_hedge: {
    title: "Late-window discount hedge",
    description: "Near expiry pair entry when one side is temporarily discounted.",
    risk: "Conservative",
  },
  high_confidence_near_expiry_side: {
    title: "High-confidence near-expiry side",
    description: "Directional UP/DOWN entry only when spot is far from target near close.",
    risk: "Strict directional",
  },
};

interface SettingsViewProps {
  config: Config;
  runtime: Runtime;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onEnabledMarketChange: (asset: string, timeframe: string, checked: boolean) => void;
}

export function SettingsView({ config, runtime, setConfig, onSubmit, onEnabledMarketChange }: SettingsViewProps) {
  function setNumber(key: keyof Config, value: string) {
    setConfig((current) => ({ ...current, [key]: Number(value) }));
  }

  const liveRequested = config.paper_mode === false;
  const liveBlocked = runtime.live_blocked === true || (liveRequested && runtime.live_trading === false);
  const strategyGroups = config.strategy_groups || {};
  const strategies = config.strategies || {};

  function setStrategyGroupEnabled(groupName: string, enabled: boolean) {
    setConfig((current) => ({
      ...current,
      strategy_groups: {
        ...current.strategy_groups,
        [groupName]: { ...current.strategy_groups[groupName], enabled },
      },
    }));
  }

  function setStrategyEnabled(strategyName: string, enabled: boolean) {
    setConfig((current) => ({
      ...current,
      strategies: {
        ...current.strategies,
        [strategyName]: { ...current.strategies[strategyName], enabled },
      },
    }));
  }

  return (
    <form className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]" onSubmit={onSubmit}>
      {/* Bot Settings */}
      <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
        <div className="border-b border-white/5 px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">Bot Settings</h2>
          <p className="mt-0.5 text-xs text-muted-foreground/60">Runtime controls persisted through backend config.</p>
        </div>
        <div className="p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <SettingField label="Capital per trade" hint="USDC">
              <Input
                type="number"
                min="1"
                step="1"
                value={config.capital_per_trade}
                onChange={(e) => setNumber("capital_per_trade", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>
            <SettingField label="Arb threshold" hint="0 – 1">
              <Input
                type="number"
                min="0"
                max="1"
                step="0.001"
                value={config.min_margin_for_arbitrage}
                onChange={(e) => setNumber("min_margin_for_arbitrage", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>
            <SettingField label="Entry threshold" hint="0.01 – 0.99">
              <Input
                type="number"
                min="0.01"
                max="0.99"
                step="0.001"
                value={config.entry_threshold}
                onChange={(e) => setNumber("entry_threshold", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>
            <SettingField label="Max sum avg" hint="0 – 1">
              <Input
                type="number"
                min="0.01"
                max="1"
                step="0.001"
                value={config.max_sum_avg}
                onChange={(e) => setNumber("max_sum_avg", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>
            <SettingField label="Max buys per side">
              <Input
                type="number"
                min="1"
                step="1"
                value={config.max_buys_per_side}
                onChange={(e) => setNumber("max_buys_per_side", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>
            {/* Trading mode */}
            <div className={cn(
              "rounded-xl border p-4 sm:col-span-2",
              liveRequested
                ? liveBlocked
                  ? "border-red-500/25 bg-red-500/10"
                  : "border-emerald-500/25 bg-emerald-500/10"
                : "border-amber-500/25 bg-amber-500/10"
            )}>
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <Label className="text-sm font-semibold text-foreground">Trading Mode</Label>
                  <p className="mt-0.5 text-xs text-muted-foreground/60">Paper simulates orders. Live requires backend env gate.</p>
                </div>
                <Switch
                  checked={!liveRequested}
                  onCheckedChange={(checked) => setConfig((current) => ({ ...current, paper_mode: checked }))}
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <ModeOption
                  active={!liveRequested}
                  tone="paper"
                  icon={<FlaskConical className="h-4 w-4" />}
                  title="Paper"
                  description="Orders stay simulated"
                  onClick={() => setConfig((current) => ({ ...current, paper_mode: true }))}
                />
                <ModeOption
                  active={liveRequested}
                  tone={liveBlocked ? "blocked" : "live"}
                  icon={liveBlocked ? <AlertTriangle className="h-4 w-4" /> : <Zap className="h-4 w-4" />}
                  title={liveBlocked ? "Live blocked" : "Live"}
                  description={liveBlocked ? runtime.live_block_reason || "Live requirements missing" : "Real orders enabled"}
                  onClick={() => setConfig((current) => ({ ...current, paper_mode: false }))}
                />
              </div>
            </div>

            <Button
              className="sm:col-span-2 bg-primary font-semibold shadow-[0_0_20px_rgba(249,115,22,0.25)] hover:shadow-[0_0_28px_rgba(249,115,22,0.35)]"
              type="submit"
            >
              {liveRequested ? "Save Live Request" : "Save Paper Mode"}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4">
        {/* Markets Matrix */}
        <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
        <div className="border-b border-white/5 px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">Markets Matrix</h2>
          <p className="mt-0.5 text-xs text-muted-foreground/60">Select asset / timeframe pairs to scan.</p>
        </div>
        <div className="p-5">
          <div className="market-grid text-sm">
            <div />
            {timeframes.map((tf) => (
              <div key={tf} className="text-center text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">
                {tf}
              </div>
            ))}
            {assets.map((asset) => [
              <div key={`${asset}-label`} className="flex items-center">
                <AssetLabel asset={asset} />
              </div>,
              ...timeframes.map((tf) => (
                <label
                  key={`${asset}-${tf}`}
                  className="group flex cursor-pointer justify-center rounded-lg border border-white/8 bg-white/[0.02] p-3 transition-colors hover:border-primary/40 hover:bg-primary/5"
                >
                  <input
                    type="checkbox"
                    className="accent-primary h-4 w-4 cursor-pointer rounded"
                    checked={(config.enabled_markets[asset] || []).includes(tf)}
                    onChange={(e) => onEnabledMarketChange(asset, tf, e.target.checked)}
                  />
                </label>
              )),
            ])}
          </div>
        </div>
      </div>

        {/* Strategy Groups */}
        <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
          <div className="border-b border-white/5 px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Strategy Groups</h2>
            <p className="mt-0.5 text-xs text-muted-foreground/60">Enable groups or individual BTC 5m strategies.</p>
          </div>
          <div className="space-y-4 p-5">
            {Object.entries(strategyGroups).map(([groupName, group]) => (
              <div key={groupName} className="rounded-xl border border-white/8 bg-black/20 p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-bold uppercase tracking-widest text-foreground">{humanize(groupName)}</div>
                    <p className="mt-1 text-[11px] text-muted-foreground/60">
                      Max {group.max_orders_per_tick} orders/tick · {Math.round(group.capital_fraction * 100)}% capital
                    </p>
                  </div>
                  <Switch checked={group.enabled} onCheckedChange={(checked) => setStrategyGroupEnabled(groupName, checked)} />
                </div>

                <div className="space-y-2">
                  {Object.entries(strategies)
                    .filter(([, strategy]) => strategy.group === groupName)
                    .map(([strategyName, strategy]) => {
                      const label = strategyLabels[strategyName] || { title: humanize(strategyName), description: "Runtime strategy", risk: "Custom" };
                      return (
                        <div key={strategyName} className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-xs font-semibold text-foreground">{label.title}</div>
                              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/60">{label.description}</p>
                              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/50">
                                <span className="rounded-full border border-white/8 px-2 py-0.5">{label.risk}</span>
                                <span className="rounded-full border border-white/8 px-2 py-0.5">{strategy.assets.join(",")}</span>
                                <span className="rounded-full border border-white/8 px-2 py-0.5">{strategy.timeframes.join(",")}</span>
                              </div>
                            </div>
                            <Switch checked={strategy.enabled} onCheckedChange={(checked) => setStrategyEnabled(strategyName, checked)} />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </form>
  );
}

function humanize(value: string) {
  return value.replace(/_/g, " ");
}

function SettingField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-semibold text-muted-foreground/80">{label}</Label>
        {hint && <span className="text-[10px] text-muted-foreground/40">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function ModeOption({
  active,
  tone,
  icon,
  title,
  description,
  onClick,
}: {
  active: boolean;
  tone: "paper" | "live" | "blocked";
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}) {
  const toneClass = {
    paper: active ? "border-amber-500/40 bg-amber-500/10 text-amber-200" : "border-white/8 bg-white/[0.02] text-muted-foreground",
    live: active ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200" : "border-white/8 bg-white/[0.02] text-muted-foreground",
    blocked: active ? "border-red-500/40 bg-red-500/10 text-red-200" : "border-white/8 bg-white/[0.02] text-muted-foreground",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("rounded-xl border p-3 text-left transition-all hover:border-primary/40", toneClass[tone])}
    >
      <div className="mb-2 flex items-center gap-2 text-sm font-bold uppercase tracking-wide">
        {icon}
        {title}
      </div>
      <p className="text-xs opacity-75">{description}</p>
    </button>
  );
}

function AssetLabel({ asset }: { asset: string }) {
  const map: Record<string, string> = {
    BTC: "text-amber-400",
    ETH: "text-indigo-400",
    SOL: "text-emerald-400",
  };
  return (
    <span className={cn("text-xs font-bold uppercase tracking-wide", map[asset] || "text-foreground")}>
      {asset}
    </span>
  );
}
