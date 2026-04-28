"""Grouped strategy evaluation for conservative crypto up/down markets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.config.runtime_config import normalize_strategies, normalize_strategy_groups
from bot.core.hedge_strategy import HedgeMode, HedgeSignal, MarketSnapshot


class StrategyRegistry:
    def __init__(self, strategy_groups: dict[str, dict[str, Any]] | None = None, strategies: dict[str, dict[str, Any]] | None = None) -> None:
        self.strategy_groups = normalize_strategy_groups(strategy_groups)
        self.strategies = normalize_strategies(strategies, self.strategy_groups)

    def configure(self, strategy_groups: dict[str, dict[str, Any]] | None, strategies: dict[str, dict[str, Any]] | None) -> None:
        self.strategy_groups = normalize_strategy_groups(strategy_groups)
        self.strategies = normalize_strategies(strategies, self.strategy_groups)

    def evaluate(self, snapshot: MarketSnapshot, capital_per_trade: float, momentum_pct: float) -> list[HedgeSignal]:
        signals: list[HedgeSignal] = []
        for name, config in self.strategies.items():
            if not self._matches(config, snapshot):
                continue
            group = self.strategy_groups[config["group"]]
            capital = capital_per_trade * float(group.get("capital_fraction", 1.0))
            signal = self._evaluate_strategy(name, snapshot, capital, momentum_pct)
            if signal is not None and (signal.yes_size > 0 or signal.no_size > 0):
                signal.strategy_name = name
                signals.append(signal)
        return sorted(signals, key=lambda signal: signal.expected_margin, reverse=True)

    def skip_diagnostics(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        for name, config in self.strategies.items():
            if self._matches(config, snapshot):
                diagnostics.extend(self._strategy_skip_diagnostics(name, snapshot))
        return diagnostics

    def max_orders_per_tick(self, group_name: str = "conservative_btc_5m") -> int:
        group = self.strategy_groups.get(group_name, {})
        return int(group.get("max_orders_per_tick", 1))

    def has_strategy_scope(self, snapshot: MarketSnapshot) -> bool:
        return any(
            snapshot.asset in config.get("assets", []) and snapshot.timeframe in config.get("timeframes", [])
            for config in self.strategies.values()
        )

    def _matches(self, config: dict[str, Any], snapshot: MarketSnapshot) -> bool:
        group = self.strategy_groups.get(str(config.get("group", "")))
        return bool(
            config.get("enabled")
            and group
            and group.get("enabled")
            and snapshot.asset in config.get("assets", [])
            and snapshot.timeframe in config.get("timeframes", [])
        )

    def _evaluate_strategy(self, name: str, snapshot: MarketSnapshot, capital: float, momentum_pct: float) -> HedgeSignal | None:
        if name == "fee_aware_pair_arbitrage":
            return self._fee_aware_pair_arbitrage(snapshot, capital)
        if name == "late_window_discount_hedge":
            return self._late_window_discount_hedge(snapshot, capital)
        if name == "high_confidence_near_expiry_side":
            return self._high_confidence_near_expiry_side(snapshot, capital)
        return None

    def _strategy_skip_diagnostics(self, name: str, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        if name == "fee_aware_pair_arbitrage":
            return self._fee_aware_pair_arbitrage_skips(snapshot)
        if name == "late_window_discount_hedge":
            return self._late_window_discount_hedge_skips(snapshot)
        if name == "high_confidence_near_expiry_side":
            return self._high_confidence_near_expiry_side_skips(snapshot)
        return [{"strategy": name, "reason": "unknown_strategy", "requirement": "registered_strategy", "actual": name}]

    def _fee_aware_pair_arbitrage_skips(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        pair_cost = self._effective_pair_cost(snapshot)
        if pair_cost > 0.98:
            return [{"strategy": "fee_aware_pair_arbitrage", "reason": "pair_cost_too_high", "requirement": "effective_pair_cost<=0.980", "actual": f"{pair_cost:.3f}"}]
        if snapshot.yes_liquidity < 10.0:
            return [{"strategy": "fee_aware_pair_arbitrage", "reason": "yes_liquidity_too_low", "requirement": "yes_liquidity>=10.000", "actual": f"{snapshot.yes_liquidity:.3f}"}]
        if snapshot.no_liquidity < 10.0:
            return [{"strategy": "fee_aware_pair_arbitrage", "reason": "no_liquidity_too_low", "requirement": "no_liquidity>=10.000", "actual": f"{snapshot.no_liquidity:.3f}"}]
        return []

    def _late_window_discount_hedge_skips(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        seconds_left = self._seconds_left(snapshot)
        if seconds_left is None:
            return [{"strategy": "late_window_discount_hedge", "reason": "missing_end_date", "requirement": "seconds_left<=90.000", "actual": "missing"}]
        if seconds_left > 90:
            return [{"strategy": "late_window_discount_hedge", "reason": "too_early", "requirement": "seconds_left<=90.000", "actual": f"{seconds_left:.3f}"}]
        pair_cost = self._effective_pair_cost(snapshot)
        if pair_cost > 0.98:
            return [{"strategy": "late_window_discount_hedge", "reason": "pair_cost_too_high", "requirement": "effective_pair_cost<=0.980", "actual": f"{pair_cost:.3f}"}]
        cheapest = min(snapshot.yes_price, snapshot.no_price)
        if cheapest > 0.40:
            return [{"strategy": "late_window_discount_hedge", "reason": "discount_too_small", "requirement": "min_side_price<=0.400", "actual": f"{cheapest:.3f}"}]
        return []

    def _high_confidence_near_expiry_side_skips(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        seconds_left = self._seconds_left(snapshot)
        if seconds_left is None:
            return [{"strategy": "high_confidence_near_expiry_side", "reason": "missing_end_date", "requirement": "seconds_left<=75.000", "actual": "missing"}]
        if seconds_left > 75:
            return [{"strategy": "high_confidence_near_expiry_side", "reason": "too_early", "requirement": "seconds_left<=75.000", "actual": f"{seconds_left:.3f}"}]
        if snapshot.price_to_beat is None:
            return [{"strategy": "high_confidence_near_expiry_side", "reason": "missing_price_to_beat", "requirement": "price_to_beat exists", "actual": "missing"}]
        distance_pct = abs(snapshot.spot_price - snapshot.price_to_beat) / snapshot.price_to_beat * 100.0 if snapshot.price_to_beat else 0.0
        if distance_pct < 0.5:
            return [{"strategy": "high_confidence_near_expiry_side", "reason": "distance_too_small", "requirement": "distance_pct>=0.500", "actual": f"{distance_pct:.3f}"}]
        if snapshot.spot_price > snapshot.price_to_beat:
            if snapshot.yes_price > 0.80:
                return [{"strategy": "high_confidence_near_expiry_side", "reason": "yes_price_too_high", "requirement": "yes_price<=0.800", "actual": f"{snapshot.yes_price:.3f}"}]
            if snapshot.yes_liquidity < 10.0:
                return [{"strategy": "high_confidence_near_expiry_side", "reason": "yes_liquidity_too_low", "requirement": "yes_liquidity>=10.000", "actual": f"{snapshot.yes_liquidity:.3f}"}]
        if snapshot.spot_price < snapshot.price_to_beat:
            if snapshot.no_price > 0.80:
                return [{"strategy": "high_confidence_near_expiry_side", "reason": "no_price_too_high", "requirement": "no_price<=0.800", "actual": f"{snapshot.no_price:.3f}"}]
            if snapshot.no_liquidity < 10.0:
                return [{"strategy": "high_confidence_near_expiry_side", "reason": "no_liquidity_too_low", "requirement": "no_liquidity>=10.000", "actual": f"{snapshot.no_liquidity:.3f}"}]
        return []

    def _fee_aware_pair_arbitrage(self, snapshot: MarketSnapshot, capital: float) -> HedgeSignal | None:
        pair_cost = self._effective_pair_cost(snapshot)
        if pair_cost > 0.98 or snapshot.yes_liquidity < 10.0 or snapshot.no_liquidity < 10.0:
            return None
        size = min(capital / pair_cost, snapshot.yes_liquidity, snapshot.no_liquidity)
        return HedgeSignal(HedgeMode.COPYTRADE, size, size, 0.98 - pair_cost, ["fee-aware pair arbitrage"], target_side="BOTH")

    def _late_window_discount_hedge(self, snapshot: MarketSnapshot, capital: float) -> HedgeSignal | None:
        if self._seconds_left(snapshot) is None or self._seconds_left(snapshot) > 90:
            return None
        pair_cost = self._effective_pair_cost(snapshot)
        if pair_cost > 0.98 or min(snapshot.yes_price, snapshot.no_price) > 0.40:
            return None
        size = min(capital / pair_cost, snapshot.yes_liquidity, snapshot.no_liquidity)
        return HedgeSignal(HedgeMode.COPYTRADE, size, size, 0.98 - pair_cost, ["late-window discount hedge"], target_side="BOTH")

    def _high_confidence_near_expiry_side(self, snapshot: MarketSnapshot, capital: float) -> HedgeSignal | None:
        seconds_left = self._seconds_left(snapshot)
        if seconds_left is None or seconds_left > 75 or snapshot.price_to_beat is None:
            return None
        distance_pct = abs(snapshot.spot_price - snapshot.price_to_beat) / snapshot.price_to_beat * 100.0 if snapshot.price_to_beat else 0.0
        if distance_pct < 0.5:
            return None
        if snapshot.spot_price > snapshot.price_to_beat and snapshot.yes_price <= 0.80 and snapshot.yes_liquidity >= 10.0:
            return HedgeSignal(HedgeMode.HEDGE_BIASED_UP, capital / snapshot.yes_price, 0.0, distance_pct, ["high-confidence near-expiry side"], target_side="YES")
        if snapshot.spot_price < snapshot.price_to_beat and snapshot.no_price <= 0.80 and snapshot.no_liquidity >= 10.0:
            return HedgeSignal(HedgeMode.HEDGE_BIASED_DOWN, 0.0, capital / snapshot.no_price, distance_pct, ["high-confidence near-expiry side"], target_side="NO")
        return None

    @staticmethod
    def _effective_pair_cost(snapshot: MarketSnapshot) -> float:
        return snapshot.yes_price + snapshot.yes_price * 0.072 + snapshot.no_price + snapshot.no_price * 0.072

    @staticmethod
    def _seconds_left(snapshot: MarketSnapshot) -> float | None:
        if not snapshot.end_date:
            return None
        try:
            end = datetime.fromisoformat(snapshot.end_date.replace("Z", "+00:00"))
        except ValueError:
            return None
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - datetime.now(timezone.utc)).total_seconds())
