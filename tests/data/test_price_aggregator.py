from __future__ import annotations

import pytest

from bot.core.binance_feed import PriceTick
from bot.data.price_aggregator import OraclePrice, PriceAggregator


def test_compare_computes_difference_and_alert() -> None:
    tick = PriceTick("BTC", "BTCUSDT", 101.0, 0.0, 0.0, 0.0, 10.0)
    oracle = OraclePrice("BTC", 100.0, 1, 9.0, False)

    comparison = PriceAggregator(discrepancy_pct=0.5).compare(tick, oracle)

    assert comparison.diff_abs == 1.0
    assert comparison.diff_pct == 1.0
    assert comparison.alert is True


def test_compare_rejects_asset_mismatch() -> None:
    tick = PriceTick("ETH", "ETHUSDT", 100.0, 0.0, 0.0, 0.0, 10.0)
    oracle = OraclePrice("BTC", 100.0, 1, 9.0, False)

    with pytest.raises(ValueError, match="assets"):
        PriceAggregator().compare(tick, oracle)
