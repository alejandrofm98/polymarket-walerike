from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

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
        "size": 5.0,
        "order_type": OrderType.GTD,
        "expiration": int(time.time()) + 120,
    }
    values.update(overrides)
    return OrderRequest(**values)


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"price": 0.0}, "price"),
        ({"price": 1.0}, "price"),
        ({"size": 4.99}, "size"),
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


def test_paper_order_records_post_only_flag() -> None:
    async def run() -> None:
        client = PolymarketClient(paper_mode=True)

        order = await client.place_order(_request(post_only=True))

        assert order.raw["post_only"] is True

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


def test_env_api_creds_require_complete_values_when_only_api_key_set() -> None:
    client = PolymarketClient(settings=Settings(api_key="key"), paper_mode=False)

    class Types:
        class ApiCreds:  # pragma: no cover - must not be constructed for incomplete values
            pass

    with pytest.raises(RuntimeError, match="POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE"):
        client._env_api_creds(Types)


def test_env_api_creds_require_complete_values_when_secret_or_passphrase_set() -> None:
    client = PolymarketClient(settings=Settings(api_secret="secret"), paper_mode=False)

    class Types:
        class ApiCreds:  # pragma: no cover - must not be constructed for incomplete values
            pass

    with pytest.raises(RuntimeError, match="POLYMARKET_API_KEY"):
        client._env_api_creds(Types)


def test_env_api_creds_construct_clob_creds() -> None:
    settings = Settings(api_key="key", api_secret="secret", api_passphrase="pass")
    client = PolymarketClient(settings=settings, paper_mode=False)

    class Types:
        @dataclass
        class ApiCreds:
            api_key: str
            api_secret: str
            api_passphrase: str

    creds = client._env_api_creds(Types)

    assert creds.api_key == "key"
    assert creds.api_secret == "secret"
    assert creds.api_passphrase == "pass"


def test_build_clob_client_prefers_v2_sdk(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    imported = []

    class FakeClobClient:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def set_api_creds(self, creds):  # type: ignore[no-untyped-def]
            self.creds = creds

        def create_or_derive_api_key(self):  # type: ignore[no-untyped-def]
            raise AssertionError("client must use configured env creds")

    class FakeClientModule:
        ClobClient = FakeClobClient

    class FakeTypesModule:
        @dataclass
        class ApiCreds:
            api_key: str
            api_secret: str
            api_passphrase: str

        @dataclass
        class OrderArgsV2:
            token_id: str
            price: float
            size: float
            side: str
            expiration: int | None = None

        class OrderType:
            GTD = "GTD"

        class OpenOrderParams:
            pass

        class TradeParams:
            pass

        class BalanceAllowanceParams:
            pass

    class FakeConstantsModule:
        BUY = "BUY"
        SELL = "SELL"

    def fake_import_module(name: str) -> object:
        imported.append(name)
        modules = {
            "py_clob_client_v2.client": FakeClientModule,
            "py_clob_client_v2.clob_types": FakeTypesModule,
            "py_clob_client_v2.order_builder.constants": FakeConstantsModule,
        }
        if name in modules:
            return modules[name]
        raise AssertionError(name)

    monkeypatch.setattr(polymarket_client_module.importlib, "import_module", fake_import_module)
    settings = Settings(paper_mode=False, live_trading=True, private_key="key", api_key="key-id", api_secret="secret", api_passphrase="pass", chain_id=137)
    client = PolymarketClient(settings=settings, paper_mode=False)

    built = client._build_clob_client()

    assert "py_clob_client_v2.client" in imported
    assert built.kwargs["host"] == settings.polymarket_host
    assert built.kwargs["creds"].api_key == "key-id"
    assert client._sdk["OrderArgs"] is FakeTypesModule.OrderArgsV2


def test_live_signing_warnings_detect_api_key_address_mismatch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(api_key_address="0x1111111111111111111111111111111111111111")
    client = PolymarketClient(settings=settings, paper_mode=False)
    warnings = []

    class FakeLogger:
        def warning(self, message: str, *args: object) -> None:
            warnings.append(message.format(*args))

    monkeypatch.setattr(polymarket_client_module, "logger", FakeLogger())

    client._warn_live_signing_config(
        "0x2222222222222222222222222222222222222222",
        "0x2222222222222222222222222222222222222222",
        0,
    )

    assert any("API key address does not match signer address" in warning for warning in warnings)


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


def test_live_positions_data_api_uses_browser_json_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen_headers: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps([{ "asset": "token-a" }]).encode()

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == 15
        assert str(getattr(request, "full_url", "")) == "https://data.example/positions?user=0xfunder"
        seen_headers.update(dict(getattr(request, "headers", {})))
        return FakeResponse()

    monkeypatch.setattr(polymarket_client_module.urllib.request, "urlopen", fake_urlopen)
    settings = Settings(paper_mode=False, polymarket_data_api_url="https://data.example")
    client = PolymarketClient(settings=settings, paper_mode=False)

    assert client._fetch_positions("0xfunder") == [{"asset": "token-a"}]
    assert seen_headers["Accept"] == "application/json"
    assert "User-agent" in seen_headers


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


def test_paper_account_reads_are_empty() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=True), paper_mode=True)

        assert await client.get_account_balances() == {"available": False, "reason": "live account data requires live mode"}
        assert await client.get_account_trades() == []

    asyncio.run(run())


def test_live_account_balances_use_clob_client_methods() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)

        @dataclass
        class FakeBalanceAllowanceParams:
            asset_type: str
            signature_type: int = -1

        class FakeClob:
            def get_balance_allowance(self, params):  # type: ignore[no-untyped-def]
                assert not isinstance(params, dict)
                assert params.asset_type == "COLLATERAL"
                assert params.signature_type == -1
                return {"balance": "1200000", "allowance": "3400000"}

        client._sdk = {"BalanceAllowanceParams": FakeBalanceAllowanceParams}
        client._clob_client = FakeClob()

        assert await client.get_account_balances() == {
            "available": True,
            "cash_balance": 1.2,
            "portfolio_value": None,
            "total_balance": 1.2,
            "allowances": {"default": 3.4},
            "raw": {"balance": "1200000", "allowance": "3400000"},
            "source": "clob",
        }

    asyncio.run(run())


def test_live_account_balances_build_clob_client_when_disconnected() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)

        @dataclass
        class FakeBalanceAllowanceParams:
            asset_type: str
            signature_type: int = -1

        class FakeClob:
            def get_balance_allowance(self, params):  # type: ignore[no-untyped-def]
                assert params.asset_type == "COLLATERAL"
                return {"balance": "1200000", "allowance": "3400000"}

        client._sdk = {"BalanceAllowanceParams": FakeBalanceAllowanceParams}
        client._build_clob_client = lambda: FakeClob()  # type: ignore[method-assign]

        assert await client.get_account_balances() == {
            "available": True,
            "cash_balance": 1.2,
            "portfolio_value": None,
            "total_balance": 1.2,
            "allowances": {"default": 3.4},
            "raw": {"balance": "1200000", "allowance": "3400000"},
            "source": "clob",
        }

    asyncio.run(run())


def test_live_account_balances_include_total_from_data_client() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True, funder="0xfunder"), paper_mode=False)

        @dataclass
        class FakeBalanceAllowanceParams:
            asset_type: str
            signature_type: int = -1

        class FakeClob:
            def get_balance_allowance(self, params):  # type: ignore[no-untyped-def]
                assert params.asset_type == "COLLATERAL"
                return {"balance": "1200000", "allowances": {"0xspender": "3400000"}}

        class FakeDataClient:
            async def portfolio_value(self, wallet: str) -> float | None:
                assert wallet == "0xfunder"
                return 4.5

        client._sdk = {"BalanceAllowanceParams": FakeBalanceAllowanceParams}
        client._clob_client = FakeClob()
        client.data_client = FakeDataClient()

        assert await client.get_account_balances() == {
            "available": True,
            "cash_balance": 1.2,
            "portfolio_value": 4.5,
            "total_balance": 5.7,
            "allowances": {"0xspender": 3.4},
            "raw": {"balance": "1200000", "allowances": {"0xspender": "3400000"}},
            "source": "clob_and_data_api",
        }

    asyncio.run(run())


def test_live_account_balances_falls_back_to_imported_params(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)

        @dataclass
        class FakeBalanceAllowanceParams:
            asset_type: str
            signature_type: int = -1

        class FakeClobTypes:
            BalanceAllowanceParams = FakeBalanceAllowanceParams

        class FakeClob:
            def get_balance_allowance(self, params):  # type: ignore[no-untyped-def]
                assert params.asset_type == "COLLATERAL"
                assert params.signature_type == -1
                return {"balance": "1200000", "allowance": "3400000"}

        def fake_import_module(name: str) -> object:
            if name == "py_clob_client.clob_types":
                return FakeClobTypes
            raise AssertionError(name)

        monkeypatch.setattr(polymarket_client_module.importlib, "import_module", fake_import_module)
        client._clob_client = FakeClob()

        assert (await client.get_account_balances())["cash_balance"] == 1.2

    asyncio.run(run())


def test_live_account_trades_normalizes_sdk_payload() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)

        class FakeClob:
            def get_trades(self):  # type: ignore[no-untyped-def]
                return [{"id": "t1", "market": "m1", "side": "BUY", "size": "10", "price": "0.42", "fee": "0.01", "timestamp": "1777320000"}]

        client._clob_client = FakeClob()

        assert await client.get_account_trades() == [
            {"id": "t1", "market": "m1", "side": "BUY", "size": 10.0, "price": 0.42, "fee": 0.01, "timestamp": 1777320000.0, "raw": {"id": "t1", "market": "m1", "side": "BUY", "size": "10", "price": "0.42", "fee": "0.01", "timestamp": "1777320000"}},
        ]

    asyncio.run(run())


def test_live_order_passes_post_only_to_sdk_post_order() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)
        calls = []

        @dataclass
        class FakeOrderArgs:
            token_id: str
            price: float
            size: float
            side: str
            expiration: int | None = None

        class FakeOrderType:
            GTD = "GTD"

        class FakeClob:
            def create_order(self, args):  # type: ignore[no-untyped-def]
                calls.append(("create_order", args))
                return {"signed": True}

            def post_order(self, signed, order_type, *, post_only=False):  # type: ignore[no-untyped-def]
                calls.append(("post_order", signed, order_type, post_only))
                return {"success": True, "orderID": "live-1", "status": "live"}

        client._sdk = {"OrderArgs": FakeOrderArgs, "OrderType": FakeOrderType, "BUY": "BUY", "SELL": "SELL"}
        client._clob_client = FakeClob()

        order = await client.place_order(_request(post_only=True))

        assert order.order_id == "live-1"
        assert calls[-1] == ("post_order", {"signed": True}, "GTD", True)

    asyncio.run(run())


def test_live_post_only_order_reports_old_sdk_clearly() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)

        @dataclass
        class FakeOrderArgs:
            token_id: str
            price: float
            size: float
            side: str
            expiration: int | None = None

        class FakeOrderType:
            GTD = "GTD"

        class FakeClob:
            def create_order(self, args):  # type: ignore[no-untyped-def]
                return {"signed": True}

            def post_order(self, signed, order_type):  # type: ignore[no-untyped-def]
                return {"success": True, "orderID": "live-1", "status": "live"}

        client._sdk = {"OrderArgs": FakeOrderArgs, "OrderType": FakeOrderType, "BUY": "BUY", "SELL": "SELL"}
        client._clob_client = FakeClob()

        with pytest.raises(RuntimeError, match="post_only"):
            await client.place_order(_request(post_only=True))

    asyncio.run(run())


def test_v2_live_order_uses_create_and_post_order_for_version_retry() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)
        calls = []

        @dataclass
        class FakeOrderArgs:
            token_id: str
            price: float
            size: float
            side: str
            expiration: int | None = None

        class FakeOrderType:
            GTD = "GTD"

        class FakeClob:
            def create_and_post_order(self, args, options=None, order_type="GTC", post_only=False):  # type: ignore[no-untyped-def]
                calls.append(("create_and_post_order", args, options, order_type, post_only))
                return {"success": True, "orderID": "live-v2", "status": "live"}

            def create_order(self, args):  # pragma: no cover
                raise AssertionError("v2 orders should use SDK retry helper")

        client._sdk = {"name": "py-clob-client-v2", "OrderArgs": FakeOrderArgs, "OrderType": FakeOrderType, "BUY": "BUY", "SELL": "SELL"}
        client._clob_client = FakeClob()

        order = await client.place_order(_request(post_only=True))

        assert order.order_id == "live-v2"
        assert calls[0][0] == "create_and_post_order"
        assert calls[0][3] == "GTD"
        assert calls[0][4] is True

    asyncio.run(run())


def test_v2_get_and_cancel_orders_use_v2_method_names() -> None:
    async def run() -> None:
        client = PolymarketClient(Settings(paper_mode=False, live_trading=True), paper_mode=False)
        calls = []

        @dataclass
        class FakeOrderPayload:
            orderID: str

        class FakeClob:
            def get_open_orders(self):  # type: ignore[no-untyped-def]
                calls.append(("get_open_orders",))
                return [{"id": "order-1"}]

            def cancel_order(self, payload):  # type: ignore[no-untyped-def]
                calls.append(("cancel_order", payload.orderID))
                return True

        client._sdk = {"name": "py-clob-client-v2", "OrderPayload": FakeOrderPayload}
        client._clob_client = FakeClob()

        assert await client.get_orders() == [{"id": "order-1"}]
        assert await client.cancel_order("order-1") is True
        assert calls == [("get_open_orders",), ("cancel_order", "order-1")]

    asyncio.run(run())
