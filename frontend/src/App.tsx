import { FormEvent, useEffect, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { AccountView } from "@/components/AccountView";
import { AccountHeroPanel } from "@/components/AccountHeroPanel";
import { CopyOverview } from "@/components/overview/CopyOverview";
import { SettingsView } from "@/components/SettingsView";
import {
  getCopyOverviewPollMs,
  getHeaderMetrics,
  getOverviewRuntime,
  shouldRefreshCopyOverview,
} from "@/lib/copyOverviewState";
import { api } from "@/lib/utils2";
import { shouldShowRealtimeLog } from "@/lib/logFiltering";
import { formatLogEntry } from "@/lib/logEntry";
import { getTrackedWalletBalancesKey } from "@/lib/trackedWalletBalances";
import type {
  View,
  Runtime,
  Config,
  AccountSummary,
  CopyOverviewPayload,
  WsEvent,
} from "@/types";

const emptyConfig: Config = {
  copy_wallets: [],
  poll_interval_seconds: 5,
  solo_log: false,
};

function App() {
  const [activeView, setActiveView] = useState<View>("overview");
  const [runtime, setRuntime] = useState<Runtime>({ status: "stopped", running: false, paused: false });
  const [socketOnline, setSocketOnline] = useState(false);
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [copyOverview, setCopyOverview] = useState<CopyOverviewPayload | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [savedTrackedWalletBalancesKey, setSavedTrackedWalletBalancesKey] = useState("");
  const [loadingAccount, setLoadingAccount] = useState(false);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [busyControl, setBusyControl] = useState(false);
  const reconnectMs = useRef(500);
  const configRef = useRef<Config>(emptyConfig);
  const refreshingCopyOverview = useRef(false);
  const queuedCopyOverviewRefresh = useRef(false);

  const headerMetrics = getHeaderMetrics(copyOverview);

  function log(message: string) {
    setLogs((current) => [formatLogEntry(message), ...current].slice(0, 80));
  }

  async function refreshStatus() {
    const data = await api<{ runtime: Runtime }>("/api/status");
    setRuntime(data.runtime || {});
  }

  async function refreshConfig() {
    const data = await api<Config>("/api/config");
    const nextConfig = { ...emptyConfig, ...data };
    setConfig(nextConfig);
    setSavedTrackedWalletBalancesKey(getTrackedWalletBalancesKey(nextConfig.copy_wallets));
  }

  async function refreshAccount() {
    setLoadingAccount(true);
    try {
      setAccount(await api<AccountSummary>("/api/account"));
    } catch (error) {
      log(`account: ${(error as Error).message}`);
    } finally {
      setLoadingAccount(false);
    }
  }

  async function refreshCopyOverview(options?: { silent?: boolean }) {
    if (!options?.silent) setLoadingOverview(true);
    try {
      const data = await api<CopyOverviewPayload>("/api/copy-overview");
      const nextRuntime = getOverviewRuntime(data);
      if (nextRuntime) setRuntime(nextRuntime);
      setCopyOverview(data);
    } catch (error) {
      log(`copy overview: ${(error as Error).message}`);
    } finally {
      if (!options?.silent) setLoadingOverview(false);
    }
  }

  function requestCopyOverviewRefresh() {
    if (refreshingCopyOverview.current) {
      queuedCopyOverviewRefresh.current = true;
      return;
    }
    refreshingCopyOverview.current = true;
    refreshCopyOverview({ silent: true })
      .finally(() => {
        refreshingCopyOverview.current = false;
        if (!queuedCopyOverviewRefresh.current) return;
        queuedCopyOverviewRefresh.current = false;
        requestCopyOverviewRefresh();
      });
  }

  async function controlBot() {
    const action = runtime.running && !runtime.paused ? "pause" : "start";
    setBusyControl(true);
    try {
      const data = await api<{ runtime: Runtime }>(`/api/bot/${action}`, { method: "POST" });
      setRuntime(data.runtime || {});
      log(`control ${action}`);
    } catch (error) {
      log((error as Error).message);
    } finally {
      setBusyControl(false);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const saved = await api<Config>("/api/config", { method: "PUT", body: JSON.stringify(config) });
      const nextConfig = { ...emptyConfig, ...saved };
      setConfig(nextConfig);
      setSavedTrackedWalletBalancesKey(getTrackedWalletBalancesKey(nextConfig.copy_wallets));
      log("settings saved");
      await Promise.allSettled([refreshStatus(), refreshCopyOverview()]);
    } catch (error) {
      log((error as Error).message);
    }
  }

  useEffect(() => {
    configRef.current = config;
  }, [config]);

  useEffect(() => {
    Promise.allSettled([
      refreshStatus(),
      refreshConfig(),
      refreshAccount(),
      refreshCopyOverview(),
    ]).then((results) => {
      for (const result of results) {
        if (result.status === "rejected") log((result.reason as Error).message);
      }
    });
  }, []);

  useEffect(() => {
    if (activeView === "account" && account === null && !loadingAccount) {
      refreshAccount();
    }
  }, [activeView, account, loadingAccount]);

  useEffect(() => {
    const pollMs = getCopyOverviewPollMs(socketOnline);
    if (pollMs === null) return;

    const pollTimer = window.setInterval(() => {
      requestCopyOverviewRefresh();
    }, pollMs);

    return () => window.clearInterval(pollTimer);
  }, [socketOnline]);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
      ws.onopen = () => {
        setSocketOnline(true);
        reconnectMs.current = 500;
        log("ws connected");
        requestCopyOverviewRefresh();
      };
      ws.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as WsEvent;
          if (event.type === "log") {
            const msg = String(event.payload.message);
            if (shouldShowRealtimeLog(msg, configRef.current)) {
              log(msg);
            }
          }
          if (event.type === "bot_status") setRuntime(event.payload || {});
          if (shouldRefreshCopyOverview(event)) {
            requestCopyOverviewRefresh();
          }
          if (event.type === "market_resolved" || event.type === "trade_resolved") {
            Promise.allSettled([refreshStatus(), refreshAccount()]);
          }
        } catch (error) {
          log(`ws parse: ${(error as Error).message}`);
        }
      };
      ws.onclose = () => {
        setSocketOnline(false);
        if (closed) return;
        reconnectTimer = window.setTimeout(connect, reconnectMs.current);
        reconnectMs.current = Math.min(reconnectMs.current * 2, 10000);
      };
      ws.onerror = () => log("ws error");
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_rgba(249,115,22,0.07)_0%,_transparent_55%),radial-gradient(ellipse_at_bottom-right,_rgba(96,165,250,0.05)_0%,_transparent_50%),linear-gradient(180deg,_#080b11_0%,_#060910_100%)]">
      <Header
        activeView={activeView}
        onViewChange={setActiveView}
        runtime={runtime}
        socketOnline={socketOnline}
        busyControl={busyControl}
        onControlBot={controlBot}
        onExport={() => (window.location.href = "/api/trades/export.csv")}
        totalPnl={headerMetrics.totalPnl}
        openPositions={headerMetrics.openPositions}
        trackedWallets={headerMetrics.trackedWallets}
      />

      <main className="p-4 lg:p-6">
        <section className="min-w-0 space-y-4">
          {activeView === "overview" && (
            <CopyOverview
              overview={copyOverview}
              loading={loadingOverview}
              logs={logs}
              onClearLogs={() => setLogs([])}
            />
          )}
          {activeView === "account" && (
            <>
              <AccountHeroPanel account={account} loading={loadingAccount} />
              <AccountView account={account} loading={loadingAccount} onRefresh={refreshAccount} />
            </>
          )}
          {activeView === "settings" && (
            <SettingsView
              config={config}
              savedTrackedWalletBalancesKey={savedTrackedWalletBalancesKey}
              runtime={runtime}
              setConfig={setConfig}
              onSubmit={saveSettings}
            />
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
