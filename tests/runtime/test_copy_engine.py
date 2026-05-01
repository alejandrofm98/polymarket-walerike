from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from bot.config.runtime_config import RuntimeConfig, RuntimeConfigStore
from bot.core.polymarket_client import OrderRequest, OrderResponse, OrderSide, OrderType
from bot.data.polymarket_data_client import WalletActivity
from bot.data.trade_logger import TradeLogger
from bot.runtime.copy_engine import CopyTradingEngine


@dataclass
class Wallet:
    address: str
    enabled: bool = True
    fixed_amount: float = 0.0
    sizing_mode: str = "leader_percent"


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
            raw={},
        )


class FlakyClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_order = True

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.fail_next_order:
            self.fail_next_order = False
            raise RuntimeError("temporary order failure")
        return await super().place_order(request)


class FakeBroadcaster:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class FakeConfigStore:
    def __init__(self, poll_interval: float = 1.0, wallets: list[Wallet] | None = None) -> None:
        self._poll_interval = poll_interval
        self._wallets = wallets or []

    def load(self) -> Any:
        return RuntimeConfig(
            poll_interval_seconds=self._poll_interval,
            copy_wallets=[
                {"address": w.address.lower(), "enabled": w.enabled, "fixed_amount": w.fixed_amount, "sizing_mode": w.sizing_mode}
                for w in self._wallets
            ],
            solo_log=False,
        )


def test_copy_engine_status_has_no_trading_mode(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = CopyTradingEngine(
        client=FakeClient(),
        data_client=FakeDataClient({}, {}),
        runtime_config_store=RuntimeConfigStore(tmp_path / "runtime_config.json"),
    )

    status = engine.status()

    assert ("pa" + "per" + "_mode") not in status


def make_activity(
    *,
    event_id: str,
    action: str,
    market_id: str = "market-1",
    side: str = "YES",
    price: float = 0.5,
    size: float = 10.0,
    wallet: str = "0xleader",
    timestamp: float | None = None,
    token_id: str = "token-yes",
) -> WalletActivity:
    return WalletActivity(
        event_id=event_id,
        wallet=wallet,
        action=action,
        market_id=market_id,
        side=side,
        price=price,
        size=size,
        timestamp=time.time() if timestamp is None else timestamp,
        token_id=token_id,
    )


def test_copy_engine_copies_buy_with_leader_percent() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=time.time(),
                    )
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert len(client.orders) == 1
        order = client.orders[0]
        assert order.side == OrderSide.BUY
        expected_size = (200.0 * 5.0 / 100.0) / 0.5
        assert order.size == expected_size

    asyncio.run(run())


def test_copy_engine_skips_duplicate_market_side() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        now = time.time()
        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=now,
                    ),
                    WalletActivity(
                        event_id="buy-2",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=6.0,
                        timestamp=now + 1,
                    ),
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
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
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=20.0,
                        timestamp=time.time(),
                    )
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
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
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=10.0,
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
            user_portfolio_value=lambda: 200.0,
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
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        leader_portfolio = 100.0
        user_portfolio = 200.0
        leader_notional = 5.0
        expected_copy_size = user_portfolio * leader_notional / leader_portfolio

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=leader_notional / 0.5,
                        timestamp=time.time() - 10,
                    ),
                    WalletActivity(
                        event_id="sell-1",
                        wallet="0xleader",
                        action="sell",
                        market_id="market-1",
                        side="YES",
                        price=0.6,
                        size=leader_notional / 0.6,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xleader": leader_portfolio},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: user_portfolio,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[0].side == OrderSide.BUY
        assert client.orders[1].side == OrderSide.SELL

    asyncio.run(run())


def test_copy_engine_copies_buy_then_matching_sell_closes_position() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-never-copied",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=time.time() - 10,
                    ),
                    WalletActivity(
                        event_id="sell-1",
                        wallet="0xleader",
                        action="sell",
                        market_id="market-never-copied",
                        side="YES",
                        price=0.6,
                        size=10.0,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[0].side == OrderSide.BUY
        assert client.orders[1].side == OrderSide.SELL

    asyncio.run(run())


def test_copy_engine_skips_unrelated_sell_and_keeps_copied_position_open() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    WalletActivity(
                        event_id="buy-1",
                        wallet="0xleader",
                        action="buy",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=time.time() - 10,
                    ),
                    WalletActivity(
                        event_id="sell-1",
                        wallet="0xleader",
                        action="sell",
                        market_id="market-2",
                        side="YES",
                        price=0.6,
                        size=10.0,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 0
        assert summary["skipped"] == 1
        assert len(client.orders) == 1
        assert client.orders[0].side == OrderSide.BUY
        assert ("0xleader", "market-1", "YES") in engine._copied_positions

    asyncio.run(run())


def test_copy_engine_duplicate_buy_does_not_let_second_wallet_sell_close_first_wallet_position() -> None:
    async def run() -> None:
        wallets = [
            Wallet(address="0xWalletA", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent"),
            Wallet(address="0xWalletB", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent"),
        ]
        config_store = FakeConfigStore(poll_interval=60, wallets=wallets)

        now = time.time()
        data_client = FakeDataClient(
            wallet_activities={
                "0xwalleta": [
                    make_activity(
                        event_id="wallet-a-buy-1",
                        action="buy",
                        wallet="0xwalleta",
                        market_id="market-x",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=now,
                        token_id="token-yes",
                    )
                ],
                "0xwalletb": [
                    make_activity(
                        event_id="wallet-b-buy-1",
                        action="buy",
                        wallet="0xwalletb",
                        market_id="market-x",
                        side="YES",
                        price=0.5,
                        size=6.0,
                        timestamp=now + 1,
                        token_id="token-yes",
                    ),
                    make_activity(
                        event_id="wallet-b-sell-1",
                        action="sell",
                        wallet="0xwalletb",
                        market_id="market-x",
                        side="YES",
                        price=0.6,
                        size=6.0,
                        timestamp=now + 2,
                        token_id="token-yes",
                    ),
                ],
            },
            portfolio_values={"0xwalleta": 100.0, "0xwalletb": 100.0},
        )

        client = FakeClient()
        broadcaster = FakeBroadcaster()

        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=broadcaster,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["duplicates"] == 1
        assert summary["skipped"] == 1
        assert summary["closed"] == 0
        assert len(client.orders) == 1
        assert client.orders[0].side == OrderSide.BUY
        assert ("0xwalleta", "market-x", "YES") in engine._copied_positions
        assert ("0xwalletb", "market-x", "YES") not in engine._copied_positions

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
            user_portfolio_value=lambda: 100.0,
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

        await engine.start()
        status = engine.status()
        assert status["running"] is True
        assert status["paused"] is False
        assert status["status"] == "running"

        await engine.stop()
        status = engine.status()
        assert status["running"] is False
        assert status["status"] == "stopped"

    asyncio.run(run())


def test_copy_engine_persists_copy_trade_metadata_and_closes_trade(tmp_path: Path) -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=5.0, sizing_mode="fixed")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])
        trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    make_activity(
                        event_id="buy-1",
                        action="buy",
                        price=0.4,
                        size=12.5,
                        timestamp=time.time() - 10,
                    ),
                    make_activity(
                        event_id="sell-1",
                        action="sell",
                        price=0.7,
                        size=7.142857142857143,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xleader": 125.0},
        )
        engine = CopyTradingEngine(
            client=FakeClient(),
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=FakeBroadcaster(),
            trade_logger=trade_logger,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert engine.client.orders[1].size == pytest.approx(7.142857142857143)
        trades = trade_logger.list_trades(limit=None)
        open_trades = trade_logger.list_trades(status="OPEN", limit=None)
        partial_closes = [trade for trade in trades if trade.status == "CLOSED"]
        assert len(open_trades) == 1
        assert open_trades[0].trade_id == "order-1"
        assert open_trades[0].size == pytest.approx(5.357142857142857)
        assert len(partial_closes) == 1
        trade = partial_closes[0]
        assert trade.trade_id.startswith("order-1::close::")
        assert trade.side == "BUY"
        assert trade.status == "CLOSED"
        assert trade.exit_price == 0.7
        assert trade.size == pytest.approx(7.142857142857143)
        assert trade.pnl == pytest.approx(2.142857142857143)
        assert open_trades[0].metadata == {
            "asset": "token-yes",
            "copy_trade": True,
            "fixed_amount": 5.0,
            "leader_event_id": "buy-1",
            "leader_notional": 5.0,
            "leader_portfolio_value": 125.0,
            "leader_price": 0.4,
            "leader_size": 12.5,
            "leader_wallet": "0xleader",
            "market_slug": None,
            "outcome_side": "YES",
            "sizing_mode": "fixed",
            "timeframe": None,
        }

    asyncio.run(run())


def test_copy_engine_partial_sell_keeps_remaining_position_open(tmp_path: Path) -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=5.0, sizing_mode="fixed")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])
        trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    make_activity(
                        event_id="buy-1",
                        action="buy",
                        price=0.4,
                        size=12.5,
                        timestamp=time.time() - 10,
                    ),
                    make_activity(
                        event_id="sell-1",
                        action="sell",
                        price=0.5,
                        size=5.0,
                        timestamp=time.time(),
                    ),
                ]
            },
            portfolio_values={"0xleader": 125.0},
        )
        client = FakeClient()
        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=FakeBroadcaster(),
            trade_logger=trade_logger,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[1].size == pytest.approx(5.0)

        open_trades = trade_logger.list_trades(status="OPEN", limit=None)
        closed_trades = trade_logger.list_trades(limit=None)
        positions = trade_logger.list_positions()

        assert len(open_trades) == 1
        assert open_trades[0].trade_id == "order-1"
        assert open_trades[0].side == "BUY"
        assert open_trades[0].size == pytest.approx(7.5)
        assert len(positions) == 1
        assert positions[0].side == "YES"
        assert positions[0].size == pytest.approx(7.5)
        partial_closes = [trade for trade in closed_trades if trade.status == "CLOSED"]
        assert len(partial_closes) == 1
        assert partial_closes[0].size == pytest.approx(5.0)
        assert partial_closes[0].pnl == pytest.approx(0.5)

    asyncio.run(run())


def test_copy_engine_partial_sell_uses_leader_share_fraction_after_price_move() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=0.0, sizing_mode="leader_percent")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        data_client = FakeDataClient(
            wallet_activities={
                "0xleader": [
                    make_activity(
                        event_id="buy-1",
                        action="buy",
                        wallet="0xleader",
                        market_id="market-1",
                        side="YES",
                        price=0.5,
                        size=10.0,
                        timestamp=time.time() - 10,
                        token_id="token-yes",
                    ),
                    make_activity(
                        event_id="sell-1",
                        action="sell",
                        wallet="0xleader",
                        market_id="market-1",
                        side="YES",
                        price=0.8,
                        size=4.0,
                        timestamp=time.time(),
                        token_id="token-yes",
                    ),
                ]
            },
            portfolio_values={"0xleader": 100.0},
        )

        client = FakeClient()
        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            user_portfolio_value=lambda: 200.0,
        )

        summary = await engine.run_once()

        assert summary["copied"] == 1
        assert summary["closed"] == 1
        assert len(client.orders) == 2
        assert client.orders[0].size == pytest.approx(20.0)
        assert client.orders[1].side == OrderSide.SELL
        assert client.orders[1].size == pytest.approx(8.0)
        assert engine._copied_positions[("0xleader", "market-1", "YES")]["size"] == pytest.approx(12.0)

    asyncio.run(run())


def test_copy_engine_retries_event_after_transient_order_failure() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=5.0, sizing_mode="fixed")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])
        activity = make_activity(event_id="buy-1", action="buy", price=0.4, size=12.5, timestamp=time.time())
        data_client = FakeDataClient(wallet_activities={"0xleader": [activity]}, portfolio_values={"0xleader": 125.0})
        client = FlakyClient()
        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=FakeBroadcaster(),
            user_portfolio_value=lambda: 200.0,
        )

        first_summary = await engine.run_once()

        assert first_summary["copied"] == 0
        assert first_summary["skipped"] == 1
        assert len(client.orders) == 0
        assert activity.event_id not in engine._seen_events

        second_summary = await engine.run_once()

        assert second_summary["copied"] == 1
        assert len(client.orders) == 1
        assert activity.event_id in engine._seen_events

    asyncio.run(run())


def test_copy_engine_unmatched_sell_does_not_replay_and_close_later_buy() -> None:
    async def run() -> None:
        wallet = Wallet(address="0xLeader", enabled=True, fixed_amount=5.0, sizing_mode="fixed")
        config_store = FakeConfigStore(poll_interval=60, wallets=[wallet])

        old_sell = make_activity(
            event_id="sell-old",
            action="sell",
            price=0.6,
            size=5.0,
            timestamp=time.time() - 60,
        )
        later_buy = make_activity(
            event_id="buy-new",
            action="buy",
            price=0.4,
            size=12.5,
            timestamp=time.time(),
        )
        data_client = FakeDataClient(
            wallet_activities={"0xleader": [old_sell]},
            portfolio_values={"0xleader": 125.0},
        )
        client = FakeClient()
        engine = CopyTradingEngine(
            client=client,
            data_client=data_client,
            runtime_config_store=config_store,
            broadcaster=FakeBroadcaster(),
            user_portfolio_value=lambda: 200.0,
        )

        first_summary = await engine.run_once()

        assert first_summary["copied"] == 0
        assert first_summary["closed"] == 0
        assert first_summary["skipped"] == 1
        assert len(client.orders) == 0

        data_client.wallet_activities["0xleader"] = [later_buy, old_sell]

        second_summary = await engine.run_once()

        assert second_summary["copied"] == 1
        assert second_summary["closed"] == 0
        assert second_summary["skipped"] == 0
        assert len(client.orders) == 1
        assert client.orders[0].side == OrderSide.BUY

    asyncio.run(run())
