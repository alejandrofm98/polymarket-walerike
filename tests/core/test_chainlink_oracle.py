from __future__ import annotations

import time

import pytest

from bot.config.settings import Settings
from bot.core.chainlink_oracle import ChainlinkOracle


def test_manual_price_cache_works_without_web3() -> None:
    oracle = ChainlinkOracle(settings=Settings(chainlink_stale_seconds=10))

    price = oracle.set_manual_price("btc", 65000.0, updated_at=time.time())
    cached = oracle.get_cached_price("BTC")

    assert price.asset == "BTC"
    assert cached is not None
    assert cached.price == 65000.0
    assert cached.stale is False


def test_live_read_without_web3_or_rpc_has_clear_runtime_error() -> None:
    oracle = ChainlinkOracle(settings=Settings(chainlink_btc_usd_feed="0x0000000000000000000000000000000000000001"))

    with pytest.raises(RuntimeError, match="CHAINLINK_RPC_URL"):
        oracle.read_price("BTC", prefer_cache=False)
