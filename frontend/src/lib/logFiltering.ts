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
];

export function shouldShowRealtimeLog(message: string, config?: Pick<Config, "strategy_groups" | "strategies">): boolean {
  const strategy = message.match(/\bstrategy=([^\s]+)/)?.[1];
  if (strategy && config) {
    const strategyConfig = config.strategies?.[strategy];
    const groupConfig = strategyConfig ? config.strategy_groups?.[strategyConfig.group] : undefined;
    if (!strategyConfig?.enabled || !groupConfig?.enabled) return false;
  }
  return IMPORTANT_LOG_MARKERS.some((marker) => message.includes(marker));
}
