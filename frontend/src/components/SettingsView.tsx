import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, FlaskConical, Zap, Plus, Trash2, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { getTrackedWalletBalancesKey } from "@/lib/trackedWalletBalances";
import { cn } from "@/lib/utils";
import { api } from "@/lib/utils2";
import type { Config, CopyWalletConfig, Runtime, TrackedWalletBalance } from "@/types";

interface SettingsViewProps {
  config: Config;
  savedTrackedWalletBalancesKey: string;
  runtime: Runtime;
  setConfig: React.Dispatch<React.SetStateAction<Config>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function SettingsView({ config, savedTrackedWalletBalancesKey, runtime, setConfig, onSubmit }: SettingsViewProps) {
  const copyWallets = config.copy_wallets || [];
  const [walletBalances, setWalletBalances] = useState<TrackedWalletBalance[]>([]);
  const [loadingBalances, setLoadingBalances] = useState(false);

  useEffect(() => {
    if (savedTrackedWalletBalancesKey !== getTrackedWalletBalancesKey(copyWallets)) {
      setLoadingBalances(false);
      return;
    }
    if (!savedTrackedWalletBalancesKey) {
      setWalletBalances([]);
      return;
    }
    setLoadingBalances(true);
    api<TrackedWalletBalance[]>("/api/tracked-wallet-balances")
      .then(setWalletBalances)
      .catch(() => setWalletBalances([]))
      .finally(() => setLoadingBalances(false));
  }, [copyWallets, savedTrackedWalletBalancesKey]);

  function getBalanceForWallet(address: string): TrackedWalletBalance | undefined {
    return walletBalances.find(w => w.address === address);
  }

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
  const enabledCount = copyWallets.filter((wallet) => wallet.enabled).length;
  const fixedCount = copyWallets.filter((wallet) => wallet.sizing_mode === "fixed").length;
  const trackedBalanceTotal = walletBalances.reduce((sum, wallet) => sum + Number(wallet.total || 0), 0);

  return (
    <form className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]" onSubmit={onSubmit}>
      <div className="editorial-panel">
        <div className="relative border-b editorial-divider px-5 py-5">
          <div className="editorial-kicker">Copy Wallet Sources</div>
          <h2 className="editorial-title mt-2 text-2xl text-foreground">Leader routing and execution rules.</h2>
          <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground/70">
            Maintain source wallets, sizing instructions, and mode gates for copied flow from Polymarket.
          </p>
        </div>
        <div className="relative space-y-6 p-5">
          <div className="space-y-4">
            {copyWallets.map((wallet, index) => (
              <div key={index} className="editorial-subpanel space-y-4 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="editorial-kicker">Source {index + 1}</div>
                    <Label className="mt-1 block text-sm font-semibold text-foreground">Tracked leader wallet</Label>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeWallet(index)}
                    className="h-7 w-7 rounded-full p-0 text-muted-foreground hover:bg-white/5 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label className="text-xs text-muted-foreground/60">Wallet Address</Label>
                    <Input
                      value={wallet.address}
                      onChange={(e) => updateWallet(index, "address", e.target.value)}
                      placeholder="0x..."
                      className="border-white/10 bg-black/20 font-mono text-xs"
                    />
                  </div>
                  <div className="editorial-subpanel flex items-center justify-between px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={wallet.enabled}
                        onCheckedChange={(checked) => updateWallet(index, "enabled", checked)}
                      />
                      <Label className="text-xs text-muted-foreground/70">Active for mirroring</Label>
                    </div>
                    {wallet.address && getBalanceForWallet(wallet.address) && (
                      <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground/80">
                        <Wallet className="h-3 w-3" />
                        {loadingBalances ? (
                          <span className="animate-pulse">Loading...</span>
                        ) : (
                          <span>${getBalanceForWallet(wallet.address)?.total?.toFixed(2) || "0.00"}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground/60">Sizing Rule</Label>
                    <select
                      value={wallet.sizing_mode}
                      onChange={(e) => updateWallet(index, "sizing_mode", e.target.value)}
                      className="w-full rounded-md border border-white/10 bg-black/20 px-3 py-2 text-xs"
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
                        className="border-white/10 bg-black/20 font-mono text-xs"
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" onClick={addWallet} className="w-full border-white/10 bg-white/[0.03] hover:bg-white/8">
              <Plus className="h-4 w-4 mr-2" />
              Add Source Wallet
            </Button>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="editorial-panel p-5">
          <div className="relative space-y-5">
            <div>
              <div className="editorial-kicker">Source Desk</div>
              <h3 className="editorial-title mt-2 text-xl text-foreground">Wallets stay primary.</h3>
              <p className="mt-1.5 text-sm text-muted-foreground/70">
                Use this pane to review how many leaders feed copy flow and whether sizing leans fixed or leader-relative.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <SummaryTile label="Tracked Wallets" value={String(copyWallets.length)} detail={`${enabledCount} enabled`} />
              <SummaryTile label="Sizing Split" value={`${fixedCount}/${copyWallets.length || 0}`} detail="fixed vs total" />
              <SummaryTile
                label="Leader Equity"
                value={loadingBalances ? "..." : `$${trackedBalanceTotal.toFixed(2)}`}
                detail={walletBalances.length ? "aggregate tracked balance" : "waiting for tracked balances"}
              />
            </div>

            <div>
              <Label className="text-xs font-semibold text-muted-foreground/80">Poll Interval (seconds)</Label>
              <Input
                type="number"
                min="1"
                max="300"
                value={config.poll_interval_seconds}
                onChange={(e) => setNumber("poll_interval_seconds", e.target.value)}
                className="mt-2 border-white/10 bg-black/20 font-mono"
              />
            </div>
          </div>
        </div>

        <div className={cn(
            "editorial-panel p-5",
            liveRequested
              ? liveBlocked
                ? "border-red-500/25 bg-red-500/10"
                : "border-emerald-500/25 bg-emerald-500/10"
              : "border-amber-500/25 bg-amber-500/10"
          )}>
            <div className="relative mb-4 flex items-center justify-between gap-4">
              <div>
                <div className="editorial-kicker">Execution Gate</div>
                <Label className="mt-1.5 block text-sm font-semibold text-foreground">Trading Mode</Label>
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
            <Button
              className="relative mt-5 w-full bg-primary font-semibold shadow-[0_0_20px_rgba(249,115,22,0.25)] hover:shadow-[0_0_28px_rgba(249,115,22,0.35)]"
              type="submit"
            >
              {liveRequested ? "Save Live Request" : "Save Paper Mode"}
            </Button>
          </div>
      </div>
    </form>
  );
}

function SummaryTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="editorial-subpanel px-4 py-3">
      <div className="editorial-kicker">{label}</div>
      <div className="mt-2 font-mono text-lg text-foreground">{value}</div>
      <p className="mt-1 text-xs text-muted-foreground/60">{detail}</p>
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
        "rounded-2xl border p-3 text-left transition-colors",
        active ? tones[tone] : "border-white/8 bg-white/[0.03] opacity-70 hover:opacity-90"
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
