import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { Config } from "@/types";

const assets = ["BTC", "ETH", "SOL"];
const timeframes = ["5m", "15m", "1h"];

interface SettingsViewProps {
  config: Config;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onEnabledMarketChange: (asset: string, timeframe: string, checked: boolean) => void;
}

export function SettingsView({ config, setConfig, onSubmit, onEnabledMarketChange }: SettingsViewProps) {
  function setNumber(key: keyof Config, value: string) {
    setConfig((current) => ({ ...current, [key]: Number(value) }));
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
            <SettingField label="Shares per order">
              <Input
                type="number"
                min="1"
                step="1"
                value={config.shares_per_order}
                onChange={(e) => setNumber("shares_per_order", e.target.value)}
                className="border-white/10 bg-white/[0.03] font-mono"
              />
            </SettingField>

            {/* Paper mode */}
            <div className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.02] p-4 sm:col-span-2">
              <div>
                <Label className="text-sm font-semibold text-foreground">Paper mode</Label>
                <p className="mt-0.5 text-xs text-muted-foreground/60">Live trading remains backend-gated.</p>
              </div>
              <div className="flex items-center gap-3">
                <span className={cn("text-xs font-semibold", config.paper_mode !== false ? "text-amber-400" : "text-muted-foreground/50")}>
                  {config.paper_mode !== false ? "Paper" : "Live"}
                </span>
                <Switch
                  checked={config.paper_mode !== false}
                  onCheckedChange={(checked) => setConfig((current) => ({ ...current, paper_mode: checked }))}
                />
              </div>
            </div>

            </div>

            <Button
              className="sm:col-span-2 bg-primary font-semibold shadow-[0_0_20px_rgba(249,115,22,0.25)] hover:shadow-[0_0_28px_rgba(249,115,22,0.35)]"
              type="submit"
            >
              Save Settings
            </Button>
          </div>
        </div>
      </div>

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
    </form>
  );
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
