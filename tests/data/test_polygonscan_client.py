from __future__ import annotations

import asyncio

from bot.data.polygonscan_client import PolygonScanClient


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    calls: list[tuple[str, dict[str, object]]] = []

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def get(self, url: str, params: dict[str, object]) -> _FakeResponse:
        self.calls.append((url, params))
        return _FakeResponse({"status": "1", "message": "OK", "result": "165431942289"})


def test_pusd_balance_uses_etherscan_v2_polygon_and_current_polymarket_usd_contract(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        from bot.data import polygonscan_client as module

        _FakeAsyncClient.calls = []
        monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
        client = PolygonScanClient("key")

        balance = await client.pusd_balance("0x63ce342161250d705dc0b16df89036c8e5f9ba9a")

        assert balance == 165431.942289
        assert _FakeAsyncClient.calls == [
            (
                "https://api.etherscan.io/v2/api",
                {
                    "chainid": 137,
                    "module": "account",
                    "action": "tokenbalance",
                    "contractaddress": "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb",
                    "address": "0x63ce342161250d705dc0b16df89036c8e5f9ba9a",
                    "tag": "latest",
                    "apikey": "key",
                },
            )
        ]

    asyncio.run(run())
