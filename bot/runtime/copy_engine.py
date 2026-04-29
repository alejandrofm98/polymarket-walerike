from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

from bot.config.runtime_config import RuntimeConfigStore, validate_runtime_config
from bot.core.polymarket_client import OrderRequest, OrderSide, OrderType
from bot.data.polymarket_data_client import PolymarketDataClient, WalletActivity


class CopyTradingEngine:
    def __init__(
        self,
        *,
        client: Any,
        data_client: PolymarketDataClient | Any,
        runtime_config_store: RuntimeConfigStore | Any,
        broadcaster: Any | None = None,
        user_portfolio_value: Callable[[], float] | None = None,
        paper: bool = True,
    ) -> None:
        self.client = client
        self.data_client = data_client
        self.runtime_config_store = runtime_config_store
        self.broadcaster = broadcaster
        self.user_portfolio_value = user_portfolio_value or (lambda: 0.0)
        self.paper = paper
        self.running = False
        self.paused = False
        self.ticks = 0
        self.orders_placed = 0
        self.skipped = 0
        self.last_error: str | None = None
        self.last_tick_at: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._seen_events: set[str] = set()
        self._copied_market_sides: set[tuple[str, str]] = set()
        self._copied_positions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.logger = logging.getLogger("walerike.copy_engine")

    async def start(self) -> dict[str, Any]:
        if self.running:
            return self.status()
        self.running = True
        self.paused = False
        self._task = asyncio.create_task(self._loop())
        await self._log_event("copy bot started")
        return self.status()

    async def pause(self) -> dict[str, Any]:
        self.paused = True
        await self._log_event("copy bot paused")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self.running = False
        self.paused = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._log_event("copy bot stopped")
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "paused": self.paused,
            "paper_mode": self.paper,
            "status": "paused" if self.paused else "running" if self.running else "stopped",
            "ticks": self.ticks,
            "orders_placed": self.orders_placed,
            "skipped": self.skipped,
            "last_error": self.last_error,
            "last_tick_at": self.last_tick_at,
        }

    async def run_once(self) -> dict[str, int]:
        self.ticks += 1
        self.last_tick_at = time.time()
        config = self.runtime_config_store.load()
        validate_runtime_config(config)
        summary = {"wallets": 0, "events": 0, "copied": 0, "closed": 0, "duplicates": 0, "skipped": 0}
        for wallet in config.copy_wallets:
            if not wallet.get("enabled"):
                continue
            summary["wallets"] += 1
            try:
                events = await self.data_client.wallet_activity(wallet["address"])
                leader_portfolio = await self.data_client.portfolio_value(wallet["address"])
            except Exception as exc:
                self.last_error = str(exc)
                summary["skipped"] += 1
                await self._log_event(f"copy wallet poll failed wallet={wallet['address']} error={exc}", level="error")
                continue
            for activity in events:
                summary["events"] += 1
                if activity.event_id in self._seen_events:
                    continue
                self._seen_events.add(activity.event_id)
                if activity.action == "buy":
                    result = await self._copy_buy(wallet, activity, leader_portfolio)
                    summary[result] += 1
                elif activity.action == "sell":
                    result = await self._copy_sell(wallet, activity)
                    summary[result] += 1
        return summary

    async def _copy_buy(self, wallet: dict[str, Any], activity: WalletActivity, leader_portfolio: float | None) -> str:
        market_side = (activity.market_id, activity.side)
        if market_side in self._copied_market_sides:
            self.skipped += 1
            await self._log_event(f"[COPY_SKIP] reason=duplicate_market_side wallet={wallet['address']} market={activity.market_id} side={activity.side}")
            return "duplicates"
        notional = self._copy_notional(wallet, activity, leader_portfolio)
        if notional <= 0:
            self.skipped += 1
            await self._log_event(f"[COPY_SKIP] reason=invalid_size wallet={wallet['address']} leader_event={activity.event_id}")
            return "skipped"
        if activity.price <= 0:
            self.skipped += 1
            await self._log_event(f"[COPY_SKIP] reason=zero_price wallet={wallet['address']} leader_event={activity.event_id}")
            return "skipped"
        size = notional / activity.price
        try:
            order = await self.client.place_order(
                OrderRequest(
                    market=activity.market_id,
                    asset_id=activity.token_id or "",
                    side=OrderSide.BUY,
                    price=activity.price,
                    size=size,
                    order_type=OrderType.GTD,
                    expiration=int(time.time()) + 120,
                )
            )
        except Exception as exc:
            self.last_error = f"order failed: {exc}"
            await self._log_event(f"[COPY_ERROR] action=buy wallet={wallet['address']} market={activity.market_id} error={exc}", level="error")
            return "skipped"
        self.orders_placed += 1
        self._copied_market_sides.add(market_side)
        self._copied_positions[(wallet["address"], activity.market_id, activity.side)] = {
            "order_id": order.order_id,
            "size": size,
            "token_id": activity.token_id,
            "price": activity.price,
        }
        await self._log_event(f"[COPY_TRADE] action=buy wallet={wallet['address']} market={activity.market_id} side={activity.side} price={activity.price:.3f} size={size:.2f}")
        return "copied"

    async def _copy_sell(self, wallet: dict[str, Any], activity: WalletActivity) -> str:
        key = (wallet["address"], activity.market_id, activity.side)
        position = self._copied_positions.get(key)
        if not position:
            return "skipped"
        size = min(float(position["size"]), activity.size)
        try:
            await self.client.place_order(
                OrderRequest(
                    market=activity.market_id,
                    asset_id=position.get("token_id") or activity.token_id or "",
                    side=OrderSide.SELL,
                    price=activity.price,
                    size=size,
                    order_type=OrderType.GTD,
                    expiration=int(time.time()) + 120,
                )
            )
        except Exception as exc:
            self.last_error = f"order failed: {exc}"
            await self._log_event(f"[COPY_ERROR] action=sell wallet={wallet['address']} market={activity.market_id} error={exc}", level="error")
            return "skipped"
        self.orders_placed += 1
        self._copied_positions.pop(key, None)
        self._copied_market_sides.discard((activity.market_id, activity.side))
        await self._log_event(f"[COPY_TRADE] action=sell wallet={wallet['address']} market={activity.market_id} side={activity.side} price={activity.price:.3f} size={size:.2f}")
        return "closed"

    def _copy_notional(self, wallet: dict[str, Any], activity: WalletActivity, leader_portfolio: float | None) -> float:
        if wallet.get("sizing_mode") == "fixed":
            return float(wallet.get("fixed_amount") or 0.0)
        if not leader_portfolio or leader_portfolio <= 0:
            return 0.0
        return self.user_portfolio_value() * (activity.notional / leader_portfolio)

    async def _loop(self) -> None:
        while self.running:
            if not self.paused:
                await self.run_once()
            config = self.runtime_config_store.load()
            await asyncio.sleep(float(getattr(config, "poll_interval_seconds", 5.0)))

    async def _log_event(self, message: str, *, level: str = "info") -> None:
        getattr(self.logger, level, self.logger.info)(message)
        if self.broadcaster is not None and hasattr(self.broadcaster, "publish"):
            await self.broadcaster.publish("log", {"level": level, "message": message})