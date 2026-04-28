import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { MarketsView } from "@/components/markets/MarketsView";
import { AccountHeroPanel } from "@/components/AccountHeroPanel";
import { SettingsView } from "@/components/SettingsView";
import { api } from "@/lib/utils2";
import { shouldShowRealtimeLog } from "@/lib/logFiltering";
import { mergeMarketTick } from "@/lib/marketMerge";
import type {
  View,
  Runtime,
  Config,
  Market,
  Trade,
  Position,
  AccountSummary,
  WsEvent,
} from "@/types";

const emptyConfig: Config = {
  capital_per_trade: 0,
  min_margin_for_arbitrage: 0,
  entry_threshold: 0,
  max_sum_avg: 0,
  max_buys_per_side: 1,
  paper_mode: true,
  enabled_markets: {},
  strategy_groups: {},
  strategies: {},
};

const MARKET_TICK_THROTTLE_MS = 1000;

function App() {
  const [activeView, setActiveView] = useState<View>("markets");
  const [runtime, setRuntime] = useState<Runtime>({ status: "stopped", running: false, paused: false });
  const [socketOnline, setSocketOnline] = useState(false);
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loadingMarkets, setLoadingMarkets] = useState(false);
  const [loadingAccount, setLoadingAccount] = useState(false);
  const [busyControl, setBusyControl] = useState(false);
  const reconnectMs = useRef(500);
  const fallbackPoll = useRef<number | null>(null);
  const pendingMarketTick = useRef<Market[] | null>(null);
  const marketTickTimer = useRef<number | null>(null);

  const summary = useMemo(() => {
    let open = 0;
    let closed = 0;
    let pnl = 0;
    for (const trade of trades) {
      if (trade.status === "OPEN") open += 1;
      else closed += 1;
      pnl += Number(trade.pnl || 0);
    }
    return { open, closed, pnl };
  }, [trades]);

  const activeMarkets = useMemo(
    () => markets.filter((m) => m.accepting_orders !== false && m.closed !== true).length,
    [markets]
  );

  function log(message: string) {
    setLogs((current) => [`${new Date().toLocaleTimeString()} ${message}`, ...current].slice(0, 80));
  }

  async function refreshStatus() {
    const data = await api<{ runtime: Runtime }>("/api/status");
    setRuntime(data.runtime || {});
  }

  async function refreshConfig() {
    const data = await api<Config>("/api/config");
    setConfig({ ...emptyConfig, ...data, paper_mode: data.paper_mode !== false });
  }

  async function refreshTrades() {
    setTrades(await api<Trade[]>("/api/trades"));
  }

  async function refreshPositions() {
    setPositions(await api<Position[]>("/api/positions"));
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

  async function refreshMarkets() {
    if (loadingMarkets) return;
    setLoadingMarkets(true);
    try {
      setMarkets(await api<Market[]>("/api/markets"));
    } catch (error) {
      log(`markets: ${(error as Error).message}`);
    } finally {
      setLoadingMarkets(false);
    }
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

  async function clearPositions() {
    try {
      const result = await api<{ cleared?: number }>("/api/trades/clear-open-positions", { method: "POST" });
      log(`cleared ${result.cleared || 0} positions`);
      await Promise.all([refreshTrades(), refreshPositions(), refreshStatus()]);
    } catch (error) {
      log((error as Error).message);
    }
  }

  async function clearTradeHistory() {
    if (!window.confirm("Delete all trade history? This cannot be undone.")) return;
    try {
      const result = await api<{ cleared?: number }>("/api/trades/clear", { method: "POST" });
      log(`cleared ${result.cleared || 0} trades`);
      await Promise.all([refreshTrades(), refreshPositions(), refreshStatus()]);
    } catch (error) {
      log((error as Error).message);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const saved = await api<Config>("/api/config", { method: "PUT", body: JSON.stringify(config) });
      setConfig({ ...emptyConfig, ...saved, paper_mode: saved.paper_mode !== false });
      log("settings saved");
      await Promise.allSettled([refreshStatus(), refreshMarkets()]);
    } catch (error) {
      log((error as Error).message);
    }
  }

  function updateEnabledMarket(asset: string, timeframe: string, checked: boolean) {
    setConfig((current) => {
      const enabled = { ...current.enabled_markets };
      const values = new Set(enabled[asset] || []);
      if (checked) values.add(timeframe);
      else values.delete(timeframe);
      enabled[asset] = Array.from(values);
      return { ...current, enabled_markets: enabled };
    });
  }

  useEffect(() => {
    Promise.allSettled([
      refreshStatus(),
      refreshConfig(),
      refreshTrades(),
      refreshPositions(),
      refreshAccount(),
      refreshMarkets(),
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
    let closed = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    function startFallbackPolling() {
      if (fallbackPoll.current !== null) return;
      fallbackPoll.current = window.setInterval(
        () => refreshMarkets().catch((error) => log(error.message)),
        5000
      );
    }

    function stopFallbackPolling() {
      if (fallbackPoll.current === null) return;
      window.clearInterval(fallbackPoll.current);
      fallbackPoll.current = null;
    }

    function flushMarketTick() {
      marketTickTimer.current = null;
      const incoming = pendingMarketTick.current;
      pendingMarketTick.current = null;
      if (!incoming) return;
      setMarkets((prev) => {
        return mergeMarketTick(prev || [], incoming);
      });
    }

    function scheduleMarketTick(markets: Market[]) {
      pendingMarketTick.current = markets;
      if (marketTickTimer.current !== null) return;
      marketTickTimer.current = window.setTimeout(flushMarketTick, MARKET_TICK_THROTTLE_MS);
    }

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
      ws.onopen = () => {
        setSocketOnline(true);
        reconnectMs.current = 500;
        stopFallbackPolling();
        log("ws connected");
      };
      ws.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as WsEvent;
          if (event.type === "log") {
            const msg = String(event.payload.message);
            if (shouldShowRealtimeLog(msg)) {
              log(msg);
            }
          }
          if (event.type === "markets" || event.type === "market_tick")
            scheduleMarketTick(event.payload.markets || []);
          if (event.type === "positions") setPositions(event.payload.positions || []);
          if (event.type === "bot_status") setRuntime(event.payload || {});
          if (event.type === "order_placed")
            Promise.allSettled([refreshTrades(), refreshPositions()]);
          if (event.type === "market_resolved" || event.type === "trade_resolved") {
            Promise.allSettled([refreshTrades(), refreshPositions(), refreshStatus()]);
          }
        } catch (error) {
          log(`ws parse: ${(error as Error).message}`);
        }
      };
      ws.onclose = () => {
        setSocketOnline(false);
        startFallbackPolling();
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
      if (marketTickTimer.current !== null) window.clearTimeout(marketTickTimer.current);
      marketTickTimer.current = null;
      pendingMarketTick.current = null;
      stopFallbackPolling();
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
        totalPnl={summary.pnl}
        openPositions={summary.open}
        activeMarkets={activeMarkets}
      />

      <main className="p-4 lg:p-6">
        <section className="min-w-0 space-y-4">
          <AccountHeroPanel account={account} loading={loadingAccount} />
          {activeView === "markets" && (
            <MarketsView
              markets={markets}
              trades={trades}
              positions={positions}
              logs={logs}
              loadingMarkets={loadingMarkets}
              onRefresh={refreshMarkets}
              onClearLogs={() => setLogs([])}
              onClearPositions={clearPositions}
              onClearTradeHistory={clearTradeHistory}
            />
          )}
          {activeView === "account" && (
            <AccountHeroPanel account={account} loading={loadingAccount} />
          )}
          {activeView === "settings" && (
            <SettingsView
              config={config}
              runtime={runtime}
              setConfig={setConfig}
              onSubmit={saveSettings}
              onEnabledMarketChange={updateEnabledMarket}
            />
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
