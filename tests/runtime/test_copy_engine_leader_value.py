from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from bot.config.runtime_config import RuntimeConfigStore
from bot.core.polymarket_client import OrderRequest, OrderResponse, OrderSide
from bot.data.polymarket_data_client import WalletActivity
from bot.runtime.copy_engine import CopyTradingEngine


class FakeDataClient:
    def __init__(self, activities: list[WalletActivity], portfolio_value: float | None) -> None:
        self.activities = activities
        self._portfolio_value = portfolio_value

    async def wallet_activity(self, wallet: str) -> list[WalletActivity]:
        return list(self.activities)

    async def portfolio_value(self, wallet: str) -> float | None:
        return self._portfolio_value


class FakeClient:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        self.orders.append(request)
        return OrderResponse(
            order_id=f"order-{len(self.orders)}",
            status="OPEN",
            market=request.market,
            asset_id=request.asset_id,
            side=request.side,
            price=request.price,
            size=request.size,
            raw={"paper": True},
        )


class FakeBroadcaster:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


def _write_config(path: Path, *, sizing_mode: str, fixed_amount: float = 0.0) -> RuntimeConfigStore:
    store = RuntimeConfigStore(path)
    store.update(
        {
            "copy_wallets": [
                {
                    "address": "0xLeader",
                    "enabled": True,
                    "sizing_mode": sizing_mode,
                    "fixed_amount": fixed_amount,
                }
            ],
            "poll_interval_seconds": 60,
        }
    )
    return store


def _buy_activity() -> WalletActivity:
    return WalletActivity(
        event_id="leader-buy-1",
        wallet="0xleader",
        action="buy",
        market_id="market-1",
        side="YES",
        price=0.5,
        size=10.0,
        timestamp=time.time(),
        token_id="token-yes",
    )


def test_copy_engine_skips_leader_percent_without_portfolio_value(tmp_path: Path) -> None:
    async def run() -> None:
        config_store = _write_config(tmp_path / "runtime_config.json", sizing_mode="leader_percent")
        client = FakeClient()
        broadcaster = FakeBroadcaster()
        engine = CopyTradingEngine(
            client=client,
            data_client=FakeDataClient([_buy_activity()], portfolio_value=None),
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 0
        assert summary["skipped"] == 1
        assert client.orders == []
        messages = [payload["message"] for event, payload in broadcaster.events if event == "log"]
        assert any("reason=missing_leader_portfolio_value" in message for message in messages)

    asyncio.run(run())


def test_copy_engine_allows_fixed_mode_without_portfolio_value(tmp_path: Path) -> None:
    async def run() -> None:
        config_store = _write_config(tmp_path / "runtime_config.json", sizing_mode="fixed", fixed_amount=5.0)
        client = FakeClient()
        engine = CopyTradingEngine(
            client=client,
            data_client=FakeDataClient([_buy_activity()], portfolio_value=None),
            runtime_config_store=config_store,
            broadcaster=FakeBroadcaster(),
            user_portfolio_value=lambda: 200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["skipped"] == 0
        assert len(client.orders) == 1
        assert client.orders[0].side == OrderSide.BUY

    asyncio.run(run())
