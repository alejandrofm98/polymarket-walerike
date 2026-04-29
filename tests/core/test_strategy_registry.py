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


def test_fee_aware_pair_arbitrage_uses_outcome_fee_curve() -> None:
    registry = StrategyRegistry()

    signals = registry.evaluate(snapshot(yes_price=0.47, no_price=0.47), capital_per_trade=10.0, momentum_pct=0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "BOTH"
    assert signals[0].expected_margin > 0.0


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


def test_late_window_discount_hedge_uses_outcome_fee_curve() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "late_window_discount_hedge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(yes_price=0.39, no_price=0.55), capital_per_trade=10.0, momentum_pct=0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "BOTH"
    assert signals[0].expected_margin > 0.0


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


def test_conservative_oracle_edge_buys_yes_when_spot_is_safely_above_strike() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.70, no_price=0.34), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "YES"
    assert signals[0].yes_size > 0
    assert signals[0].no_size == 0.0
    assert signals[0].expected_margin > 0.0
    assert "conservative oracle edge" in signals[0].reasons


def test_conservative_oracle_edge_buys_no_when_spot_is_safely_below_strike() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=99.40, oracle_price=99.40, price_to_beat=100.0, yes_price=0.34, no_price=0.70), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "NO"
    assert signals[0].yes_size == 0.0
    assert signals[0].no_size > 0
    assert signals[0].expected_margin > 0.0
    assert "conservative oracle edge" in signals[0].reasons


def test_conservative_oracle_edge_skips_when_distance_is_too_small() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.01, oracle_price=100.01, price_to_beat=100.0, yes_price=0.55), 10.0, 0.0)
    diagnostics = registry.skip_diagnostics(snapshot(spot_price=100.01, oracle_price=100.01, price_to_beat=100.0, yes_price=0.55))

    assert signals == []
    assert diagnostics == [
        {
            "strategy": "conservative_oracle_edge",
            "reason": "distance_too_small",
            "requirement": "distance_pct>=0.025",
            "actual": "0.010",
        }
    ]


def test_conservative_oracle_edge_skips_when_price_is_too_high() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.83), 10.0, 0.0)
    diagnostics = registry.skip_diagnostics(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.83))

    assert signals == []
    assert diagnostics[0]["reason"] == "price_too_high"


def test_conservative_oracle_edge_allows_liquidity_at_order_minimum() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.70, yes_liquidity=7.0), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "YES"
    assert signals[0].yes_size == 7.0


def test_conservative_oracle_edge_skips_liquidity_below_order_minimum() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.70, yes_liquidity=4.0), 10.0, 0.0)
    diagnostics = registry.skip_diagnostics(snapshot(spot_price=100.60, oracle_price=100.60, price_to_beat=100.0, yes_price=0.70, yes_liquidity=4.0))

    assert signals == []
    assert diagnostics == [
        {
            "strategy": "conservative_oracle_edge",
            "reason": "liquidity_too_low",
            "requirement": "side_liquidity>=5.000",
            "actual": "4.000",
        }
    ]


def test_conservative_oracle_edge_emits_post_only_maker_signal_for_medium_edge() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.30, oracle_price=100.30, price_to_beat=100.0, yes_price=0.60, no_price=0.44), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "YES"
    assert signals[0].yes_size > 0
    assert signals[0].no_size == 0.0
    assert signals[0].order_type == "MAKER"
    assert signals[0].post_only is True
    assert signals[0].limit_price == 0.59


def test_conservative_oracle_edge_emits_post_only_maker_signal_for_small_live_edge() -> None:
    registry = StrategyRegistry(
        strategies={
            "fee_aware_pair_arbitrage": {"enabled": False, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
            "conservative_oracle_edge": {"enabled": True, "group": "conservative_btc_5m", "assets": ["BTC"], "timeframes": ["5m"]},
        }
    )

    signals = registry.evaluate(snapshot(spot_price=100.025, oracle_price=100.025, price_to_beat=100.0, yes_price=0.50, no_price=0.53), 10.0, 0.0)

    assert len(signals) == 1
    assert signals[0].target_side == "YES"
    assert signals[0].order_type == "MAKER"
    assert signals[0].post_only is True
    assert signals[0].limit_price == 0.48
