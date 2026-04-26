from __future__ import annotations

import asyncio

from bot.web.server import _fetch_crypto_price_api_target, _fetch_historical_target_price, _scrape_target_price_from_html
from bot.web.websocket_server import WebSocketBroadcaster


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


class EmptyRTDSFeed:
    def price_at(self, _asset: str, _timestamp: float) -> None:
        return None


class CryptoPriceClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, str, str]] = []

    async def fetch_crypto_price(self, symbol: str, event_start_time: str, variant: str, end_date: str) -> dict[str, object]:
        self.calls.append((symbol, event_start_time, variant, end_date))
        return self.payload


class PastResultsClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, str]] = []

    async def fetch_past_results(self, symbol: str, current_event_start_time: str, end_date: str) -> dict[str, object]:
        self.calls.append((symbol, current_event_start_time, end_date))
        return self.payload


class Market:
    asset = "BTC"
    timeframe = "5m"
    window_start_timestamp = 1777223700


def test_broadcaster_sends_recent_buffer_on_connect() -> None:
    async def run() -> None:
        broadcaster = WebSocketBroadcaster(buffer_size=2)
        await broadcaster.publish("price", {"asset": "BTC", "price": 100})
        ws = FakeWebSocket()

        await broadcaster.connect(ws)
        await broadcaster.publish("status", {"ok": True})

        assert ws.accepted is True
        assert [event["type"] for event in ws.sent] == ["price", "status"]

    asyncio.run(run())


def test_broadcaster_removes_stale_connections() -> None:
    async def run() -> None:
        broadcaster = WebSocketBroadcaster()
        ws = FakeWebSocket(fail=True)
        await broadcaster.connect(ws)

        await broadcaster.publish("event", {})

        assert ws.closed is True
        assert ws not in broadcaster.active

    asyncio.run(run())


def test_historical_target_price_returns_none_when_no_feed_has_data() -> None:
    async def run() -> None:
        price, source = await _fetch_historical_target_price("BTC", 1777069800.0, EmptyRTDSFeed(), None)
        assert price is None
        assert source is None

    asyncio.run(run())


def test_crypto_price_api_target_uses_5m_window_params() -> None:
    async def run() -> None:
        client = CryptoPriceClient({"openPrice": 78030.02999197552})

        price, source = await _fetch_crypto_price_api_target(Market(), client)

        assert price == 78030.02999197552
        assert source == "polymarket_crypto_price_api"
        assert client.calls == [("BTC", "2026-04-26T17:15:00Z", "fiveminute", "2026-04-26T17:20:00Z")]

    asyncio.run(run())


def test_crypto_price_api_target_uses_15m_window_params() -> None:
    async def run() -> None:
        client = CryptoPriceClient({"openPrice": 78030.02999197552})
        market = Market()
        market.timeframe = "15m"

        price, source = await _fetch_crypto_price_api_target(market, client)

        assert price == 78030.02999197552
        assert source == "polymarket_crypto_price_api"
        assert client.calls == [("BTC", "2026-04-26T17:15:00Z", "fifteen", "2026-04-26T17:30:00Z")]

    asyncio.run(run())


def test_crypto_price_api_target_uses_1h_past_results_close_price() -> None:
    async def run() -> None:
        client = PastResultsClient({
            "status": "success",
            "data": {
                "results": [
                    {"startTime": "2026-04-26T15:00:00.000Z", "closePrice": 78049},
                    {"startTime": "2026-04-26T16:00:00.000Z", "closePrice": 77919.43},
                ]
            },
        })
        market = Market()
        market.timeframe = "1h"
        market.window_start_timestamp = 1777222800

        price, source = await _fetch_crypto_price_api_target(market, client)

        assert price == 77919.43
        assert source == "polymarket_past_results_api"
        assert client.calls == [("BTC", "2026-04-26T17:00:00Z", "2026-04-26T18:00:00Z")]

    asyncio.run(run())


def test_crypto_price_api_target_ignores_1h_missing_close_price() -> None:
    async def run() -> None:
        client = PastResultsClient({"data": {"results": [{"closePrice": None}]}})
        market = Market()
        market.timeframe = "1h"

        price, source = await _fetch_crypto_price_api_target(market, client)

        assert price is None
        assert source is None

    asyncio.run(run())


def test_scrape_extracts_price_from_next_data_json() -> None:
    html = '''<script id="__NEXT_DATA__">{"props":{"pageProps":{"market":{"openPrice":92345.67}}}}</script>'''
    price, source = _scrape_target_price_from_html(html, "btc-updown-5m-123")
    assert price == 92345.67
    assert source == "polymarket_page_scrape"


def test_scrape_ignores_plain_html_without_strict_anchor() -> None:
    html = '<html><body>Bitcoin price at $92,345.67 on Polymarket</body></html>'
    price, source = _scrape_target_price_from_html(html, "btc-updown-5m-123")
    assert price is None
    assert source is None


def test_scrape_extracts_open_price_from_raw_json() -> None:
    html = '''<script>window.__NEXT_DATA__ = {"props":{"pageProps":{"openPrice":77652.81}}}</script>'''
    price, source = _scrape_target_price_from_html(html, "btc-updown-5m-123")
    assert price == 77652.81
    assert source == "polymarket_page_scrape"


def test_scrape_returns_none_on_empty_html() -> None:
    price, source = _scrape_target_price_from_html(None, "btc-updown-5m-123")
    assert price is None
    assert source is None
    price, source = _scrape_target_price_from_html("", "btc-updown-5m-123")
    assert price is None
    assert source is None


def test_scrape_returns_none_when_no_price_found() -> None:
    html = '<html><body>No price here</body></html>'
    price, source = _scrape_target_price_from_html(html, "btc-updown-5m-123")
    assert price is None
    assert source is None
