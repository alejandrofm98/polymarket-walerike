from __future__ import annotations

import asyncio
import importlib
import sys
import types


def _load_module():
    fake_httpx = types.SimpleNamespace(AsyncClient=None, HTTPStatusError=RuntimeError, RequestError=RuntimeError)
    sys.modules.setdefault("httpx", fake_httpx)
    return importlib.import_module("bot.data.polymarket_data_client")


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:  # type: ignore[no-untyped-def]
        self._payload = payload
        self.status_code = status_code

    def json(self):  # type: ignore[no-untyped-def]
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def get(self, url: str, params: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
        key = f"{url}?user={params.get('user')}" if params else url
        return self.responses[key]


def test_portfolio_value_uses_data_api_value_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        module = _load_module()
        responses = {
            "https://data.example/value?user=0xabc": _FakeResponse([{"user": "0xabc", "value": 7.25}]),
        }
        monkeypatch.setattr(module.httpx, "AsyncClient", lambda timeout: _FakeAsyncClient(responses))
        client = module.PolymarketDataClient("https://data.example")

        assert await client.portfolio_value("0xabc") == 7.25

    asyncio.run(run())
