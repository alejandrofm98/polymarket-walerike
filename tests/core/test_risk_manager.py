from __future__ import annotations

from bot.core.hedge_strategy import HedgeMode
from bot.core.risk_manager import AccountRiskState, RiskConfig, RiskManager


def test_allows_trade_with_size_adjustment_only() -> None:
    manager = RiskManager(RiskConfig(max_position_per_market=100, max_total_exposure=150))
    state = AccountRiskState(balance=200, total_exposure=80, positions_by_market={"m1": 40})

    decision = manager.check_trade(
        market_id="m1",
        asset="BTC",
        yes_price=0.45,
        no_price=0.50,
        requested_size=80,
        state=state,
    )

    assert decision.allowed is True
    assert decision.adjusted_size == 60
    assert "size adjusted for max position per market" in decision.reasons


def test_blocks_core_risk_failures() -> None:
    manager = RiskManager(RiskConfig(same_asset_cooldown_seconds=10))
    state = AccountRiskState(
        balance=10,
        total_exposure=0,
        daily_pnl=-100,
        open_trade_keys={"BTC:m1"},
        last_trade_ts_by_asset={"BTC": 95},
    )

    decision = manager.check_trade(
        market_id="m1",
        asset="BTC",
        yes_price=0.51,
        no_price=0.49,
        requested_size=20,
        state=state,
        oracle_discrepancy_pct=2.0,
        slippage_pct=3.0,
        trade_key="BTC:m1",
        now=100,
    )

    assert decision.allowed is False
    assert "spread not below threshold (default)" in decision.reasons
    assert "oracle discrepancy above no-trade threshold" in decision.reasons
    assert "slippage above limit" in decision.reasons
    assert "balance insufficient" in decision.reasons
    assert "duplicate trade" in decision.reasons
    assert "same asset cooldown active" in decision.reasons


def test_hedge_mode_allowed_when_spread_valid() -> None:
    manager = RiskManager(RiskConfig(min_yes_no_sum=0.98, hedge_max_yes_no_sum=2.0))
    state = AccountRiskState(balance=100, total_exposure=0)

    decision = manager.check_trade(
        market_id="m1",
        asset="BTC",
        yes_price=0.65,
        no_price=0.35,
        requested_size=10,
        state=state,
        signal_mode=HedgeMode.HEDGE_NEUTRAL,
    )

    assert decision.allowed is True
    assert "hedge spread too tight - no margin" not in decision.reasons


def test_hedge_mode_blocked_when_spread_too_tight() -> None:
    manager = RiskManager(RiskConfig(min_yes_no_sum=0.98, hedge_max_yes_no_sum=2.0))
    state = AccountRiskState(balance=100, total_exposure=0)

    decision = manager.check_trade(
        market_id="m1",
        asset="BTC",
        yes_price=0.52,
        no_price=0.45,
        requested_size=10,
        state=state,
        signal_mode=HedgeMode.HEDGE_NEUTRAL,
    )

    assert decision.allowed is False
    assert "hedge spread too tight - no margin" in decision.reasons


def test_arbitrage_blocked_when_not_below_threshold() -> None:
    manager = RiskManager(RiskConfig(min_yes_no_sum=0.98))
    state = AccountRiskState(balance=100, total_exposure=0)

    decision = manager.check_trade(
        market_id="m1",
        asset="BTC",
        yes_price=0.60,
        no_price=0.45,
        requested_size=10,
        state=state,
        signal_mode=HedgeMode.ARBITRAGE,
    )

    assert decision.allowed is False
    assert "arbitrage spread not below threshold" in decision.reasons
