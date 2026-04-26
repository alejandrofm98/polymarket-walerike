from __future__ import annotations

import asyncio
import json
import time

import pytest

from bot.config.settings import Settings
import bot.core.polymarket_client as polymarket_client_module
from bot.core.polymarket_client import OrderRequest, OrderSide, OrderType, PolymarketClient


def _request(**overrides: object) -> OrderRequest:
    values = {
        "market": "condition-1",
        "asset_id": "token-1",
        "side": OrderSide.BUY,
        "price": 0.5,
        "size": 1.0,
        "order_type": OrderType.GTD,
        "expiration": int(time.time()) + 60,
    }
    values.update(overrides)
    return OrderRequest(**values)


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"price": 0.0}, "price"),
        ({"price": 1.0}, "price"),
        ({"size": 0.99}, "size"),
        ({"expiration": None}, "GTD"),
        ({"expiration": int(time.time()) - 1}, "future"),
    ],
)
def test_validation_rejects_bad_price_size_and_gtd(overrides: dict[str, object], error: str) -> None:
    client = PolymarketClient(paper_mode=True)

    with pytest.raises(ValueError, match=error):
        client._validate_order(_request(**overrides))


def test_paper_order_and_cancel_never_touch_live_sdk() -> None:
    async def run() -> None:
        client = PolymarketClient(paper_mode=True)

        def fail_build() -> object:
            raise AssertionError("paper mode must not build live SDK client")

        client._build_clob_client = fail_build  # type: ignore[method-assign]
        await client.connect()
        order = await client.place_order(_request())

        assert order.order_id.startswith("paper-")
        assert order.raw["paper"] is True
        assert await client.cancel_order(order.order_id) is True
        assert await client.cancel_order(order.order_id) is False

    asyncio.run(run())


def test_live_trading_guard_blocks_sdk_import_before_configured() -> None:
    async def run() -> None:
        settings = Settings(paper_mode=False, live_trading=False)
        client = PolymarketClient(settings=settings, paper_mode=False)

        def fail_build() -> object:
            raise AssertionError("guard must block before SDK build")

        client._build_clob_client = fail_build  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="POLYMARKET_LIVE_TRADING"):
            await client.connect()

        with pytest.raises(RuntimeError, match="POLYMARKET_LIVE_TRADING"):
            await client.place_order(_request())

        with pytest.raises(RuntimeError, match="POLYMARKET_LIVE_TRADING"):
            await client.cancel_order("order-1")

    asyncio.run(run())


def test_live_connect_missing_sdk_reports_clear_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def missing_module(name: str) -> object:
        if name.startswith("py_clob_client"):
            raise ImportError(name)
        raise AssertionError(name)

    monkeypatch.setattr(polymarket_client_module.importlib, "import_module", missing_module)

    async def run() -> None:
        settings = Settings(paper_mode=False, live_trading=True)
        client = PolymarketClient(settings=settings, paper_mode=False)

        with pytest.raises(RuntimeError, match="py-clob-client"):
            await client.connect()

    asyncio.run(run())


def test_websocket_payload_builders_and_urls() -> None:
    settings = Settings(api_key="key")
    client = PolymarketClient(settings=settings, paper_mode=True)

    assert client.build_market_subscribe_payload(["token-a", "token-b"]) == {
        "type": "market",
        "assets_ids": ["token-a", "token-b"],
    }
    assert client.build_user_subscribe_payload(["condition-a"]) == {"type": "user", "markets": ["condition-a"], "auth": {"apiKey": "key"}}
    assert client._ws_url("market") == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    assert client._ws_url("user") == "wss://ws-subscriptions-clob.polymarket.com/ws/user"


def test_live_positions_use_data_api_not_sdk_positions() -> None:
    async def run() -> None:
        settings = Settings(paper_mode=False, funder="0xfunder")
        client = PolymarketClient(settings=settings, paper_mode=False)
        client._clob_client = object()

        def fail_build() -> object:
            raise AssertionError("positions must not build or query py-clob-client")

        def fake_fetch(funder: str) -> list[dict[str, str]]:
            assert funder == "0xfunder"
            return [{"asset": "token-a"}]

        client._build_clob_client = fail_build  # type: ignore[method-assign]
        client._fetch_positions = fake_fetch  # type: ignore[method-assign]

        assert await client.get_positions() == [{"asset": "token-a"}]

    asyncio.run(run())


def test_gamma_fetch_builds_public_urls_in_paper_mode(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        seen_urls: list[str] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"ok": True}).encode()

        def fake_urlopen(url: object, timeout: int) -> FakeResponse:
            seen_urls.append(str(getattr(url, "full_url", url)))
            assert timeout == 15
            return FakeResponse()

        monkeypatch.setattr(polymarket_client_module.urllib.request, "urlopen", fake_urlopen)
        settings = Settings(paper_mode=True, polymarket_gamma_api_url="https://gamma.example")
        client = PolymarketClient(settings=settings, paper_mode=True)

        assert await client.fetch_event_by_slug("https://polymarket.com/es/event/btc-updown-5m-1777069800") == {"ok": True}
        assert await client.fetch_market_by_slug("btc-updown-5m-1777069800") == {"ok": True}
        assert await client.fetch_events({"q": "BTC updown 5m", "active": "true", "closed": "false", "limit": 20}) == {"ok": True}

        assert seen_urls[0] == "https://gamma.example/events/slug/btc-updown-5m-1777069800"
        assert seen_urls[1] == "https://gamma.example/markets/slug/btc-updown-5m-1777069800"
        assert seen_urls[2].startswith("https://gamma.example/events?")
        assert "q=BTC+updown+5m" in seen_urls[2]
        assert "active=true" in seen_urls[2]
        assert "closed=false" in seen_urls[2]

    asyncio.run(run())


def test_crypto_price_fetch_builds_polymarket_web_api_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        seen_urls: list[str] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"openPrice": 78030.02999197552}).encode()

        def fake_urlopen(url: object, timeout: int) -> FakeResponse:
            seen_urls.append(str(getattr(url, "full_url", url)))
            assert timeout == 15
            return FakeResponse()

        monkeypatch.setattr(polymarket_client_module.urllib.request, "urlopen", fake_urlopen)
        client = PolymarketClient(settings=Settings(paper_mode=True), paper_mode=True)

        assert await client.fetch_crypto_price("btc", "2026-04-26T17:15:00Z", "fiveminute", "2026-04-26T17:20:00Z") == {"openPrice": 78030.02999197552}
        assert seen_urls == [
            "https://polymarket.com/api/crypto/crypto-price?symbol=BTC&eventStartTime=2026-04-26T17%3A15%3A00Z&variant=fiveminute&endDate=2026-04-26T17%3A20%3A00Z"
        ]

    asyncio.run(run())


def test_past_results_fetch_builds_polymarket_web_api_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        seen_urls: list[str] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"data": {"results": [{"closePrice": 77919.43}]}}).encode()

        def fake_urlopen(url: object, timeout: int) -> FakeResponse:
            seen_urls.append(str(getattr(url, "full_url", url)))
            assert timeout == 15
            return FakeResponse()

        monkeypatch.setattr(polymarket_client_module.urllib.request, "urlopen", fake_urlopen)
        client = PolymarketClient(settings=Settings(paper_mode=True), paper_mode=True)

        assert await client.fetch_past_results("btc", "2026-04-26T17:00:00Z", "2026-04-26T18:00:00Z") == {"data": {"results": [{"closePrice": 77919.43}]}}
        assert seen_urls == [
            "https://polymarket.com/api/past-results?symbol=BTC&variant=hourly&assetType=crypto&currentEventStartTime=2026-04-26T17%3A00%3A00Z&count=4&endDate=2026-04-26T18%3A00%3A00Z&includeOutcomesBySlug=true"
        ]

    asyncio.run(run())


def test_clob_book_fetches_public_urls_in_paper_mode(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        seen: list[tuple[str, str | None, object]] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps([{"ok": True}]).encode()

        def fake_urlopen(request: object, timeout: int) -> FakeResponse:
            method = request.get_method() if hasattr(request, "get_method") else getattr(request, "method", None)
            seen.append((str(getattr(request, "full_url", request)), method, getattr(request, "data", None)))
            assert timeout == 15
            return FakeResponse()

        monkeypatch.setattr(polymarket_client_module.urllib.request, "urlopen", fake_urlopen)
        settings = Settings(paper_mode=True, polymarket_host="https://clob.example")
        client = PolymarketClient(settings=settings, paper_mode=True)

        assert await client.fetch_order_books(["token-a"]) == [{"ok": True}]
        assert await client.fetch_order_book("token-a") == [{"ok": True}]

        assert seen[0][0] == "https://clob.example/books"
        assert seen[0][1] == "POST"
        assert json.loads(seen[0][2].decode()) == [{"token_id": "token-a"}]
        assert seen[1][0] == "https://clob.example/book?token_id=token-a"

    asyncio.run(run())
