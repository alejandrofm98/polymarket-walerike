"""Grouped strategy evaluation for conservative crypto up/down markets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.config.runtime_config import normalize_strategies, normalize_strategy_groups
from bot.core.hedge_strategy import HedgeMode, HedgeSignal, MarketSnapshot
from bot.core.polymarket_client import POLYMARKET_MIN_ORDER_SIZE


CRYPTO_TAKER_FEE_RATE = 0.072
CONSERVATIVE_EDGE_MAX_SECONDS_LEFT = 90.0
CONSERVATIVE_EDGE_MIN_DISTANCE_PCT = 0.35
CONSERVATIVE_EDGE_MAKER_MIN_DISTANCE_PCT = 0.025
CONSERVATIVE_EDGE_MIN_MARGIN = 0.04
CONSERVATIVE_EDGE_MAKER_MIN_MARGIN = 0.03
CONSERVATIVE_EDGE_MAX_PRICE = 0.82
CONSERVATIVE_EDGE_MIN_LIQUIDITY = POLYMARKET_MIN_ORDER_SIZE
CONSERVATIVE_EDGE_MAKER_MIN_SECONDS_LEFT = 20.0


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
        if name == "conservative_oracle_edge":
            return self._conservative_oracle_edge(snapshot, capital)
        return None

    def _strategy_skip_diagnostics(self, name: str, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        if name == "fee_aware_pair_arbitrage":
            return self._fee_aware_pair_arbitrage_skips(snapshot)
        if name == "late_window_discount_hedge":
            return self._late_window_discount_hedge_skips(snapshot)
        if name == "high_confidence_near_expiry_side":
            return self._high_confidence_near_expiry_side_skips(snapshot)
        if name == "conservative_oracle_edge":
            return self._conservative_oracle_edge_skips(snapshot)
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

    def _conservative_oracle_edge_skips(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        setup = self._conservative_oracle_edge_setup(snapshot)
        if setup["reason"]:
            return [setup]
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

    def _conservative_oracle_edge(self, snapshot: MarketSnapshot, capital: float) -> HedgeSignal | None:
        setup = self._conservative_oracle_edge_setup(snapshot)
        if setup["reason"]:
            return None
        side = str(setup["side"])
        price = float(setup["price"])
        liquidity = float(setup["liquidity"])
        limit_price = float(setup.get("limit_price") or price)
        size = min(capital / limit_price, liquidity)
        order_type = str(setup.get("order_type") or "TAKER")
        post_only = bool(setup.get("post_only"))
        if side == "YES":
            return HedgeSignal(HedgeMode.HEDGE_BIASED_UP, size, 0.0, float(setup["margin"]), ["conservative oracle edge"], target_side="YES", order_type=order_type, post_only=post_only, limit_price=limit_price)
        return HedgeSignal(HedgeMode.HEDGE_BIASED_DOWN, 0.0, size, float(setup["margin"]), ["conservative oracle edge"], target_side="NO", order_type=order_type, post_only=post_only, limit_price=limit_price)

    def _conservative_oracle_edge_setup(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        seconds_left = self._seconds_left(snapshot)
        if seconds_left is None:
            return {"strategy": "conservative_oracle_edge", "reason": "missing_end_date", "requirement": "seconds_left<=90.000", "actual": "missing"}
        if seconds_left > CONSERVATIVE_EDGE_MAX_SECONDS_LEFT:
            return {"strategy": "conservative_oracle_edge", "reason": "too_early", "requirement": "seconds_left<=90.000", "actual": f"{seconds_left:.3f}"}
        if seconds_left < CONSERVATIVE_EDGE_MAKER_MIN_SECONDS_LEFT:
            return {"strategy": "conservative_oracle_edge", "reason": "maker_window_closed", "requirement": "seconds_left>=20.000", "actual": f"{seconds_left:.3f}"}
        if snapshot.price_to_beat is None or snapshot.price_to_beat <= 0:
            return {"strategy": "conservative_oracle_edge", "reason": "missing_price_to_beat", "requirement": "price_to_beat exists", "actual": "missing"}
        if snapshot.spot_price == snapshot.price_to_beat:
            return {"strategy": "conservative_oracle_edge", "reason": "distance_too_small", "requirement": "distance_pct>=0.025", "actual": "0.000"}

        distance_pct = abs(snapshot.spot_price - snapshot.price_to_beat) / snapshot.price_to_beat * 100.0
        if distance_pct < CONSERVATIVE_EDGE_MAKER_MIN_DISTANCE_PCT:
            return {"strategy": "conservative_oracle_edge", "reason": "distance_too_small", "requirement": "distance_pct>=0.025", "actual": f"{distance_pct:.3f}"}

        side = "YES" if snapshot.spot_price > snapshot.price_to_beat else "NO"
        price = snapshot.yes_price if side == "YES" else snapshot.no_price
        liquidity = snapshot.yes_liquidity if side == "YES" else snapshot.no_liquidity
        if liquidity < CONSERVATIVE_EDGE_MIN_LIQUIDITY:
            return {"strategy": "conservative_oracle_edge", "reason": "liquidity_too_low", "requirement": f"side_liquidity>={CONSERVATIVE_EDGE_MIN_LIQUIDITY:.3f}", "actual": f"{liquidity:.3f}"}
        if price > CONSERVATIVE_EDGE_MAX_PRICE:
            return {"strategy": "conservative_oracle_edge", "reason": "price_too_high", "requirement": "side_price<=0.820", "actual": f"{price:.3f}"}

        effective_price = price + self._fee_per_share(price)
        fair_value = min(0.96, 0.5 + (distance_pct / 2.0))
        margin = fair_value - effective_price
        if margin >= CONSERVATIVE_EDGE_MIN_MARGIN and distance_pct >= CONSERVATIVE_EDGE_MIN_DISTANCE_PCT:
            return {"strategy": "conservative_oracle_edge", "reason": "", "side": side, "price": price, "liquidity": liquidity, "margin": margin, "order_type": "TAKER", "post_only": False}

        maker_price = max(0.01, min(0.99, price - 0.01, fair_value - CONSERVATIVE_EDGE_MAKER_MIN_MARGIN))
        maker_margin = fair_value - maker_price
        if maker_margin >= CONSERVATIVE_EDGE_MAKER_MIN_MARGIN and maker_price < price:
            return {"strategy": "conservative_oracle_edge", "reason": "", "side": side, "price": price, "liquidity": liquidity, "margin": maker_margin, "order_type": "MAKER", "post_only": True, "limit_price": round(maker_price, 2)}
        if margin < CONSERVATIVE_EDGE_MIN_MARGIN:
            return {"strategy": "conservative_oracle_edge", "reason": "edge_after_fee_too_small", "requirement": "margin>=0.040", "actual": f"{margin:.3f}"}
        return {"strategy": "conservative_oracle_edge", "reason": "edge_after_fee_too_small", "requirement": "margin>=0.030", "actual": f"{maker_margin:.3f}"}

    @staticmethod
    def _effective_pair_cost(snapshot: MarketSnapshot) -> float:
        return (
            snapshot.yes_price
            + StrategyRegistry._fee_per_share(snapshot.yes_price)
            + snapshot.no_price
            + StrategyRegistry._fee_per_share(snapshot.no_price)
        )

    @staticmethod
    def _fee_per_share(price: float) -> float:
        return max(0.0, CRYPTO_TAKER_FEE_RATE * price * (1.0 - price))

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
