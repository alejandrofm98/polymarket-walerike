from __future__ import annotations

from bot.config.settings import Settings
from bot.core.polymarket_rtds_feed import PolymarketRTDSFeed
from main import create_price_feed


def test_chainlink_topic_update_stores_latest_and_history() -> None:
    feed = PolymarketRTDSFeed(assets=["BTC"], history_limit=2)

    tick = feed.parse_update(
        {
            "topic": "crypto_prices_chainlink",
            "payload": {"symbol": "btc/usd", "value": "65000.5", "timestamp": 1000},
        }
    )

    assert feed.topic == "crypto_prices_chainlink"
    assert tick is not None
    assert tick.price == 65000.5
    assert tick.timestamp == 1.0
    assert feed.latest["BTC"].price == 65000.5
    assert len(feed.history["BTC"]) == 1


def test_binance_topic_remains_supported_for_compatibility() -> None:
    feed = PolymarketRTDSFeed(assets=["ETH"], topic="crypto_prices")

    tick = feed.parse_update(
        {
            "topic": "crypto_prices",
            "payload": {"symbol": "eth/usd", "value": "3200", "timestamp": 2000},
        }
    )

    assert feed.topic == "crypto_prices"
    assert tick is not None
    assert feed.latest["ETH"].price == 3200.0


def test_create_price_feed_defaults_to_chainlink_topic() -> None:
    feed = create_price_feed(Settings())

    assert isinstance(feed, PolymarketRTDSFeed)
    assert feed.topic == "crypto_prices_chainlink"


def test_create_price_feed_can_use_non_chainlink_rtds_topic() -> None:
    feed = create_price_feed(Settings(price_feed_source="polymarket_rtds"))

    assert isinstance(feed, PolymarketRTDSFeed)
    assert feed.topic == "crypto_prices"
