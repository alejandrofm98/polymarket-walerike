const IMPORTANT_LOG_MARKERS = [
  "control",
  "started",
  "stopped",
  "paused",
  "order",
  "APPROVED",
  "BET_EVAL",
  "BET_SKIP",
  "placed",
  "attempt",
  "FAILED",
  "error",
  "ERROR",
];

export function shouldShowRealtimeLog(message: string): boolean {
  return IMPORTANT_LOG_MARKERS.some((marker) => message.includes(marker));
}
