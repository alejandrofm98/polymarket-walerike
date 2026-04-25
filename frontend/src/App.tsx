import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Bot, Download, Pause, Play, RefreshCcw, Trash2, Wifi, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

type View = "markets" | "settings" | "logs";

type Runtime = {
  status?: string;
  running?: boolean;
  paused?: boolean;
  paper_mode?: boolean;
};

type Config = {
  capital_per_trade: number;
  min_margin_for_arbitrage: number;
  entry_threshold: number;
  max_sum_avg: number;
  max_buys_per_side: number;
  shares_per_order: number;
  paper_mode: boolean;
  enabled_markets: Record<string, string[]>;
  explicit_slugs?: string[];
};

type Market = {
  asset?: string;
  timeframe?: string;
  event_slug?: string;
  slug?: string;
  price_to_beat?: number | null;
  current_price?: number | null;
  price_diff?: number | null;
  price_diff_pct?: number | null;
  best_bid_up?: number | null;
  best_ask_up?: number | null;
  best_bid_down?: number | null;
  best_ask_down?: number | null;
  edge?: number | null;
  seconds_left?: number | null;
  accepting_orders?: boolean;
  closed?: boolean;
};

type Trade = {
  trade_id?: string;
  market?: string;
  side?: string;
  size?: number;
  status?: string;
  pnl?: number;
};

type Position = {
  asset?: string;
  side?: string;
  size?: number;
  avg_price?: number;
  price?: number;
  market?: string;
};

type WsEvent = {
  type: string;
  payload: Record<string, any>;
};

type ChartSeries = {
  prices: number[];
  targets: Array<number | null>;
};

const assets = ["BTC", "ETH", "SOL"];
const timeframes = ["5m", "15m", "1h"];

const emptyConfig: Config = {
  capital_per_trade: 0,
  min_margin_for_arbitrage: 0,
  entry_threshold: 0,
  max_sum_avg: 0,
  max_buys_per_side: 1,
  shares_per_order: 1,
  paper_mode: true,
  enabled_markets: {},
  explicit_slugs: [],
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

function formatNumber(value: unknown, digits: number) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "";
}

function formatBidAsk(_bid?: number | null, ask?: number | null) {
  return formatNumber(ask, 3) || "-";
}

function getMarketKey(market: Market) {
  return `${market.asset || "?"}:${market.timeframe || "?"}:${market.event_slug || market.slug || "?"}`;
}

function App() {
  const [activeView, setActiveView] = useState<View>("markets");
  const [runtime, setRuntime] = useState<Runtime>({ status: "stopped", running: false, paused: false });
  const [socketOnline, setSocketOnline] = useState(false);
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [loadingMarkets, setLoadingMarkets] = useState(false);
  const [busyControl, setBusyControl] = useState(false);
  const [chartData, setChartData] = useState<Record<string, ChartSeries>>({});
  const reconnectMs = useRef(500);
  const fallbackPoll = useRef<number | null>(null);

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

  async function clearPaperOrders() {
    try {
      const result = await api<{ cleared?: number }>("/api/trades/clear-open-paper", { method: "POST" });
      log(`cleared ${result.cleared || 0} paper orders`);
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
      if (activeView === "markets") await refreshMarkets();
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
    Promise.allSettled([refreshStatus(), refreshConfig(), refreshTrades(), refreshPositions(), refreshMarkets()]).then((results) => {
      for (const result of results) {
        if (result.status === "rejected") log((result.reason as Error).message);
      }
    });
  }, []);

  useEffect(() => {
    setChartData((current) => {
      const next = { ...current };
      for (const market of markets) {
        const price = Number(market.current_price);
        if (!Number.isFinite(price)) continue;
        const key = getMarketKey(market);
        const series = next[key] || { prices: [], targets: [] };
        next[key] = {
          prices: [...series.prices, price].slice(-120),
          targets: [...series.targets, Number.isFinite(Number(market.price_to_beat)) ? Number(market.price_to_beat) : null].slice(-120),
        };
      }
      return next;
    });
  }, [markets]);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    function startFallbackPolling() {
      if (fallbackPoll.current !== null) return;
      fallbackPoll.current = window.setInterval(() => refreshMarkets().catch((error) => log(error.message)), 5000);
    }

    function stopFallbackPolling() {
      if (fallbackPoll.current === null) return;
      window.clearInterval(fallbackPoll.current);
      fallbackPoll.current = null;
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
          if (event.type !== "market_tick") log(event.type === "log" ? String(event.payload.message) : event.type);
          if (event.type === "markets" || event.type === "market_tick") setMarkets(event.payload.markets || []);
          if (event.type === "positions") setPositions(event.payload.positions || []);
          if (event.type === "bot_status") setRuntime(event.payload || {});
          if (event.type === "order_placed") Promise.allSettled([refreshTrades(), refreshPositions()]);
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
      stopFallbackPolling();
      ws?.close();
    };
  }, []);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(249,115,22,0.16),_transparent_32rem),linear-gradient(180deg,_#080b11_0%,_#0c1018_100%)]">
      <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur-xl">
        <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border bg-primary/15 text-primary">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Walerike</h1>
              <p className="text-xs text-muted-foreground">Polymarket crypto hedge dashboard</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <NavButton active={activeView === "markets"} onClick={() => setActiveView("markets")}>Markets</NavButton>
            <NavButton active={activeView === "settings"} onClick={() => setActiveView("settings")}>Settings</NavButton>
            <NavButton active={activeView === "logs"} onClick={() => setActiveView("logs")}>Logs</NavButton>
            <Button variant="outline" onClick={controlBot} disabled={busyControl}>
              {runtime.running && !runtime.paused ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {runtime.running && !runtime.paused ? "Pause" : "Play"}
            </Button>
            <Button variant="secondary" onClick={() => (window.location.href = "/api/trades/export.csv")}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
          </div>
        </div>
      </header>

      <main className="grid gap-4 p-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:p-6">
        <aside className="space-y-4">
          <StatusCard runtime={runtime} socketOnline={socketOnline} />
          <AccountCard open={summary.open} closed={summary.closed} pnl={summary.pnl} />
        </aside>

        <section className="min-w-0 space-y-4">
          {activeView === "markets" && (
            <MarketsView
              markets={markets}
              trades={trades}
              positions={positions}
              chartData={chartData}
              loadingMarkets={loadingMarkets}
              onRefresh={() => refreshMarkets()}
              onClearPaperOrders={clearPaperOrders}
            />
          )}
          {activeView === "settings" && (
            <SettingsView
              config={config}
              setConfig={setConfig}
              onSubmit={saveSettings}
              onEnabledMarketChange={updateEnabledMarket}
            />
          )}
          {activeView === "logs" && <LogsView logs={logs} onClear={() => setLogs([])} />}
        </section>
      </main>
    </div>
  );
}

function NavButton({ active, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean }) {
  return (
    <button
      className={cn(
        "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        active && "bg-muted text-foreground ring-1 ring-border",
        className,
      )}
      {...props}
    />
  );
}

function StatusCard({ runtime, socketOnline }: { runtime: Runtime; socketOnline: boolean }) {
  return (
    <Card className="bg-card/80 backdrop-blur">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-wide text-muted-foreground">
          <Activity className="h-4 w-4" /> Status
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <SummaryRow label="Runtime" value={runtime.status || "stopped"} />
        <SummaryRow label="Mode" value={runtime.paper_mode === false ? "live" : "paper"} />
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Socket</span>
          <Badge variant={socketOnline ? "default" : "secondary"} className={cn(socketOnline ? "bg-emerald-500" : "")}>{socketOnline ? <Wifi className="mr-1 h-3 w-3" /> : <WifiOff className="mr-1 h-3 w-3" />}{socketOnline ? "online" : "offline"}</Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function AccountCard({ open, closed, pnl }: { open: number; closed: number; pnl: number }) {
  return (
    <Card className="bg-card/80 backdrop-blur">
      <CardHeader>
        <CardTitle className="text-sm uppercase tracking-wide text-muted-foreground">Account</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <SummaryRow label="Open" value={String(open)} />
        <SummaryRow label="Closed" value={String(closed)} />
        <SummaryRow label="PnL" value={pnl.toFixed(2)} valueClassName={pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
      </CardContent>
    </Card>
  );
}

function SummaryRow({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("font-semibold", valueClassName)}>{value}</span>
    </div>
  );
}

function MarketsView(props: {
  markets: Market[];
  trades: Trade[];
  positions: Position[];
  chartData: Record<string, ChartSeries>;
  loadingMarkets: boolean;
  onRefresh: () => void;
  onClearPaperOrders: () => void;
}) {
  return (
    <>
      <Card className="overflow-hidden bg-card/80 backdrop-blur">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Live Markets</CardTitle>
            <CardDescription>Resolved markets, CLOB prices and active edge.</CardDescription>
          </div>
          <Button variant="outline" onClick={props.onRefresh} disabled={props.loadingMarkets}>
            <RefreshCcw className={cn("h-4 w-4", props.loadingMarkets && "animate-spin")} /> Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <MarketsTable markets={props.markets} />
        </CardContent>
      </Card>

      <Card className="bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle>Price Charts</CardTitle>
          <CardDescription>Last 120 market updates per active market.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 xl:grid-cols-2">
            {props.markets.length ? props.markets.map((market) => <PriceChart key={getMarketKey(market)} market={market} series={props.chartData[getMarketKey(market)]} />) : <EmptyState>No charts yet</EmptyState>}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle>Positions</CardTitle>
        </CardHeader>
        <CardContent>
          {props.positions.length ? <div className="grid gap-2">{props.positions.map((position, index) => <PositionRow key={`${position.market}-${index}`} position={position} />)}</div> : <EmptyState>No positions</EmptyState>}
        </CardContent>
      </Card>

      <Card className="bg-card/80 backdrop-blur">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Trade History</CardTitle>
          <Button variant="outline" size="sm" onClick={props.onClearPaperOrders}><Trash2 className="h-4 w-4" /> Clear Paper Orders</Button>
        </CardHeader>
        <CardContent>
          <TradesTable trades={props.trades} />
        </CardContent>
      </Card>
    </>
  );
}

function MarketsTable({ markets }: { markets: Market[] }) {
  if (!markets.length) return <EmptyState>No markets loaded</EmptyState>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Asset</TableHead><TableHead>TF</TableHead><TableHead>Slug</TableHead><TableHead>Target</TableHead><TableHead>Current</TableHead><TableHead>Diff</TableHead><TableHead>UP</TableHead><TableHead>DOWN</TableHead><TableHead>Edge</TableHead><TableHead>Left</TableHead><TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {markets.map((market) => {
          const slug = market.event_slug || market.slug || "";
          const diff = market.price_diff != null ? `${market.price_diff >= 0 ? "+" : ""}$${market.price_diff.toFixed(2)}` : "-";
          const diffPct = market.price_diff_pct != null ? `${market.price_diff_pct >= 0 ? "+" : ""}${market.price_diff_pct.toFixed(2)}%` : "-";
          const status = market.accepting_orders === false || market.closed === true ? "closed" : "accepting";
          return (
            <TableRow key={getMarketKey(market)}>
              <TableCell className="font-semibold">{market.asset}</TableCell>
              <TableCell>{market.timeframe}</TableCell>
              <TableCell className="max-w-[220px] truncate">{slug ? <a href={`https://polymarket.com/event/${slug}`} target="_blank" rel="noreferrer" title={slug}>{slug}</a> : "-"}</TableCell>
              <TableCell>{formatNumber(market.price_to_beat, 2) || "-"}</TableCell>
              <TableCell>{formatNumber(market.current_price, 2) || "-"}</TableCell>
              <TableCell className={cn(Number(market.price_diff) > 0 && "text-emerald-400", Number(market.price_diff) < 0 && "text-red-400")}>{diff} ({diffPct})</TableCell>
              <TableCell>{formatBidAsk(market.best_bid_up, market.best_ask_up)}</TableCell>
              <TableCell>{formatBidAsk(market.best_bid_down, market.best_ask_down)}</TableCell>
              <TableCell>{formatNumber(market.edge, 4) || "-"}</TableCell>
              <TableCell>{market.seconds_left != null ? `${Math.floor(market.seconds_left / 60)}:${String(market.seconds_left % 60).padStart(2, "0")}` : "-"}</TableCell>
              <TableCell><Badge variant={status === "accepting" ? "default" : "secondary"} className={status === "accepting" ? "bg-emerald-500" : ""}>{status}</Badge></TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function PriceChart({ market, series }: { market: Market; series?: ChartSeries }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !series?.prices.length) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(ratio, ratio);
    const width = rect.width;
    const height = rect.height;
    const targets = series.targets.filter((value): value is number => value != null);
    const values = [...series.prices, ...targets];
    const min = Math.min(...values) * 0.995;
    const max = Math.max(...values) * 1.005;
    const range = max - min || 1;
    const y = (value: number) => height - ((value - min) / range) * (height - 24) - 12;
    const step = width / (series.prices.length - 1 || 1);
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i += 1) {
      const gy = (height / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(width, gy);
      ctx.stroke();
    }
    const target = targets[0];
    if (target != null) {
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = "#f59e0b";
      ctx.beginPath();
      ctx.moveTo(0, y(target));
      ctx.lineTo(width, y(target));
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const last = series.prices[series.prices.length - 1];
    ctx.strokeStyle = target != null && last < target ? "#f97316" : "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    series.prices.forEach((price, index) => {
      const x = index * step;
      const py = y(price);
      if (index === 0) ctx.moveTo(x, py);
      else ctx.lineTo(x, py);
    });
    ctx.stroke();
    ctx.fillStyle = "rgba(148,163,184,0.72)";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`$${min.toFixed(2)}`, 4, height - 6);
    ctx.fillText(`$${max.toFixed(2)}`, 4, 12);
  }, [series]);
  return (
    <div className="rounded-lg border bg-background/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{market.asset} {market.timeframe}</h3>
        <span className="text-xs text-muted-foreground">{formatNumber(market.current_price, 2) || "-"}</span>
      </div>
      <canvas ref={canvasRef} className="chart-canvas rounded-md border bg-background/60" />
    </div>
  );
}

function PositionRow({ position }: { position: Position }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background/40 px-3 py-2 text-sm">
      <span className="font-semibold">{position.asset || ""} {position.side || ""}</span>
      <span className="text-muted-foreground">size={Number(position.size || 0).toFixed(2)} avg={Number(position.avg_price || position.price || 0).toFixed(3)}</span>
      <span className="max-w-full truncate text-muted-foreground">{position.market || ""}</span>
    </div>
  );
}

function TradesTable({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <EmptyState>No trades</EmptyState>;
  return (
    <Table>
      <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Market</TableHead><TableHead>Side</TableHead><TableHead>Size</TableHead><TableHead>Status</TableHead><TableHead>PnL</TableHead></TableRow></TableHeader>
      <TableBody>{trades.map((trade, index) => <TableRow key={`${trade.trade_id}-${index}`}><TableCell>{trade.trade_id}</TableCell><TableCell>{trade.market}</TableCell><TableCell>{trade.side}</TableCell><TableCell>{trade.size}</TableCell><TableCell>{trade.status}</TableCell><TableCell className={cn(Number(trade.pnl) >= 0 ? "text-emerald-400" : "text-red-400")}>{Number(trade.pnl || 0).toFixed(2)}</TableCell></TableRow>)}</TableBody>
    </Table>
  );
}

function SettingsView({ config, setConfig, onSubmit, onEnabledMarketChange }: { config: Config; setConfig: React.Dispatch<React.SetStateAction<Config>>; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onEnabledMarketChange: (asset: string, timeframe: string, checked: boolean) => void }) {
  function setNumber(key: keyof Config, value: string) {
    setConfig((current) => ({ ...current, [key]: Number(value) }));
  }
  return (
    <form className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]" onSubmit={onSubmit}>
      <Card className="bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle>Bot Settings</CardTitle>
          <CardDescription>Runtime controls persisted through backend config.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Capital per trade"><Input type="number" min="1" step="1" value={config.capital_per_trade} onChange={(event) => setNumber("capital_per_trade", event.target.value)} /></Field>
          <Field label="Arb threshold"><Input type="number" min="0" max="1" step="0.001" value={config.min_margin_for_arbitrage} onChange={(event) => setNumber("min_margin_for_arbitrage", event.target.value)} /></Field>
          <Field label="Entry threshold"><Input type="number" min="0.01" max="0.99" step="0.001" value={config.entry_threshold} onChange={(event) => setNumber("entry_threshold", event.target.value)} /></Field>
          <Field label="Max sum avg"><Input type="number" min="0.01" max="1" step="0.001" value={config.max_sum_avg} onChange={(event) => setNumber("max_sum_avg", event.target.value)} /></Field>
          <Field label="Max buys per side"><Input type="number" min="1" step="1" value={config.max_buys_per_side} onChange={(event) => setNumber("max_buys_per_side", event.target.value)} /></Field>
          <Field label="Shares per order"><Input type="number" min="1" step="1" value={config.shares_per_order} onChange={(event) => setNumber("shares_per_order", event.target.value)} /></Field>
          <div className="flex items-center justify-between rounded-lg border bg-background/40 p-3 sm:col-span-2">
            <div><Label>Paper mode</Label><p className="text-xs text-muted-foreground">Live trading remains backend-gated.</p></div>
            <Switch checked={config.paper_mode !== false} onCheckedChange={(checked) => setConfig((current) => ({ ...current, paper_mode: checked }))} />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Explicit slugs</Label>
            <textarea className="min-h-28 rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm outline-none ring-offset-background focus-visible:ring-1 focus-visible:ring-ring" value={(config.explicit_slugs || []).join("\n")} onChange={(event) => setConfig((current) => ({ ...current, explicit_slugs: event.target.value.split(/[\n,]/).map((slug) => slug.trim()).filter(Boolean) }))} placeholder="btc-updown-5m-..." />
          </div>
          <Button className="sm:col-span-2" type="submit">Save Settings</Button>
        </CardContent>
      </Card>

      <Card className="bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle>Markets Matrix</CardTitle>
          <CardDescription>Select asset/timeframe pairs to scan.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="market-grid text-sm">
            <div />
            {timeframes.map((timeframe) => <div key={timeframe} className="text-center text-xs font-semibold uppercase text-muted-foreground">{timeframe}</div>)}
            {assets.map((asset) => [
              <div key={`${asset}-label`} className="font-semibold">{asset}</div>,
              ...timeframes.map((timeframe) => <label key={`${asset}-${timeframe}`} className="flex justify-center rounded-md border bg-background/40 p-2"><input type="checkbox" checked={(config.enabled_markets[asset] || []).includes(timeframe)} onChange={(event) => onEnabledMarketChange(asset, timeframe, event.target.checked)} /></label>),
            ])}
          </div>
        </CardContent>
      </Card>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid gap-2"><Label>{label}</Label>{children}</div>;
}

function LogsView({ logs, onClear }: { logs: string[]; onClear: () => void }) {
  return (
    <Card className="bg-card/80 backdrop-blur">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div><CardTitle>Realtime Log</CardTitle><CardDescription>WebSocket events and UI errors.</CardDescription></div>
        <Button variant="outline" size="sm" onClick={onClear}>Clear</Button>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[520px] rounded-lg border bg-background/60 p-3">
          {logs.length ? <ol className="space-y-1 font-mono text-xs text-muted-foreground">{logs.map((entry, index) => <li key={`${entry}-${index}`}>{entry}</li>)}</ol> : <EmptyState>No logs</EmptyState>}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed bg-background/30 p-6 text-center text-sm text-muted-foreground">{children}</div>;
}

export default App;
