type LedgerKind = "position" | "trade";

export type LedgerRow = {
  activity: string;
  title: string;
  outcome: string;
  badge: string;
  shares: string;
  price: string;
  value: string;
  time: string;
  tone: "up" | "down" | "neutral";
};

export function formatLedgerRow(item: Record<string, any>, kind: LedgerKind, nowSeconds?: number): LedgerRow {
  const price = firstNumber(item, ["price", "avg_price", "avgPrice", "average_price"]);
  const shares = firstNumber(item, ["size", "shares", "amount"]);
  const timestamp = firstNumber(item, ["timestamp", "createdAt", "created_at", "opened_at", "closed_at"]);
  const side = String(item.side || "").toUpperCase();
  const outcome = findOutcome(item);
  const activity = kind === "position" ? "Posición" : side === "SELL" ? "Vender" : "Comprar";
  const tradeValue = kind === "trade" && price != null && shares != null ? price * shares * (side === "SELL" ? 1 : -1) : null;

  return {
    activity,
    title: formatTitle(item),
    outcome,
    badge: formatBadge(outcome, price),
    shares: shares == null ? "-" : shares.toFixed(2),
    price: price == null ? "-" : `${Math.round(price * 100)}c`,
    value: money(tradeValue),
    time: timestamp == null ? (kind === "position" ? "Abierta" : "-") : formatDate(timestamp),
    tone: outcome.toLowerCase() === "down" ? "down" : outcome.toLowerCase() === "up" ? "up" : "neutral",
  };
}

export function relativeLedgerTime(value: unknown, nowSeconds = Date.now() / 1000): string {
  const timestamp = num(value);
  if (timestamp == null) return "-";
  const seconds = Math.max(0, nowSeconds - timestamp);
  const days = Math.floor(seconds / 86_400);
  if (days >= 1) return `${days}d hace`;
  const hours = Math.floor(seconds / 3_600);
  if (hours >= 1) return `${hours}h hace`;
  const minutes = Math.max(1, Math.floor(seconds / 60));
  return `${minutes}m hace`;
}

function formatTitle(item: Record<string, any>): string {
  const explicit = firstString(item, ["title", "question", "event_title", "eventTitle", "market_title", "marketTitle", "name"]);
  if (explicit) return explicit;
  const fallback = firstString(item, ["market_slug", "slug", "market"]);
  return prettifySlug(fallback || "-");
}

function formatOutcome(value: string): string {
  const clean = value.trim();
  const upper = clean.toUpperCase();
  if (upper === "YES" || upper === "UP") return "Up";
  if (upper === "NO" || upper === "DOWN") return "Down";
  if (upper === "BUY" || upper === "SELL") return "-";
  return clean || "-";
}

function findOutcome(item: Record<string, any>): string {
  const direct = formatOutcome(firstString(item, ["outcome", "outcome_side", "outcomeSide"]));
  if (direct !== "-") return direct;
  const rawOutcome = formatOutcome(firstRawString(item, ["outcome", "outcome_side", "outcomeSide", "asset", "token"]));
  if (rawOutcome !== "-") return rawOutcome;
  const side = formatOutcome(String(item.side || ""));
  if (side !== "-") return side;
  const asset = formatOutcome(String(item.asset || ""));
  return asset === "Up" || asset === "Down" ? asset : "-";
}

function formatBadge(outcome: string, price: number | null): string {
  if (outcome === "-") return price == null ? "-" : `${Math.round(price * 100)}c`;
  return price == null ? outcome : `${outcome} ${Math.round(price * 100)}c`;
}

function formatDate(value: number): string {
  const millis = value > 10_000_000_000 ? value : value * 1000;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(millis));
}

function money(value: number | null): string {
  if (value == null) return "-";
  const prefix = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${prefix}$${Math.abs(value).toFixed(2)}`;
}

function firstNumber(item: Record<string, any>, keys: string[]): number | null {
  for (const key of keys) {
    const value = valueFor(item, key);
    const parsed = num(value);
    if (parsed != null) return parsed;
  }
  return null;
}

function firstString(item: Record<string, any>, keys: string[]): string {
  for (const key of keys) {
    const value = valueFor(item, key);
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function firstRawString(item: Record<string, any>, keys: string[]): string {
  const raw = item.raw;
  if (!raw || typeof raw !== "object") return "";
  for (const key of keys) {
    const value = valueFor(raw, key);
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function valueFor(item: Record<string, any>, key: string): unknown {
  if (item[key] != null && item[key] !== "") return item[key];
  const raw = item.raw;
  if (!raw || typeof raw !== "object") return undefined;
  if (raw[key] != null && raw[key] !== "") return raw[key];
  const market = raw.market;
  if (market && typeof market === "object" && market[key] != null && market[key] !== "") return market[key];
  const event = raw.event;
  if (event && typeof event === "object" && event[key] != null && event[key] !== "") return event[key];
  return undefined;
}

function prettifySlug(value: string): string {
  if (!value || value === "-") return "-";
  if (/^0x[a-f0-9]+$/i.test(value)) return "-";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .trim() || "-";
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
