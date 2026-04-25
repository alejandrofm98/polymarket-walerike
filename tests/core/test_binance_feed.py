from __future__ import annotations

from bot.core.binance_feed import BinanceTickerFeed


def test_parse_update_stores_latest_and_history_without_network() -> None:
    feed = BinanceTickerFeed(history_limit=2)

    tick = feed.parse_update({"data": {"s": "BTCUSDT", "c": "100.0", "p": "5", "P": "5", "v": "10", "E": 1000}})
    feed.parse_update({"s": "BTCUSDT", "c": "110.0", "p": "10", "P": "10", "v": "11", "E": 2000})
    feed.parse_update({"s": "BTCUSDT", "c": "121.0", "p": "21", "P": "21", "v": "12", "E": 3000})

    assert tick is not None
    assert feed.latest["BTC"].price == 121.0
    assert len(feed.history["BTC"]) == 2
    assert feed.momentum_pct("BTC", window_count=1) == 10.0


def test_agg_trade_stream_and_payload_update_price() -> None:
    feed = BinanceTickerFeed(symbols={"BTC": "btcusdt"})

    tick = feed.parse_update({"data": {"e": "aggTrade", "s": "BTCUSDT", "p": "123.45", "T": 2500}})

    assert "btcusdt@aggTrade" in feed.url
    assert tick is not None
    assert tick.price == 123.45
    assert tick.timestamp == 2.5
    assert feed.latest["BTC"].price == 123.45


def test_malformed_or_unknown_messages_do_not_crash() -> None:
    feed = BinanceTickerFeed()

    assert feed.parse_update("not-json") is None
    assert feed.parse_update({"s": "DOGEUSDT", "c": "1"}) is None
    assert feed.latest == {}
