from __future__ import annotations

import pytest

from bot.config.runtime_config import RuntimeConfigStore


def test_runtime_config_persists_valid_updates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")

    config = store.update(
        {
            "capital_per_trade": "25",
            "min_margin_for_arbitrage": 0.05,
            "enabled_markets": {"btc": ["5M", "1h"], "ETH": ["15m"]},
            "explicit_slugs": ["https://polymarket.com/es/event/btc-updown-5m-1777069800"],
            "email_loss_alert_pct": 10,
            "solo_log": True,
        }
    )

    assert config.capital_per_trade == 25.0
    assert config.min_margin_for_arbitrage == 0.05
    assert config.enabled_markets == {"BTC": ["5m", "1h"], "ETH": ["15m"]}
    assert config.explicit_slugs == ["btc-updown-5m-1777069800"]
    assert store.load().solo_log is True


def test_runtime_config_converts_old_enabled_markets_list(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")

    config = store.update({"enabled_markets": ["btc", "ETH"]})

    assert config.enabled_markets == {"BTC": ["5m", "15m", "1h"], "ETH": ["5m", "15m", "1h"]}


def test_runtime_config_rejects_bad_ranges(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")

    with pytest.raises(ValueError, match="capital_per_trade"):
        store.update({"capital_per_trade": 0})

    with pytest.raises(ValueError, match="min_margin_for_arbitrage"):
        store.update({"min_margin_for_arbitrage": 2})

    with pytest.raises(ValueError, match="asset"):
        store.update({"enabled_markets": {"DOGE": ["5m"]}})

    with pytest.raises(ValueError, match="timeframe"):
        store.update({"enabled_markets": {"BTC": ["4h"]}})
