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
            "email_loss_alert_pct": 10,
            "solo_log": True,
        }
    )

    assert config.capital_per_trade == 25.0
    assert config.min_margin_for_arbitrage == 0.05
    assert config.enabled_markets == {"BTC": ["5m", "1h"], "ETH": ["15m"]}
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


def test_runtime_config_defaults_strategy_groups(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")

    config = store.load()

    assert config.strategy_groups["conservative_btc_5m"]["enabled"] is True
    assert config.strategy_groups["conservative_btc_5m"]["max_orders_per_tick"] == 2
    assert config.strategies["fee_aware_pair_arbitrage"]["enabled"] is True
    assert config.strategies["late_window_discount_hedge"]["enabled"] is False
    assert config.strategies["high_confidence_near_expiry_side"]["enabled"] is False
    assert config.strategies["conservative_oracle_edge"] == {
        "enabled": False,
        "group": "conservative_btc_5m",
        "assets": ["BTC"],
        "timeframes": ["5m"],
    }


def test_runtime_config_validates_strategy_shapes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")

    config = store.update(
        {
            "strategy_groups": {"conservative_btc_5m": {"enabled": False, "max_orders_per_tick": 1, "capital_fraction": 0.5}},
            "strategies": {
                "fee_aware_pair_arbitrage": {
                    "enabled": True,
                    "group": "conservative_btc_5m",
                    "assets": ["btc"],
                    "timeframes": ["5M"],
                }
            },
        }
    )

    assert config.strategy_groups["conservative_btc_5m"]["enabled"] is False
    assert config.strategy_groups["conservative_btc_5m"]["capital_fraction"] == 0.5
    assert config.strategies["fee_aware_pair_arbitrage"]["assets"] == ["BTC"]
    assert config.strategies["fee_aware_pair_arbitrage"]["timeframes"] == ["5m"]

    with pytest.raises(ValueError, match="strategy_groups"):
        store.update({"strategy_groups": []})

    with pytest.raises(ValueError, match="group"):
        store.update({"strategies": {"fee_aware_pair_arbitrage": {"group": "missing"}}})
