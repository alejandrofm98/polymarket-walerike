"""Pure price aggregation helpers for exchange and oracle feeds."""

from __future__ import annotations

from dataclasses import dataclass

from bot.core.binance_feed import PriceTick


@dataclass(slots=True)
class OraclePrice:
    asset: str
    price: float
    round_id: int | None
    updated_at: float
    stale: bool


@dataclass(slots=True)
class PriceComparison:
    asset: str
    binance_price: float
    oracle_price: float
    diff_abs: float
    diff_pct: float
    alert: bool
    binance_timestamp: float
    oracle_updated_at: float
    oracle_stale: bool


class PriceAggregator:
    def __init__(self, discrepancy_pct: float = 0.5) -> None:
        if discrepancy_pct < 0:
            raise ValueError("discrepancy_pct must be >= 0")
        self.discrepancy_pct = discrepancy_pct

    def compare(self, tick: PriceTick, oracle: OraclePrice) -> PriceComparison:
        if tick.asset.upper() != oracle.asset.upper():
            raise ValueError("tick and oracle assets must match")
        diff_abs = tick.price - oracle.price
        diff_pct = (diff_abs / oracle.price) * 100.0 if oracle.price else 0.0
        return PriceComparison(
            asset=tick.asset.upper(),
            binance_price=tick.price,
            oracle_price=oracle.price,
            diff_abs=diff_abs,
            diff_pct=diff_pct,
            alert=abs(diff_pct) >= self.discrepancy_pct or oracle.stale,
            binance_timestamp=tick.timestamp,
            oracle_updated_at=oracle.updated_at,
            oracle_stale=oracle.stale,
        )

    def compare_latest(
        self,
        ticks: dict[str, PriceTick],
        oracles: dict[str, OraclePrice],
    ) -> dict[str, PriceComparison]:
        comparisons: dict[str, PriceComparison] = {}
        for asset, tick in ticks.items():
            oracle = oracles.get(asset.upper()) or oracles.get(asset)
            if oracle is None:
                continue
            comparisons[asset.upper()] = self.compare(tick, oracle)
        return comparisons
