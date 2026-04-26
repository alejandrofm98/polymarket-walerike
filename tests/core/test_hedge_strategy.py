from __future__ import annotations

from bot.core.hedge_strategy import HedgeMode, HedgeStrategy, MarketSnapshot


def _snapshot(**overrides: object) -> MarketSnapshot:
    values = {
        "market_id": "m1",
        "asset": "BTC",
        "timeframe": "15m",
        "yes_token_id": "yes",
        "no_token_id": "no",
        "yes_price": 0.45,
        "no_price": 0.50,
        "yes_liquidity": 1000.0,
        "no_liquidity": 1000.0,
        "spot_price": 65000.0,
        "oracle_price": 65000.0,
        "timestamp": 1.0,
    }
    values.update(overrides)
    return MarketSnapshot(**values)


def test_copytrade_tracks_entry_then_buys_on_reversal() -> None:
    strategy = HedgeStrategy()
    first = strategy.evaluate(_snapshot(yes_price=0.45), capital_per_trade=95.0, momentum_pct=0.0)
    signal = strategy.evaluate(_snapshot(yes_price=0.48), capital_per_trade=95.0, momentum_pct=0.0)

    assert first.mode is HedgeMode.COPYTRADE
    assert first.yes_size == 0
    assert "tracking YES below entry threshold" in first.reasons
    assert signal.mode is HedgeMode.COPYTRADE
    assert signal.yes_size > 0
    assert signal.no_size == 0
    assert "reversal trigger" in signal.reasons


def test_copytrade_reports_soft_checks_without_momentum_hedge() -> None:
    signal = HedgeStrategy().evaluate(
        _snapshot(yes_price=0.55, no_price=0.46, yes_liquidity=10.0, spot_price=67000.0),
        capital_per_trade=100.0,
        momentum_pct=0.5,
    )

    assert signal.mode is HedgeMode.COPYTRADE
    assert signal.yes_size == 0.0
    assert signal.no_size == 0.0
    assert "tracking NO below entry threshold" in signal.reasons
    assert "liquidity below threshold" in signal.reasons
    assert "oracle discrepancy above threshold" in signal.reasons


def test_copytrade_sum_avg_guard_includes_crypto_taker_fees() -> None:
    strategy = HedgeStrategy()
    snapshot = _snapshot(yes_price=0.56, no_price=0.49)
    strategy.record_buy(snapshot, "NO", 0.49, 5.0)

    signal = strategy.evaluate(snapshot, capital_per_trade=100.0, momentum_pct=0.0)

    assert signal.yes_size == 0.0
    assert signal.no_size == 0.0
    assert any("includes_fee" in reason for reason in signal.reasons)
