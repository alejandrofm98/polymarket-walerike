export function formatNumber(value: unknown, digits: number) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "";
}

export function formatBidAsk(_bid?: number | null, ask?: number | null) {
  return formatNumber(ask, 3) || "-";
}

export function formatChartValue(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${number.toLocaleString(undefined, { maximumFractionDigits: Math.abs(number) >= 100 ? 0 : 3 })}`;
}

export function formatChartTime(value: unknown) {
  const time = Number(value);
  if (!Number.isFinite(time)) return "";
  return new Date(time).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function formatSide(side?: string) {
  const normalized = side?.trim().toUpperCase();
  if (normalized === "YES") return "UP";
  if (normalized === "NO") return "DOWN";
  return side || "";
}

export function sideClass(side?: string) {
  const label = formatSide(side);
  if (label === "UP") return "text-emerald-400";
  if (label === "DOWN") return "text-red-400";
  return "";
}

export function getMarketKey(market: { asset?: string; timeframe?: string; event_slug?: string; slug?: string }) {
  return `${market.asset || "?"}:${market.timeframe || "?"}:${market.event_slug || market.slug || "?"}`;
}

const TIMEFRAME_SECONDS: Record<string, number> = {
  "5m": 300,
  "15m": 900,
  "1h": 3600,
};

function parseTimestampFromSlug(slug?: string | null): number | null {
  if (!slug) return null;
  const match = slug.match(/-(\d{10})$/);
  if (match) return parseInt(match[1], 10);
  return null;
}

function getWindowDuration(tf?: string | null): number {
  return TIMEFRAME_SECONDS[tf || ""] || 300;
}

function parseWindowStart(arg: { window_start_timestamp?: number | null } | number | null): number | null {
  if (arg == null) return null;
  if (typeof arg === "number") return arg;
  return arg.window_start_timestamp ?? null;
}

export function formatMarketWindow(data: {
  timeframe?: string | null;
  window_start_timestamp?: number | null;
  end_date?: string | null;
  market_slug?: string | null;
}) {
  const duration = getWindowDuration(data.timeframe);
  let start: number | null = null;

  if (data.window_start_timestamp != null) {
    start = data.window_start_timestamp;
  } else if (data.market_slug) {
    start = parseTimestampFromSlug(data.market_slug);
  }

  if (start == null && data.end_date) {
    try {
      const end = new Date(data.end_date);
      if (!isNaN(end.getTime())) {
        start = Math.floor((end.getTime() / 1000) - duration);
      }
    } catch {
      // ignore parse errors
    }
  }

  if (start == null) return data.market_slug || "";

  const end = start + duration;
  const fmt = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/New_York",
    timeZoneName: "short",
  });

  const formatTime = (ts: number) => {
    const date = new Date(ts * 1000);
    return fmt.formatToParts(date).reduce((acc, part) => {
      if (part.type === "literal" && part.value.includes(":")) return acc;
      if (part.type === "timeZoneName") return acc;
      return acc + part.value;
    }, "").trim();
  };

  const formatTimeRange = (startTs: number, endTs: number) => {
    const sDate = new Date(startTs * 1000);
    const eDate = new Date(endTs * 1000);
    const sParts = fmt.formatToParts(sDate);
    const eParts = fmt.formatToParts(eDate);

    const getPart = (parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) =>
      parts.find((p) => p.type === type)?.value || "";

    const month = getPart(sParts, "month");
    const day = getPart(sParts, "day");
    const sHour = getPart(sParts, "hour");
    const sMinute = getPart(sParts, "minute");
    const eHour = getPart(eParts, "hour");
    const eMinute = getPart(eParts, "minute");
    const ampm = getPart(sParts, "dayPeriod");

    return `${month} ${day}, ${sHour}:${sMinute}-${eHour}:${eMinute}${ampm} ET`;
  };

  return formatTimeRange(start, end);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}
