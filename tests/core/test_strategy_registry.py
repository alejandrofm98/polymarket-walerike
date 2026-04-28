from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from bot.core.hedge_strategy import MarketSnapshot
from bot.core.strategy_registry import StrategyRegistry


def snapshot(**overrides: object) -> MarketSnapshot:
    values = {
        "market_id": "btc-5m",
        "asset": "BTC",
        "timeframe": "5m",
        "yes_token_id": "up-token",
        "no_token_id": "down-token",
        "yes_price": 0.45,
        "no_price": 0.45,
        "yes_liquidity": 100.0,
        "no_liquidity": 100.0,
        "spot_price": 101.0,
        "oracle_price": 101.0,
        "timestamp": time.time(),
        "market_slug": "btc-updown-5m-test",
        "end_date": (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat(),
        "price_to_beat": 100.0,
        "window_start_timestamp": int(time.time()) - 240,
    }
    values.update(overrides)
    return MarketSnapshot(**values)  # type: ignore[arg-type]


def test_registry_filters_disabled_group() -> None:
    registry = StrategyRegistry(
        strategy_groups={"conservative_btc_5m": {"enabled": False, "max_orders_per_tick": 2, "capital_fraction": 1.0}},
        strategies={"fee_aware_pair_arbitrage": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]}},
    )

    assert registry.evaluate(snapshot(), capital_per_trade=10.0, momentum_pct=0.0) == []


def test_fee_aware_pair_arbitrage_emits_both_sides_when_pair_is_cheap() -> None:
    registry = StrategyRegistry()

    signals = registry.evaluate(snapshot(), capital_per_trade=10.0, momentum_pct=0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "BOTH"
    assert signals[0].yes_size > 0
    assert signals[0].no_size > 0
    assert "fee-aware pair arbitrage" in signals[0].reasons


def test_late_window_discount_hedge_requires_near_expiry_and_discount() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "late_window_discount_hedge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    early = registry.evaluate(snapshot(end_date=(datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat()), 10.0, 0.0)
    late = registry.evaluate(snapshot(yes_price=0.38, no_price=0.50), 10.0, 0.0)

    assert early == []
    assert len(late) == 1
    assert late[0].target_side == "BOTH"
    assert "late-window discount hedge" in late[0].reasons


def test_high_confidence_near_expiry_side_buys_directional_edge() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "high_confidence_near_expiry_side": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=102.0, oracle_price=102.0, price_to_beat=100.0, yes_price=0.72, no_price=0.25), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "YES"
    assert signals[0].yes_size > 0
    assert signals[0].no_size == 0.0
    assert "high-confidence near-expiry side" in signals[0].reasons
