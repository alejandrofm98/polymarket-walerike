from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.config.settings import Settings
from bot.core.chainlink_oracle import OraclePrice
from bot.core.polymarket_client import OrderResponse
from bot.data.market_scanner import MarketCandidate
from bot.data.trade_logger import TradeLogger, TradeRecord
from bot.runtime import BotEngine


@dataclass(slots=True)
class Tick:
    asset: str
    price: float


class FakeScanner:
    async def scan(self) -> list[MarketCandidate]:
        return [
            MarketCandidate(
                market_id="btc-15m",
                question="Bitcoin up or down in 15m?",
                asset="BTC",
                timeframe="15m",
                tokens=[
                    {"outcome": "Yes", "token_id": "yes-token", "price": 0.4, "liquidity": 100},
                    {"outcome": "No", "token_id": "no-token", "price": 0.5, "liquidity": 100},
                ],
            )
        ]


class ReversalScanner:
    def __init__(self) -> None:
        self.prices = [0.4, 0.43]
        self.calls = 0

    async def scan(self) -> list[MarketCandidate]:
        price = self.prices[min(self.calls, len(self.prices) - 1)]
        self.calls += 1
        return [
            MarketCandidate(
                market_id="btc-15m",
                question="Bitcoin up or down in 15m?",
                asset="BTC",
                timeframe="15m",
                market_slug="btc-updown-15m-test",
                tokens=[
                    {"outcome": "Yes", "token_id": "yes-token", "price": price, "liquidity": 100},
                    {"outcome": "No", "token_id": "no-token", "price": 0.5, "liquidity": 100},
                ],
            )
        ]


class EmptyScanner:
    async def scan(self) -> list[MarketCandidate]:
        return []


class ExpiredScanner:
    async def scan(self) -> list[MarketCandidate]:
        return [
            MarketCandidate(
                market_id="m1",
                condition_id="m1",
                question="Bitcoin up or down?",
                asset="BTC",
                timeframe="5m",
                end_date=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                price_to_beat=99.0,
                tokens=[
                    {"outcome": "Yes", "token_id": "yes-token", "price": 0.4, "liquidity": 100},
                    {"outcome": "No", "token_id": "no-token", "price": 0.5, "liquidity": 100},
                ],
            )
        ]


class FakeClient:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.orders = []

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def place_order(self, request):  # type: ignore[no-untyped-def]
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


class OfficialResolutionClient(FakeClient):
    async def fetch_market_by_slug(self, slug: str) -> dict[str, object]:
        assert slug == "btc-updown-5m-closed"
        return {
            "slug": slug,
            "closed": True,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0", "1"]',
        }


class FakeLogger:
    def __init__(self) -> None:
        self.records = []

    def log_trade_opened(self, record):  # type: ignore[no-untyped-def]
        self.records.append(record)
        return record

    def account_stats(self) -> dict[str, int]:
        return {"total_trades": len(self.records)}


class FakeBroadcaster:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))


class FakeOracle:
    def get_cached_price(self, asset: str) -> OraclePrice:
        return OraclePrice(asset=asset, price=100.0, round_id=1, updated_at=time.time(), stale=False)


class FakePriceFeed:
    def __init__(self) -> None:
        self.latest = {"BTC": Tick(asset="BTC", price=100.0)}
        self.closed = False

    def momentum_pct(self, asset: str) -> float:
        return 0.0

    def close(self) -> None:
        self.closed = True


def test_bot_engine_lifecycle_and_single_paper_tick() -> None:
    async def run() -> None:
        lifecycle_client = FakeClient()
        lifecycle_engine = BotEngine(
            settings=Settings(paper_mode=True, live_trading=False),
            client=lifecycle_client,
            scanner=EmptyScanner(),
            price_feed=FakePriceFeed(),
            oracle=FakeOracle(),
            scan_interval=60,
        )

        assert lifecycle_engine.status()["status"] == "stopped"
        await lifecycle_engine.start()
        await lifecycle_engine.pause()
        assert lifecycle_engine.status()["status"] == "paused"
        await lifecycle_engine.stop()
        assert lifecycle_client.connected is True
        assert lifecycle_client.closed is True

        client = FakeClient()
        logger = FakeLogger()
        broadcaster = FakeBroadcaster()
        price_feed = FakePriceFeed()
        engine = BotEngine(
            settings=Settings(paper_mode=True, live_trading=False),
            client=client,
            trade_logger=logger,
            broadcaster=broadcaster,
            scanner=ReversalScanner(),
            price_feed=price_feed,
            oracle=FakeOracle(),
            scan_interval=60,
        )

        first_summary = await engine.run_once()
        summary = await engine.run_once()
        await engine.close()

        assert first_summary == {"scanned": 1, "evaluated": 1, "orders": 0, "skipped": 0}
        assert summary == {"scanned": 1, "evaluated": 1, "orders": 1, "skipped": 0}
        assert len(client.orders) == 1
        assert len(logger.records) == 1
        assert price_feed.closed is True
        assert any(event[0] == "order_placed" for event in broadcaster.events)

    asyncio.run(run())


def test_bot_engine_skips_missing_prices_without_crashing() -> None:
    async def run() -> None:
        engine = BotEngine(
            settings=Settings(paper_mode=True, live_trading=False),
            client=FakeClient(),
            scanner=FakeScanner(),
            price_feed=None,
            oracle=FakeOracle(),
        )

        summary = await engine.run_once()

        assert summary["skipped"] == 1
        assert engine.last_error is None

    asyncio.run(run())


def test_bot_engine_settles_expired_paper_market(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        trade_logger.log_trade_opened(
            TradeRecord(
                trade_id="yes",
                market="m1",
                asset="BTC",
                side="YES",
                entry_price=0.4,
                size=10,
                metadata={"end_date": past, "price_to_beat": 99.0, "paper": True},
            )
        )
        trade_logger.log_trade_opened(
            TradeRecord(
                trade_id="no",
                market="m1",
                asset="BTC",
                side="NO",
                entry_price=0.5,
                size=10,
                metadata={"end_date": past, "price_to_beat": 99.0, "paper": True},
            )
        )
        broadcaster = FakeBroadcaster()
        engine = BotEngine(
            settings=Settings(paper_mode=True, live_trading=False),
            client=FakeClient(),
            trade_logger=trade_logger,
            broadcaster=broadcaster,
            scanner=ExpiredScanner(),
            price_feed=FakePriceFeed(),
            oracle=FakeOracle(),
        )

        summary = await engine.run_once()

        yes = trade_logger.get_trade("yes")
        no = trade_logger.get_trade("no")
        assert summary["orders"] == 0
        assert yes is not None and yes.status == "RESOLVED" and yes.pnl == 6.0
        assert no is not None and no.status == "RESOLVED" and no.pnl == -5.0
        assert trade_logger.list_positions() == []
        assert engine.account.daily_pnl == 1.0
        assert any(event[0] == "market_resolved" for event in broadcaster.events)
        assert any(event[0] == "positions" for event in broadcaster.events)

    asyncio.run(run())


def test_bot_engine_prefers_official_gamma_resolution(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        metadata = {
            "end_date": past,
            "price_to_beat": 99.0,
            "paper": True,
            "market_slug": "btc-updown-5m-closed",
        }
        trade_logger.log_trade_opened(
            TradeRecord(
                trade_id="yes",
                market="m1",
                asset="BTC",
                side="YES",
                entry_price=0.2,
                size=10,
                metadata=metadata,
            )
        )
        trade_logger.log_trade_opened(
            TradeRecord(
                trade_id="no",
                market="m1",
                asset="BTC",
                side="NO",
                entry_price=0.6,
                size=5,
                metadata=metadata,
            )
        )
        broadcaster = FakeBroadcaster()
        engine = BotEngine(
            settings=Settings(paper_mode=True, live_trading=False),
            client=OfficialResolutionClient(),
            trade_logger=trade_logger,
            broadcaster=broadcaster,
            scanner=EmptyScanner(),
            price_feed=FakePriceFeed(),
            oracle=FakeOracle(),
        )

        await engine.run_once()

        yes = trade_logger.get_trade("yes")
        no = trade_logger.get_trade("no")
        assert yes is not None and yes.status == "RESOLVED" and yes.exit_price == 0.0 and yes.pnl == -2.0
        assert no is not None and no.status == "RESOLVED" and no.exit_price == 1.0 and no.pnl == 2.0
        resolved_events = [event for event in broadcaster.events if event[0] == "market_resolved"]
        assert resolved_events
        assert resolved_events[0][1]["winning_side"] == "NO"
        assert resolved_events[0][1]["resolution_source"] == "official_gamma"

    asyncio.run(run())
