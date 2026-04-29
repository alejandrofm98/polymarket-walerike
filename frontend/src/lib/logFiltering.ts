import type { Config } from "@/types";

const IMPORTANT_LOG_MARKERS = [
  "control",
  "started",
  "stopped",
  "paused",
  "order",
  "APPROVED",
  "BET_SKIP",
  "placed",
  "attempt",
  "FAILED",
  "error",
  "ERROR",
  "COPY",
  "copy",
];

export function shouldShowRealtimeLog(message: string, _config?: Partial<Config>): boolean {
  return IMPORTANT_LOG_MARKERS.some((marker) => message.includes(marker));
}