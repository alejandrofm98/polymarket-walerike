from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from bot.config.runtime_config import RuntimeConfigStore
from bot.core.polymarket_client import OrderRequest, OrderResponse, OrderSide, OrderType
from bot.runtime.copy_engine import CopyTradingEngine


@dataclass
class Wallet:
    address: str
    enabled: bool = True
    fixed_amount: float = 0.0
    sizing_mode: str = "percent"


@dataclass
class WalletActivity:
    wallet_address: str
    market_id: str
    side: str
    size: float
    notional: float
    timestamp: float = field(default_factory=time.time)


class FakeDataClient:
    def __init__(self, wallet_activities: dict[str, list[WalletActivity]], portfolio_values: dict[str, float]) -> None:
        self.wallet_activities = wallet_activities
        self.portfolio_values = portfolio_values

    async def wallet_activity(self, wallet_address: str) -> list[WalletActivity]:
        return self.wallet_activities.get(wallet_address, [])

    async def portfolio_value(self, wallet_address: str) -> float | None:
        return self.portfolio_values.get(wallet_address)


class FakeClient:
    def __init__(self) -> None:
        self.orders = []

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
        self.events = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class FakeConfigStore:
    def __init__(self, poll_interval: float = 1.0, wallets: list[Wallet] | None = None) -> None:
        self._poll_interval = poll_interval
        self._wallets = wallets or []
        self._config: dict[str, Any] = {
            "poll_interval_seconds": poll_interval,
            "wallets": [{"address": w.address, "enabled": w.enabled, "fixed_amount": w.fixed_amount, "sizing_mode": w.sizing_mode} for w in self._wallets],
        }

    def load(self) -> dict[str, Any]:
        return self._config


def test_copy_engine_copies_buy_with_leader_percent() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=5.0,
                        notional=5.0,
                        timestamp=time.time(),
                    )
                ]
            },
            portfolio_values={"0xLeader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert len(client.orders) == 1
        order = client.orders[0]
        assert order.side == OrderSide.BUY
        expected_size = 200.0 * 5.0 / 100.0
        assert order.size == expected_size

    asyncio.run(run())


def test_copy_engine_skips_duplicate_market_side() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        now = time.time()
        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=5.0,
                        notional=5.0,
                        timestamp=now,
                    ),
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=3.0,
                        notional=3.0,
                        timestamp=now + 1,
                    ),
                ]
            },
            portfolio_values={"0xLeader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["duplicates"] == 1
        assert len(client.orders) == 1

    asyncio.run(run())


def test_copy_engine_copies_buy_with_fixed() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=5.0, sizing_mode="fixed")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=10.0,
                        notional=10.0,
                        timestamp=time.time(),
                    )
                ]
            },
            portfolio_values={"0xLeader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert len(client.orders) == 1
        order = client.orders[0]
        fixed_size = 5.0 / order.price
        assert abs(order.size - fixed_size) < 0.01

    asyncio.run(run())


def test_copy_engine_skips_when_leader_portfolio_missing() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=5.0,
                        notional=5.0,
                        timestamp=time.time(),
                    )
                ]
            },
            portfolio_values={},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 0
        assert summary["skipped"] == 1
        assert len(client.orders) == 0
        log_events = [e for e in broadcaster.events if e[0] == "log"]
        assert any("leader_portfolio" in e[1].get("message", "").lower() for e in log_events)

    asyncio.run(run())


def test_copy_engine_copies_sell_closes_copied_position() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        leader_portfolio = 100.0
        user_portfolio = 200.0
        leader_notional = 5.0
        expected_copy_size = user_portfolio * leader_notional / leader_portfolio

        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="BUY",
                        size=leader_notional,
                        notional=leader_notional,
                        timestamp=time.time() - 10,
                    ),
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-1",
                        side="SELL",
                        size=leader_notional,
                        notional=leader_notional,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xLeader": leader_portfolio},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=user_portfolio,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[0].side == OrderSide.BUY
        assert client.orders[1].side == OrderSide.SELL

    asyncio.run(run())


def test_copy_engine_does_not_close_unrelated_sell() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xLeader": [
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-never-copied",
                        side="BUY",
                        size=5.0,
                        notional=5.0,
                        timestamp=time.time() - 10,
                    ),
                    WalletActivity(
                        wallet_address="0xLeader",
                        market_id="market-never-copied",
                        side="SELL",
                        size=5.0,
                        notional=5.0,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xLeader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=200.0,
            paper=True,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[0].side == OrderSide.BUY
        assert client.orders[1].side == OrderSide.SELL

    asyncio.run(run())


def test_copy_engine_lifecycle() -> None:
    async def run() -> None:
        config_store = FakeConfigStore(poll_interval=60, wallets=[])
        data_client = FakeDataClient({}, {})
        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=100.0,
            paper=True,
        )

        assert engine.status()["status"] == "stopped"

        await engine.start()
        status = engine.status()
        assert status["running"] is True
        assert status["status"] == "running"

        await engine.pause()
        status = engine.status()
        assert status["paused"] is True
        assert status["status"] == "paused"

        await engine.stop()
        status = engine.status()
        assert status["running"] is False
        assert status["status"] == "stopped"

    asyncio.run(run())