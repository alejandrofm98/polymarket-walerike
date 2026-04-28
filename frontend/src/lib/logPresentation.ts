export type LogTone = "info" | "connected" | "error" | "trade" | "decision" | "skip";

export interface LogPresentation {
  label: string;
  tone: LogTone;
}

export type LogTokenKind = "text" | "tag" | "market" | "strategy" | "field";

export interface LogToken {
  text: string;
  kind: LogTokenKind;
  colorClass?: string;
}

export function getLogPresentation(message: string): LogPresentation {
  const normalized = message.toLowerCase();

  if (normalized.includes("error") || normalized.includes("failed") || normalized.includes("abort")) {
    return { label: "ERROR", tone: "error" };
  }
  if (normalized.includes("[trade]") || normalized.includes("[order_accepted]") || normalized.includes("placed")) {
    return { label: "TRADE", tone: "trade" };
  }
  if (normalized.includes("[bet_decision]") || normalized.includes("[bet_eval]")) {
    return { label: "DECISION", tone: "decision" };
  }
  if (normalized.includes("[skip]") || normalized.includes("skipped") || normalized.includes("[snapshot_skip]")) {
    return { label: "SKIP", tone: "skip" };
  }
  if (normalized.includes("connected") || normalized.includes("started")) {
    return { label: "LIVE", tone: "connected" };
  }

  return { label: "INFO", tone: "info" };
}

export function tokenizeLogMessage(message: string): LogToken[] {
  return message.split(/\s+/).filter(Boolean).map((part) => {
    if (/^\[[A-Z_]+\]$/.test(part)) return { text: part, kind: "tag" };
    if (part.startsWith("market=")) return { text: part, kind: "market" };
    if (part.startsWith("strategy=")) {
      return { text: part, kind: "strategy", colorClass: strategyColorClass(part.slice("strategy=".length)) };
    }
    if (/^[a-z_]+=.*/.test(part)) return { text: part, kind: "field" };
    return { text: part, kind: "text" };
  });
}

function strategyColorClass(strategy: string): string {
  const classes = [
    "text-orange-200 border-orange-300/25 bg-orange-300/10",
    "text-sky-200 border-sky-300/25 bg-sky-300/10",
    "text-emerald-200 border-emerald-300/25 bg-emerald-300/10",
    "text-fuchsia-200 border-fuchsia-300/25 bg-fuchsia-300/10",
    "text-amber-200 border-amber-300/25 bg-amber-300/10",
  ];
  let hash = 0;
  for (const char of strategy) hash = (hash + char.charCodeAt(0)) % classes.length;
  return classes[hash];
}
