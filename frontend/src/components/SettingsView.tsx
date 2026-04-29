import { FormEvent } from "react";
import { AlertTriangle, FlaskConical, Zap, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { Config, CopyWalletConfig, Runtime } from "@/types";

interface SettingsViewProps {
  config: Config;
  runtime: Runtime;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function SettingsView({ config, runtime, setConfig, onSubmit }: SettingsViewProps) {
  const copyWallets = config.copy_wallets || [];

  function addWallet() {
    setConfig((current) => ({
      ...current,
      copy_wallets: [
        ...(current.copy_wallets || []),
        { address: "", enabled: true, sizing_mode: "leader_percent", fixed_amount: 10 },
      ],
    }));
  }

  function updateWallet(index: number, field: keyof CopyWalletConfig, value: string | boolean | number) {
    setConfig((current) => {
      const wallets = [...(current.copy_wallets || [])];
      wallets[index] = { ...wallets[index], [field]: value };
      return { ...current, copy_wallets: wallets };
    });
  }

  function removeWallet(index: number) {
    setConfig((current) => ({
      ...current,
      copy_wallets: (current.copy_wallets || []).filter((_, i) => i !== index),
    }));
  }

  function setNumber(key: keyof Config, value: string) {
    setConfig((current) => ({ ...current, [key]: Number(value) }));
  }

  const liveRequested = config.paper_mode === false;
  const liveBlocked = runtime.live_blocked === true || (liveRequested && runtime.live_trading === false);

  return (
    <form className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]" onSubmit={onSubmit}>
      <div className="rounded-xl border border-white/8 bg-white/[0.02] backdrop-blur">
        <div className="border-b border-white/5 px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">Copy Trading Settings</h2>
          <p className="mt-0.5 text-xs text-muted-foreground/60">Configure wallets to copy from Polymarket.</p>
        </div>
        <div className="p-5 space-y-6">
          <div className="space-y-4">
            {copyWallets.map((wallet, index) => (
              <div key={index} className="rounded-lg border border-white/8 bg-white/[0.02] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-semibold text-muted-foreground/80">Wallet {index + 1}</Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeWallet(index)}
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label className="text-xs text-muted-foreground/60">Address</Label>
                    <Input
                      value={wallet.address}
                      onChange={(e) => updateWallet(index, "address", e.target.value)}
                      placeholder="0x..."
                      className="border-white/10 bg-white/[0.03] font-mono text-xs"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={wallet.enabled}
                      onCheckedChange={(checked) => updateWallet(index, "enabled", checked)}
                    />
                    <Label className="text-xs text-muted-foreground/60">Enabled</Label>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground/60">Sizing Mode</Label>
                    <select
                      value={wallet.sizing_mode}
                      onChange={(e) => updateWallet(index, "sizing_mode", e.target.value)}
                      className="w-full rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-xs"
                    >
                      <option value="leader_percent">Leader %</option>
                      <option value="fixed">Fixed Amount</option>
                    </select>
                  </div>
                  {wallet.sizing_mode === "fixed" && (
                    <div>
                      <Label className="text-xs text-muted-foreground/60">Fixed Amount (USDC)</Label>
                      <Input
                        type="number"
                        min="1"
                        value={wallet.fixed_amount}
                        onChange={(e) => updateWallet(index, "fixed_amount", Number(e.target.value))}
                        className="border-white/10 bg-white/[0.03] font-mono text-xs"
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" onClick={addWallet} className="w-full">
              <Plus className="h-4 w-4 mr-2" />
              Add Wallet
            </Button>
          </div>
          <div>
            <Label className="text-xs font-semibold text-muted-foreground/80">Poll Interval (seconds)</Label>
            <Input
              type="number"
              min="1"
              max="300"
              value={config.poll_interval_seconds}
              onChange={(e) => setNumber("poll_interval_seconds", e.target.value)}
              className="border-white/10 bg-white/[0.03] font-mono"
            />
          </div>
          <div className={cn(
            "rounded-xl border p-4",
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
            className="w-full bg-primary font-semibold shadow-[0_0_20px_rgba(249,115,22,0.25)] hover:shadow-[0_0_28px_rgba(249,115,22,0.35)]"
            type="submit"
          >
            {liveRequested ? "Save Live Request" : "Save Paper Mode"}
          </Button>
        </div>
      </div>
    </form>
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
  const tones = {
    paper: "border-amber-500/25 bg-amber-500/10 hover:border-amber-500/50",
    live: "border-emerald-500/25 bg-emerald-500/10 hover:border-emerald-500/50",
    blocked: "border-red-500/25 bg-red-500/10 hover:border-red-500/50",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border p-3 text-left transition-colors",
        active ? tones[tone] : "border-white/8 bg-white/[0.02] opacity-60 hover:opacity-80"
      )}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm font-semibold text-foreground">{title}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground/60">{description}</p>
    </button>
  );
}