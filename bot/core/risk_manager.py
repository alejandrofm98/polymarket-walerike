"""Pure risk checks for hedge decisions before order execution."""

from __future__ import annotations

import time
from bot.core.hedge_strategy import HedgeMode

from dataclasses import dataclass, field


@dataclass(slots=True)
class RiskConfig:
    max_position_per_market: float = 100.0
    max_total_exposure: float = 500.0
    daily_drawdown_limit: float = 100.0
    max_oracle_discrepancy_pct: float = 1.0
    max_slippage_pct: float = 2.0
    same_asset_cooldown_seconds: float = 10.0
    min_yes_no_sum: float = 0.98
    hedge_min_yes_no_sum: float = 1.95
    hedge_allowed_margin: float = 0.02
    hedge_max_yes_no_sum: float = 2.0


@dataclass(slots=True)
class AccountRiskState:
    balance: float
    total_exposure: float = 0.0
    daily_pnl: float = 0.0
    positions_by_market: dict[str, float] = field(default_factory=dict)
    open_trade_keys: set[str] = field(default_factory=set)
    last_trade_ts_by_asset: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    adjusted_size: float | None = None


class RiskManager:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def check_trade(
        self,
        *,
        market_id: str,
        asset: str,
        yes_price: float,
        no_price: float,
        requested_size: float,
        state: AccountRiskState,
        oracle_discrepancy_pct: float = 0.0,
        slippage_pct: float = 0.0,
        trade_key: str | None = None,
        now: float | None = None,
        signal_mode: HedgeMode | None = None,
    ) -> RiskDecision:
        now = now or time.time()
        reasons: list[str] = []
        adjusted_size = max(0.0, requested_size)
        current_position = state.positions_by_market.get(market_id, 0.0)
        remaining_market = self.config.max_position_per_market - current_position
        remaining_total = self.config.max_total_exposure - state.total_exposure
        adjusted_size = min(adjusted_size, remaining_market, remaining_total, state.balance)

        if requested_size <= 0:
            reasons.append("requested size must be positive")
        if current_position >= self.config.max_position_per_market:
            reasons.append("max position per market reached")
        elif requested_size > remaining_market:
            reasons.append("size adjusted for max position per market")
        if state.total_exposure >= self.config.max_total_exposure:
            reasons.append("max total exposure reached")
        elif requested_size > remaining_total:
            reasons.append("size adjusted for max total exposure")
        if state.daily_pnl <= -abs(self.config.daily_drawdown_limit):
            reasons.append("daily drawdown stop reached")
        yes_no_sum = yes_price + no_price
        if signal_mode is HedgeMode.COPYTRADE:
            pass
        elif signal_mode is HedgeMode.ARBITRAGE:
            if yes_no_sum >= self.config.min_yes_no_sum:
                reasons.append("arbitrage spread not below threshold")
        elif signal_mode is not None and signal_mode.name.startswith("HEDGE"):
            if yes_no_sum < self.config.min_yes_no_sum:
                reasons.append("hedge spread too tight - no margin")
            elif yes_no_sum > self.config.hedge_max_yes_no_sum:
                reasons.append("hedge spread exceed max (invalid)")
        else:
            if yes_no_sum >= self.config.min_yes_no_sum:
                reasons.append("spread not below threshold (default)")
        if oracle_discrepancy_pct > self.config.max_oracle_discrepancy_pct:
            reasons.append("oracle discrepancy above no-trade threshold")
        if slippage_pct > self.config.max_slippage_pct:
            reasons.append("slippage above limit")
        if state.balance < requested_size:
            reasons.append("balance insufficient")
        if adjusted_size <= 0:
            reasons.append("no risk capacity remaining")
        if signal_mode is not HedgeMode.COPYTRADE and trade_key and trade_key in state.open_trade_keys:
            reasons.append("duplicate trade")
        last_trade_ts = state.last_trade_ts_by_asset.get(asset.upper())
        if signal_mode is not HedgeMode.COPYTRADE and last_trade_ts is not None and (now - last_trade_ts) < self.config.same_asset_cooldown_seconds:
            reasons.append("same asset cooldown active")

        blocking = [reason for reason in reasons if not reason.startswith("size adjusted")]
        return RiskDecision(allowed=not blocking, reasons=reasons, adjusted_size=adjusted_size)
