"""Async bot runner that keeps trading disabled unless explicitly enabled."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict
from typing import Any

from bot.config.runtime_config import RuntimeConfigStore, validate_runtime_config
from bot.config.settings import Settings
from bot.core.hedge_strategy import HedgeStrategy, MarketSnapshot
from bot.core.polymarket_client import OrderRequest, OrderSide, OrderType, PolymarketClient
from bot.core.risk_manager import AccountRiskState, RiskManager
from bot.core.strategy_registry import StrategyRegistry
from bot.data.market_scanner import MarketCandidate, MarketScanner
from bot.data.trade_logger import TradeLogger, TradeRecord


def sanitize_log_message(message: str) -> str:
    message = re.sub(r"\bmode=\S+\s*", "", message)
    message = re.sub(r"\btrade_key=\S+:([A-Z]+:[A-Za-z0-9]+)", r"market=\1", message)
    return re.sub(r"\s{2,}", " ", message).strip()


class BotEngine:
    """Small lifecycle wrapper for paper/live bot execution."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: Any | None = None,
        trade_logger: TradeLogger | Any | None = None,
        broadcaster: Any | None = None,
        runtime_config_store: RuntimeConfigStore | Any | None = None,
        scanner: Any | None = None,
        price_feed: Any | None = None,
        oracle: Any | None = None,
        risk_manager: RiskManager | None = None,
        strategy: HedgeStrategy | None = None,
        strategy_registry: StrategyRegistry | None = None,
        paper: bool | None = None,
        scan_interval: float = 0.1,
        realtime_interval: float = 0.5,
        capital_per_trade: float = 10.0,
        initial_balance: float = 1_000.0,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.paper = self.settings.paper_mode if paper is None else paper
        self._ensure_live_guard()
        self.client = client or PolymarketClient(settings=self.settings, paper_mode=self.paper)
        self.trade_logger = trade_logger
        self.broadcaster = broadcaster
        self.runtime_config_store = runtime_config_store
        self.scanner = scanner or MarketScanner(self.client, self.settings.market_assets, self.settings.market_timeframes)
        self.price_feed = price_feed
        self.oracle = oracle
        self.risk_manager = risk_manager or RiskManager()
        self.strategy = strategy or HedgeStrategy()
        self.strategy_registry = strategy_registry or StrategyRegistry()
        self.scan_interval = scan_interval
        self.realtime_interval = realtime_interval
        self.capital_per_trade = capital_per_trade
        self.account = AccountRiskState(balance=initial_balance)
        self.running = False
        self.paused = False
        self.solo_log = False
        self.requested_paper_mode = self.paper
        self.last_error: str | None = None
        self.last_skip_reason: str | None = None
        self.last_snapshot_debug: dict[str, Any] | None = None
        self.last_tick_at: float | None = None
        self.ticks = 0
        self.orders_placed = 0
        self.order_attempts = 0
        self.order_failures = 0
        self.last_order_attempt_at: float | None = None
        self.last_order_failure: str | None = None
        self.skipped = 0
        self._task: asyncio.Task[None] = None
        self._realtime_task: asyncio.Task[None] = None
        self._connected = False
        self._active_markets: list = []
        self._cached_markets: list = []
        self._last_scan_at: float = 0.0
        self.SCAN_CACHE_DURATION: float = 10.0
        self._first_window_seen: dict[str, int] = {}
        self.logger = logging.getLogger("walerike.bot_engine")
        self._apply_runtime_config()

    async def start(self) -> dict[str, Any]:
        self._ensure_live_guard()
        self.paused = False
        if self.running:
            return self.status()
        await self._connect()
        self.running = True
        self._task = asyncio.create_task(self._loop())
        if self.realtime_interval > 0:
            self._realtime_task = asyncio.create_task(self._realtime_loop())
        await self._log_event("bot started")
        await self._publish("bot_status", self.status())
        return self.status()

    async def pause(self) -> dict[str, Any]:
        if self.running:
            self.paused = True
            await self._log_event("bot paused")
        await self._publish("bot_status", self.status())
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
        rt_task = self._realtime_task
        self._realtime_task = None
        if rt_task is not None:
            rt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await rt_task
        await self.close()
        await self._log_event("bot stopped")
        await self._publish("bot_status", self.status())
        return self.status()

    async def set_solo_log(self, enabled: bool) -> dict[str, Any]:
        self.solo_log = enabled
        await self._log_event(f"solo_log set to {enabled}")
        await self._publish("bot_status", self.status())
        return self.status()

    async def set_paper_mode(self, paper_mode: bool) -> dict[str, Any]:
        paper_mode = bool(paper_mode)
        previous_paper = self.paper
        previous_settings_paper = self.settings.paper_mode
        previous_client = self.client
        previous_scanner = self.scanner
        was_running = self.running

        if previous_paper == paper_mode:
            self.requested_paper_mode = paper_mode
            self.settings.paper_mode = paper_mode
            self._apply_runtime_config()
            await self._publish("bot_status", self.status())
            return self.status()

        self.paper = paper_mode
        self.settings.paper_mode = paper_mode
        try:
            self._ensure_live_guard()
        except Exception:
            self.paper = previous_paper
            self.settings.paper_mode = previous_settings_paper
            raise

        self.running = False
        self.paused = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        rt_task = self._realtime_task
        self._realtime_task = None
        if rt_task is not None:
            rt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await rt_task
        if previous_client is not None and hasattr(previous_client, "close") and self._connected:
            with contextlib.suppress(Exception):
                await previous_client.close()
        self._connected = False

        try:
            self.client = PolymarketClient(settings=self.settings, paper_mode=paper_mode)
            self.scanner = MarketScanner(self.client, self.settings.market_assets, self.settings.market_timeframes)
            self._apply_runtime_config()
            if was_running:
                await self._connect()
                self.running = True
                self._task = asyncio.create_task(self._loop())
                if self.realtime_interval > 0:
                    self._realtime_task = asyncio.create_task(self._realtime_loop())
        except Exception:
            self.paper = previous_paper
            self.settings.paper_mode = previous_settings_paper
            self.client = previous_client
            self.scanner = previous_scanner
            self._connected = False
            if was_running:
                with contextlib.suppress(Exception):
                    await self._connect()
                    self.running = True
                    self._task = asyncio.create_task(self._loop())
                    if self.realtime_interval > 0:
                        self._realtime_task = asyncio.create_task(self._realtime_loop())
            raise

        await self._log_event(f"trading mode set to {'paper' if paper_mode else 'live'}")
        await self._publish("bot_status", self.status())
        return self.status()

    async def run_once(self) -> dict[str, Any]:
        self.last_tick_at = time.time()
        self.ticks += 1
        self._apply_runtime_config()
        summary = {"scanned": 0, "evaluated": 0, "orders": 0, "skipped": 0}
        now = time.time()
        if now - self._last_scan_at >= self.SCAN_CACHE_DURATION:
            try:
                self._cached_markets = await self.scanner.scan()
                self._last_scan_at = now
            except Exception as exc:  # noqa: BLE001 - runtime must stay alive
                self.last_error = str(exc)
                await self._log_event(f"scan failed: {self.last_error}", level="error")
                await self._publish("bot_error", {"error": self.last_error})
                return summary
        markets = self._cached_markets
        summary["scanned"] = len(markets)
        self._active_markets = markets
        for market in markets:
            tick = self._latest_tick(market.asset)
            if tick is not None:
                market.current_price = float(getattr(tick, "price", 0) or 0)
        await self._settle_paper_trades(markets)
        await self._publish("markets", {"markets": [market.to_dict() if hasattr(market, "to_dict") else asdict(market) for market in markets]})
        for market in markets:
            if self._market_has_ended(market):
                summary["skipped"] += 1
                self.skipped += 1
                continue
            snapshot, snapshot_debug = self._snapshot_with_debug(market)
            if snapshot is None:
                await self._record_skip(str(snapshot_debug.get("reason") or "snapshot_missing"), market, snapshot_debug)
                summary["skipped"] += 1
                self.skipped += 1
                continue
            summary["evaluated"] += 1
            result = await self._evaluate_and_order(snapshot)
            summary["orders"] += result
            if result > 0:
                break
        await self._publish("bot_tick", summary)
        return summary

    def status(self) -> dict[str, Any]:
        requested_paper_mode = self._requested_paper_mode()
        live_trading = bool(getattr(self.settings, "live_trading", False))
        live_blocked = requested_paper_mode is False and not live_trading
        can_live_trade = not self.paper and live_trading
        return {
            "running": self.running,
            "paused": self.paused,
            "paper_mode": self.paper,
            "requested_paper_mode": requested_paper_mode,
            "live_trading": live_trading,
            "can_live_trade": can_live_trade,
            "live_blocked": live_blocked,
            "mode_label": "Live blocked" if live_blocked else "Paper" if self.paper else "Live",
            "solo_log": self.solo_log,
            "status": "paused" if self.paused else "running" if self.running else "stopped",
            "ticks": self.ticks,
            "orders_placed": self.orders_placed,
            "order_attempts": self.order_attempts,
            "order_failures": self.order_failures,
            "last_order_attempt_at": self.last_order_attempt_at,
            "last_order_failure": self.last_order_failure,
            "skipped": self.skipped,
            "last_tick_at": self.last_tick_at,
            "last_error": self.last_error,
            "last_skip_reason": self.last_skip_reason,
            "last_snapshot_debug": self.last_snapshot_debug,
            "account": self.account_summary(),
        }

    def account_summary(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        if self.trade_logger is not None and hasattr(self.trade_logger, "account_stats"):
            with contextlib.suppress(Exception):
                stats = dict(self.trade_logger.account_stats())
        return {
            "balance": self.account.balance,
            "total_exposure": self.account.total_exposure,
            "daily_pnl": self.account.daily_pnl,
            "positions_by_market": dict(self.account.positions_by_market),
            "trade_stats": stats,
        }

    async def close(self) -> None:
        if self.price_feed is not None and hasattr(self.price_feed, "close"):
            with contextlib.suppress(Exception):
                self.price_feed.close()
        if self.client is not None and hasattr(self.client, "close") and self._connected:
            with contextlib.suppress(Exception):
                await self.client.close()
        self._connected = False

    async def clear_open_positions(self) -> dict[str, Any]:
        self.account.positions_by_market.clear()
        self.account.total_exposure = 0.0
        self.account.open_trade_keys.clear()
        if self.trade_logger is not None and hasattr(self.trade_logger, "cancel_open_positions"):
            self.trade_logger.cancel_open_positions()
        await self._log_event("all open positions cleared")
        await self._publish("positions", {"positions": []})
        return {"cleared": True, "positions": []}

    async def _loop(self) -> None:
        try:
            while self.running:
                if not self.paused:
                    await self.run_once()
                await asyncio.sleep(self.scan_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep status visible instead of crashing app
            self.last_error = str(exc)
            self.running = False
            await self._log_event(f"bot loop failed: {self.last_error}", level="error")
            await self._publish("bot_error", {"error": self.last_error})

    async def _realtime_loop(self) -> None:
        try:
            while self.running:
                if not self.paused and self._active_markets:
                    for market in self._active_markets:
                        tick = self._latest_tick(market.asset)
                        if tick is not None:
                            market.current_price = float(getattr(tick, "price", 0) or 0)
                    for market in self._active_markets:
                        from bot.data.market_scanner import _compute_edge, _seconds_left
                        gross_edge, net_edge = _compute_edge(market)
                        market.edge = gross_edge
                        market.net_edge = net_edge
                        market.seconds_left = _seconds_left(market)
                await asyncio.sleep(self.realtime_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"realtime loop: {exc}"
            await self._publish("bot_error", {"error": self.last_error})

    async def _connect(self) -> None:
        if self._connected or not hasattr(self.client, "connect"):
            return
        await self.client.connect()
        self._connected = True
        await self._log_event("client connected")

    async def _record_skip(self, reason: str, market: Any, details: dict[str, Any] | None = None) -> None:
        details = details or {}
        self.last_skip_reason = reason
        self.last_snapshot_debug = details
        await self._log_event(
            f"[SNAPSHOT_SKIP] reason={reason} asset={getattr(market, 'asset', None)}/{getattr(market, 'timeframe', None)} "
            f"market={getattr(market, 'condition_id', None) or getattr(market, 'market_id', None)} details={details}"
        )

    async def _evaluate_and_order(self, snapshot: MarketSnapshot) -> int:
        mode = "PAPER" if self.paper else "LIVE"
        trade_key = f"{snapshot.market_id}:{snapshot.asset}:{snapshot.timeframe}"

        momentum = self._momentum(snapshot.asset)
        signals = self.strategy_registry.evaluate(snapshot, self.capital_per_trade, momentum) if self.strategy_registry is not None else []
        has_registry_scope = bool(self.strategy_registry is not None and self.strategy_registry.has_strategy_scope(snapshot))
        if not signals and not has_registry_scope:
            signals = [self.strategy.evaluate(snapshot, self.capital_per_trade, momentum)]

        await self._log_event(
            f"[BET_EVAL] mode={mode} trade_key={trade_key} strategies={len(signals)} "
            f"yes={snapshot.yes_price:.3f} no={snapshot.no_price:.3f} momentum={momentum:.4f}"
        )

        if not signals and has_registry_scope and self.strategy_registry is not None:
            for diagnostic in self.strategy_registry.skip_diagnostics(snapshot):
                await self._log_event(
                    f"[BET_SKIP] mode={mode} trade_key={trade_key} strategy={diagnostic.get('strategy')} "
                    f"reason={diagnostic.get('reason')} requirement={diagnostic.get('requirement')} actual={diagnostic.get('actual')}"
                )

        placed = 0
        max_orders = self.strategy_registry.max_orders_per_tick() if self.strategy_registry is not None else 2
        for signal in signals:
            if placed >= max_orders:
                break
            placed += await self._execute_signal(snapshot, signal, mode, trade_key, max_orders - placed)
        return placed

    async def _execute_signal(self, snapshot: MarketSnapshot, signal: Any, mode: str, trade_key: str, remaining_orders: int) -> int:
        if signal.yes_size > 0 and signal.no_size > 0 and remaining_orders < 2:
            await self._log_event(f"[BET_DECISION] action=PAIR_SKIPPED trade_key={trade_key} reason=order_cap_insufficient")
            return 0

        decision = self.risk_manager.check_trade(
            market_id=snapshot.market_id,
            asset=snapshot.asset,
            yes_price=snapshot.yes_price,
            no_price=snapshot.no_price,
            requested_size=min(signal.yes_size + signal.no_size, self.capital_per_trade),
            state=self.account,
            oracle_discrepancy_pct=self._oracle_discrepancy(snapshot),
            trade_key=trade_key,
            signal_mode=signal.mode,
        )

        if self.solo_log or signal.yes_size <= 0 and signal.no_size <= 0:
            return 0
        if not decision.allowed:
            await self._log_event(
                f"[BET_SKIP] mode={mode} trade_key={trade_key} strategy={getattr(signal, 'strategy_name', None) or 'default'} "
                f"reason=risk_rejected requirement={'; '.join(decision.reasons)} "
                f"actual=requested_size={signal.yes_size + signal.no_size:.2f}"
            )
            return 0

        adjusted_size = decision.adjusted_size
        requested_size = signal.yes_size + signal.no_size
        if adjusted_size is not None and 0 < adjusted_size < requested_size:
            scale = adjusted_size / requested_size
            signal.yes_size *= scale
            signal.no_size *= scale

        approved_side = "BOTH" if signal.yes_size > 0 and signal.no_size > 0 else "YES" if signal.yes_size > 0 else "NO" if signal.no_size > 0 else "NONE"
        approved_size = signal.yes_size + signal.no_size
        approved_price = snapshot.yes_price if signal.yes_size > 0 else snapshot.no_price
        approved_token = f"{snapshot.yes_token_id},{snapshot.no_token_id}" if approved_side == "BOTH" else snapshot.yes_token_id if signal.yes_size > 0 else snapshot.no_token_id
        await self._log_event(
            f"[BET_DECISION] action=APPROVED mode={mode} trade_key={trade_key} side={approved_side} "
            f"price={approved_price:.3f} size={approved_size:.2f} token_id={approved_token} reasons={signal.reasons} risk={decision.reasons}"
        )
        await self._log_event(f"[TRADE] APPROVED: placing {signal.yes_size:.2f} YES @ {snapshot.yes_price:.3f} and {signal.no_size:.2f} NO @ {snapshot.no_price:.3f} for {trade_key}")
        placed = 0
        yes_placed = 0
        if signal.yes_size > 0 and remaining_orders > placed:
            result = await self._place_leg(snapshot, snapshot.yes_token_id, OrderSide.BUY, snapshot.yes_price, signal.yes_size, "YES")
            placed += result
            yes_placed = result
            if result and hasattr(self.strategy, "record_buy"):
                self.strategy.record_buy(snapshot, "YES", snapshot.yes_price, signal.yes_size)
        if signal.yes_size > 0 and signal.no_size > 0 and not yes_placed:
            await self._log_event(f"[BET_DECISION] action=PAIR_ABORTED trade_key={trade_key} reason=yes_leg_not_placed")
            return placed
        if signal.no_size > 0 and remaining_orders > placed:
            result = await self._place_leg(snapshot, snapshot.no_token_id, OrderSide.BUY, snapshot.no_price, signal.no_size, "NO")
            placed += result
            if result and hasattr(self.strategy, "record_buy"):
                self.strategy.record_buy(snapshot, "NO", snapshot.no_price, signal.no_size)
        if placed:
            self.account.open_trade_keys.add(trade_key)
            self.account.last_trade_ts_by_asset[snapshot.asset] = time.time()
            await self._log_event(f"placed {placed} orders for {trade_key}")
        return placed

    async def _place_leg(self, snapshot: MarketSnapshot, token_id: str, side: OrderSide, price: float, size: float, label: str) -> int:
        if not token_id:
            await self._log_event(f"[SKIP] {label} leg: missing token_id")
            return 0
        if size < 0.01:
            await self._log_event(f"[SKIP] {label} leg: size {size:.2f} below minimum 0.01")
            return 0
        if self.paper and side is OrderSide.BUY:
            available = snapshot.yes_liquidity if label == "YES" else snapshot.no_liquidity
            if size > available:
                await self._log_event(f"[SKIP] {label} leg: paper book liquidity {available:.2f} below requested size {size:.2f}")
                return 0
        expiration = int(time.time()) + 120
        order_price = max(0.01, min(0.99, price))
        client_order_id = f"walerike-{uuid.uuid4().hex}"
        mode = "PAPER" if self.paper else "LIVE"
        self.order_attempts += 1
        self.last_order_attempt_at = time.time()
        attempt_payload = {
            "market": snapshot.market_id,
            "asset": snapshot.asset,
            "timeframe": snapshot.timeframe,
            "side": label,
            "order_side": side.value,
            "price": order_price,
            "size": size,
            "token_id": token_id,
            "mode": mode,
            "client_order_id": client_order_id,
            "attempt": self.order_attempts,
        }
        await self._log_event(
            f"[ORDER_ATTEMPT] attempt={self.order_attempts} mode={mode} market={snapshot.market_id} "
            f"asset={snapshot.asset}/{snapshot.timeframe} side={label} order_side={side.value} "
            f"price={order_price:.3f} size={size:.2f} token_id={token_id} client_order_id={client_order_id}"
        )
        await self._publish("order_attempt", attempt_payload)
        try:
            order = await self.client.place_order(
                OrderRequest(
                    market=snapshot.market_id,
                    asset_id=token_id,
                    side=side,
                    price=order_price,
                    size=size,
                    order_type=OrderType.GTD,
                    expiration=expiration,
                    client_order_id=client_order_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - live order rejects must not stop the bot loop
            self.last_error = f"order failed {label} {snapshot.asset}/{snapshot.timeframe}: {exc}"
            self.last_order_failure = self.last_error
            self.order_failures += 1
            await self._log_event(f"[ORDER_FAILED] attempt={self.order_attempts} mode={mode} market={snapshot.market_id} side={label} price={order_price:.3f} size={size:.2f} error={exc}", level="error")
            await self._log_event(self.last_error, level="error")
            await self._publish("order_failed", {**attempt_payload, "error": str(exc)})
            await self._publish("bot_error", {"error": self.last_error})
            return 0
        if not order.order_id:
            self.last_error = f"order failed {label} {snapshot.asset}/{snapshot.timeframe}: missing order id response={order.raw}"
            self.last_order_failure = self.last_error
            self.order_failures += 1
            await self._log_event(f"[ORDER_FAILED] attempt={self.order_attempts} mode={mode} market={snapshot.market_id} side={label} price={order_price:.3f} size={size:.2f} error=missing_order_id response={order.raw}", level="error")
            await self._log_event(self.last_error, level="error")
            await self._publish("order_failed", {**attempt_payload, "error": "missing_order_id", "response": order.raw})
            await self._publish("bot_error", {"error": self.last_error})
            return 0
        await self._log_event(f"[ORDER_ACCEPTED] attempt={self.order_attempts} mode={mode} order_id={order.order_id} status={order.status} market={snapshot.market_id} side={label} price={order_price:.3f} size={size:.2f}")
        await self._publish("order_accepted", {**attempt_payload, "order_id": order.order_id, "status": order.status, "raw": order.raw})
        self.orders_placed += 1
        self.account.total_exposure += price * size
        self.account.positions_by_market[snapshot.market_id] = self.account.positions_by_market.get(snapshot.market_id, 0.0) + size
        if self.trade_logger is not None and hasattr(self.trade_logger, "log_trade_opened"):
            fee_rate = float(getattr(getattr(self.strategy, "config", None), "taker_fee_rate", 0.072))
            fee_paid = self.strategy.fee_per_share(price, fee_rate) * size if hasattr(self.strategy, "fee_per_share") else 0.0
            self.trade_logger.log_trade_opened(
                TradeRecord(
                    trade_id=order.order_id,
                    market=snapshot.market_id,
                    asset=snapshot.asset,
                    side=label,
                    entry_price=price,
                    size=size,
                    metadata={
                        "paper": self.paper,
                        "token_id": token_id,
                        "timeframe": snapshot.timeframe,
                        "market_slug": snapshot.market_slug,
                        "end_date": snapshot.end_date,
                        "price_to_beat": await self._target_price_for_snapshot(snapshot),
                        "window_start_timestamp": snapshot.window_start_timestamp,
                        "opened_spot_price": snapshot.spot_price,
                        "fee_rate": fee_rate,
                        "fee_paid": fee_paid,
                    },
                )
            )
        await self._publish("order_placed", {"order_id": order.order_id, "market": snapshot.market_id, "asset": snapshot.asset, "side": label, "price": price, "size": size})
        await self._publish("positions", {"positions": self._positions_payload()})
        return 1

    def _positions_payload(self) -> list[dict[str, Any]]:
        if self.trade_logger is not None and hasattr(self.trade_logger, "list_positions"):
            with contextlib.suppress(Exception):
                return [asdict(record) for record in self.trade_logger.list_positions()]
        return [
            {"market": market, "asset": "", "side": "TOTAL", "size": size, "avg_price": 0.0, "unrealized_pnl": 0.0}
            for market, size in self.account.positions_by_market.items()
        ]

    def _snapshot(self, market: MarketCandidate) -> MarketSnapshot | None:
        snapshot, _debug = self._snapshot_with_debug(market)
        return snapshot

    def _snapshot_with_debug(self, market: MarketCandidate) -> tuple[MarketSnapshot | None, dict[str, Any]]:
        tick = self._latest_tick(market.asset)
        oracle_price = self._oracle_price(market.asset)
        debug: dict[str, Any] = {
            "asset": market.asset,
            "timeframe": market.timeframe,
            "market_id": market.condition_id or market.market_id,
            "market_slug": market.market_slug or market.slug or market.event_slug,
            "has_price_feed": self.price_feed is not None,
            "has_oracle": self.oracle is not None,
            "tick_price": float(getattr(tick, "price", 0) or 0) if tick is not None else None,
            "oracle_price": float(getattr(oracle_price, "price", 0) or 0) if oracle_price is not None else None,
            "best_ask_up": market.best_ask_up,
            "best_ask_down": market.best_ask_down,
            "up_price": market.up_price,
            "down_price": market.down_price,
            "up_token_id": market.up_token_id,
            "down_token_id": market.down_token_id,
            "tokens_count": len(market.tokens),
        }
        if tick is None:
            debug["reason"] = "tick_missing"
            return None, debug
        if oracle_price is None:
            debug["reason"] = "oracle_missing"
            return None, debug
        up = self._token(market, "up") or self._token(market, "yes")
        down = self._token(market, "down") or self._token(market, "no")
        up_token_id = str(market.up_token_id or (up or {}).get("token_id") or (up or {}).get("asset_id") or (up or {}).get("id") or (up or {}).get("value") or "")
        down_token_id = str(market.down_token_id or (down or {}).get("token_id") or (down or {}).get("asset_id") or (down or {}).get("id") or (down or {}).get("value") or "")
        up_price = market.best_ask_up if market.best_ask_up is not None else market.up_price if market.up_price is not None else self._price(up, market.raw, "yes")
        down_price = market.best_ask_down if market.best_ask_down is not None else market.down_price if market.down_price is not None else self._price(down, market.raw, "no")
        debug.update({"resolved_up_token_id": up_token_id or None, "resolved_down_token_id": down_token_id or None, "resolved_up_price": up_price, "resolved_down_price": down_price})
        if not up_token_id:
            debug["reason"] = "yes_token_missing"
            return None, debug
        if not down_token_id:
            debug["reason"] = "no_token_missing"
            return None, debug
        if up_price is None:
            debug["reason"] = "yes_price_missing"
            return None, debug
        if down_price is None:
            debug["reason"] = "no_price_missing"
            return None, debug
        yes_liquidity = self._buy_liquidity_at_price(
            market.asks_up,
            up_price,
            fallback=self._liquidity_fallback(up, market),
            book_price=market.best_ask_up,
        )
        no_liquidity = self._buy_liquidity_at_price(
            market.asks_down,
            down_price,
            fallback=self._liquidity_fallback(down, market),
            book_price=market.best_ask_down,
        )
        debug.update({"reason": "ok", "yes_liquidity": yes_liquidity, "no_liquidity": no_liquidity})
        return MarketSnapshot(
            market_id=market.condition_id or market.market_id,
            asset=market.asset,
            timeframe=market.timeframe or "unknown",
            yes_token_id=up_token_id,
            no_token_id=down_token_id,
            yes_price=up_price,
            no_price=down_price,
            yes_liquidity=yes_liquidity,
            no_liquidity=no_liquidity,
            spot_price=float(getattr(tick, "price")),
            oracle_price=float(getattr(oracle_price, "price")),
            timestamp=time.time(),
            market_slug=market.market_slug or market.slug or market.event_slug,
            end_date=market.end_date,
            price_to_beat=market.price_to_beat,
            window_start_timestamp=market.window_start_timestamp,
        ), debug

    @staticmethod
    def _buy_liquidity_at_price(levels: list[dict[str, float]], limit_price: float, *, fallback: float, book_price: float | None) -> float:
        if levels:
            return sum(level["size"] for level in levels if level["price"] <= limit_price)
        if book_price is not None:
            return 0.0
        return fallback

    @staticmethod
    def _liquidity_fallback(token: dict[str, Any] | None, market: MarketCandidate) -> float:
        for value in (
            (token or {}).get("liquidity"),
            (token or {}).get("size"),
            market.liquidity,
            market.raw.get("liquidity"),
        ):
            if value is not None:
                with contextlib.suppress(TypeError, ValueError):
                    return float(value)
        return 100.0

    async def _settle_paper_trades(self, markets: list[MarketCandidate]) -> None:
        if not self.paper or self.trade_logger is None or not hasattr(self.trade_logger, "list_trades"):
            return
        if not hasattr(self.trade_logger, "resolve_market"):
            return

        market_by_id = {market.condition_id or market.market_id: market for market in markets}
        open_trades = self.trade_logger.list_trades(status="OPEN")
        market_ids = sorted({trade.market for trade in open_trades})
        for market_id in market_ids:
            trades = [trade for trade in open_trades if trade.market == market_id]
            metadata = trades[0].metadata or {}
            market = market_by_id.get(market_id)
            asset = str(metadata.get("asset") or getattr(market, "asset", "") or trades[0].asset)
            end_date = getattr(market, "end_date", None) or metadata.get("end_date")
            price_to_beat = getattr(market, "price_to_beat", None) if market is not None else None
            if price_to_beat is None:
                price_to_beat = metadata.get("price_to_beat")
            if price_to_beat is None:
                price_to_beat = await self._target_price_for_metadata(asset, metadata)

            official = await self._official_market_resolution(market, metadata)
            if official is None and not self._end_date_has_passed(end_date):
                continue
            if official is not None:
                final_price = official.get("resolved_price")
                target = float(price_to_beat) if price_to_beat is not None else 0.0
                winning_side = str(official["winning_side"])
                resolution_source = str(official["resolution_source"])
            else:
                if price_to_beat is None:
                    await self._log_event(f"settlement skipped market={market_id}: missing price_to_beat")
                    continue
                tick = self._latest_tick(asset)
                if tick is None:
                    await self._log_event(f"settlement skipped market={market_id}: missing final price for {asset}")
                    continue
                final_price = float(getattr(tick, "price", 0) or 0)
                target = float(price_to_beat)
                winning_side = "YES" if final_price >= target else "NO"
                resolution_source = "local_simulation"

            resolved = self.trade_logger.resolve_market(
                market_id,
                winning_side,
                resolved_price=float(final_price or 0.0),
                price_to_beat=target,
            )
            if not resolved:
                continue

            pnl = sum(float(trade.pnl or 0.0) for trade in resolved)
            cost = sum(float(trade.entry_price) * float(trade.size) for trade in resolved)
            self.account.daily_pnl += pnl
            self.account.balance += pnl
            self.account.total_exposure = max(0.0, self.account.total_exposure - cost)
            self.account.positions_by_market.pop(market_id, None)
            self.account.open_trade_keys = {key for key in self.account.open_trade_keys if not key.startswith(f"{market_id}:")}

            payload = {
                "market": market_id,
                "asset": asset,
                "winning_side": winning_side,
                "resolved_price": final_price,
                "price_to_beat": target,
                "pnl": pnl,
                "trades": [asdict(trade) for trade in resolved],
                "resolution_source": resolution_source,
            }
            final_display = f"{float(final_price):.2f}" if final_price is not None else "official"
            await self._log_event(f"settled market={market_id} winner={winning_side} final={final_display} target={target:.2f} pnl={pnl:.2f} source={resolution_source}")
            await self._publish("market_resolved", payload)
            await self._publish("trade_resolved", payload)
            await self._publish("positions", {"positions": self._positions_payload()})
            await self._publish("bot_status", self.status())

    def _is_first_window_for_market(self, asset: str, timeframe: str, window_start: int) -> bool:
        key = f"{asset}:{timeframe}"
        if key not in self._first_window_seen:
            self._first_window_seen[key] = window_start
            return True
        return self._first_window_seen[key] == window_start

    async def _target_price_for_snapshot(self, snapshot: MarketSnapshot) -> float | None:
        if snapshot.price_to_beat is not None:
            return float(snapshot.price_to_beat)
        window_ts = snapshot.window_start_timestamp
        is_first = self._is_first_window_for_market(snapshot.asset, snapshot.timeframe, window_ts) if window_ts else False
        price, window_start = await self._resolve_target_price(
            snapshot.asset,
            snapshot.timeframe,
            snapshot.market_slug,
            snapshot.window_start_timestamp,
            is_first_window=is_first,
        )
        if price is not None:
            snapshot.price_to_beat = price
        if window_start is not None:
            snapshot.window_start_timestamp = window_start
        return price

    async def _target_price_for_metadata(self, asset: str, metadata: dict[str, Any]) -> float | None:
        window_ts = self._int_or_none(metadata.get("window_start_timestamp"))
        timeframe = str(metadata.get("timeframe") or "")
        is_first = self._is_first_window_for_market(asset, timeframe, window_ts) if window_ts else False
        price, window_start = await self._resolve_target_price(
            asset,
            timeframe,
            str(metadata.get("market_slug") or "") or None,
            window_ts,
            is_first_window=is_first,
        )
        if price is not None:
            metadata["price_to_beat"] = price
        if window_start is not None:
            metadata["window_start_timestamp"] = window_start
        return price

    async def _resolve_target_price(self, asset: str, timeframe: str | None, slug: str | None, window_start: int | None, is_first_window: bool = False) -> tuple[float | None, int | None]:
        slug_window = self._window_start_from_slug(slug)
        window_start = window_start or slug_window
        if window_start is None:
            return None, None

        price = await self._fetch_crypto_api_target(asset, timeframe, window_start)
        if price is not None:
            return price, window_start

        if is_first_window and slug and hasattr(self.client, "fetch_page_html"):
            with contextlib.suppress(Exception):
                html = await self.client.fetch_page_html(slug)
                from bot.web.server import _scrape_target_price_from_html

                scraped, _source = _scrape_target_price_from_html(html, slug)
                if scraped is not None:
                    return float(scraped), window_start
        return None, window_start

    async def _fetch_crypto_api_target(self, asset: str, timeframe: str | None, window_start: int) -> float | None:
        if not hasattr(self.client, "fetch_crypto_price"):
            return None
        tf = str(timeframe or "").lower()
        variants = {"5m": ("fiveminute", 300), "15m": ("fifteen", 900)}
        variant = variants.get(tf)
        if variant is None:
            return None
        try:
            from datetime import datetime, timedelta, timezone

            variant_name, seconds = variant
            start = datetime.fromtimestamp(float(window_start), timezone.utc)
            end = start + timedelta(seconds=seconds)
            payload = await self.client.fetch_crypto_price(
                str(asset).upper(),
                start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                variant_name,
                end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            if isinstance(payload, dict) and payload.get("openPrice") is not None:
                return float(payload["openPrice"])
        except Exception as exc:  # noqa: BLE001 - target fetch is best-effort
            await self._log_event(f"target price fetch failed asset={asset} window={window_start}: {exc}")
        return None

    @staticmethod
    def _window_start_from_slug(slug: str | None) -> int | None:
        match = re.search(r"-(\d{10})$", str(slug or ""))
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _end_date_has_passed(end_date: Any) -> bool:
        if not end_date:
            return False
        try:
            from datetime import datetime, timezone

            if isinstance(end_date, (int, float)):
                return float(end_date) <= time.time()
            parsed = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp() <= time.time()
        except Exception:
            return False

    def _market_has_ended(self, market: MarketCandidate) -> bool:
        return self._end_date_has_passed(getattr(market, "end_date", None))

    async def _official_market_resolution(self, market: MarketCandidate | None, metadata: dict[str, Any]) -> dict[str, Any] | None:
        raw_market: dict[str, Any] | None = None
        slug = str(metadata.get("market_slug") or "").strip()
        if market is not None:
            slug = slug or str(market.market_slug or market.slug or market.event_slug or "").strip()
            if isinstance(market.raw, dict):
                raw = market.raw.get("market") if isinstance(market.raw.get("market"), dict) else market.raw
                raw_market = raw if isinstance(raw, dict) else None

        if slug and hasattr(self.client, "fetch_market_by_slug"):
            with contextlib.suppress(Exception):
                fetched = await self.client.fetch_market_by_slug(slug)
                if isinstance(fetched, dict):
                    raw_market = fetched

        return self._parse_official_resolution(raw_market)

    @classmethod
    def _parse_official_resolution(cls, market: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(market, dict):
            return None
        if isinstance(market.get("markets"), list) and market["markets"]:
            first = next((item for item in market["markets"] if isinstance(item, dict)), None)
            if first is not None:
                market = first

        for key in ("winningOutcome", "winning_outcome", "winner", "winning", "resolvedOutcome", "resolved_outcome", "result", "resolution"):
            winner = cls._winner_from_value(market.get(key))
            if winner is not None:
                return {"winning_side": winner, "resolved_price": None, "resolution_source": "official_gamma"}

        outcomes = cls._json_list(market.get("outcomes"))
        prices = cls._json_list(market.get("outcomePrices"))
        if len(outcomes) >= 2 and len(prices) >= 2:
            parsed_prices = [cls._float(value) for value in prices]
            if all(value is not None for value in parsed_prices):
                best_price = max(parsed_prices)  # type: ignore[arg-type]
                worst_price = min(parsed_prices)  # type: ignore[arg-type]
                closed = cls._boolish(market.get("closed")) or cls._boolish(market.get("resolved")) or cls._boolish(market.get("archived"))
                if closed and best_price >= 0.9 and worst_price <= 0.1:
                    winner_index = parsed_prices.index(best_price)
                    winner = cls._winner_from_value(outcomes[winner_index])
                    if winner is not None:
                        return {"winning_side": winner, "resolved_price": None, "resolution_source": "official_gamma"}

        return None

    @staticmethod
    def _winner_from_value(value: Any) -> str | None:
        if isinstance(value, list):
            for item in value:
                winner = BotEngine._winner_from_value(item)
                if winner is not None:
                    return winner
            return None
        if isinstance(value, dict):
            for key in ("outcome", "name", "label", "value", "winner"):
                winner = BotEngine._winner_from_value(value.get(key))
                if winner is not None:
                    return winner
            return None
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in {"yes", "up", "higher", "above", "long", "1", "true"}:
            return "YES"
        if text in {"no", "down", "lower", "below", "short", "0", "false"}:
            return "NO"
        return None

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError):
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value if isinstance(value, list) else []

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _boolish(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _latest_tick(self, asset: str) -> Any | None:
        latest = getattr(self.price_feed, "latest", None)
        if isinstance(latest, dict):
            return latest.get(asset.upper()) or latest.get(asset.lower()) or latest.get(asset)
        if hasattr(self.price_feed, "get_latest"):
            return self.price_feed.get_latest(asset)
        return None

    def _oracle_price(self, asset: str) -> Any | None:
        if self.oracle is not None and hasattr(self.oracle, "get_cached_price"):
            cached = self.oracle.get_cached_price(asset)
            if cached is not None:
                return cached
        if self.oracle is not None and hasattr(self.oracle, "read_price"):
            with contextlib.suppress(Exception):
                return self.oracle.read_price(asset)
        if self.price_feed is not None:
            tick = self._latest_tick(asset)
            if tick is not None:
                from bot.data.price_aggregator import OraclePrice
                import time
                return OraclePrice(asset=asset.upper(), price=float(getattr(tick, "price", 0) or 0), round_id=0, updated_at=time.time(), stale=False)
        return None

    def _momentum(self, asset: str) -> float:
        if self.price_feed is not None and hasattr(self.price_feed, "momentum_pct"):
            with contextlib.suppress(Exception):
                return float(self.price_feed.momentum_pct(asset))
        return 0.0

    @staticmethod
    def _token(market: MarketCandidate, target: str) -> dict[str, Any] | None:
        fallback_index = 0 if target in {"yes", "up"} else 1
        fallback = market.tokens[fallback_index] if len(market.tokens) > fallback_index else None
        for token in market.tokens:
            text = " ".join(str(token.get(key, "")) for key in ("outcome", "name", "side", "label")).lower()
            if target in text:
                return token
        return fallback

    @staticmethod
    def _price(token: dict[str, Any] | None, raw: dict[str, Any], side: str) -> float | None:
        if token is None:
            return None
        for source in (token, raw):
            for key in ("price", f"{side}_price", f"{side}Price", "bestAsk", "bestBid"):
                value = source.get(key)
                if value is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        return float(value)
        return None

    @staticmethod
    def _oracle_discrepancy(snapshot: MarketSnapshot) -> float:
        if snapshot.oracle_price <= 0:
            return 0.0
        return abs(snapshot.spot_price - snapshot.oracle_price) / snapshot.oracle_price * 100.0

    async def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.broadcaster is None or not hasattr(self.broadcaster, "publish"):
            return
        with contextlib.suppress(Exception):
            await self.broadcaster.publish(event_type, payload)

    async def _log_event(self, message: str, *, level: str = "info") -> None:
        message = sanitize_log_message(message)
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)
        await self._publish("log", {"level": level, "message": message})

    def _apply_runtime_config(self) -> None:
        if self.runtime_config_store is None or not hasattr(self.runtime_config_store, "load"):
            return
        with contextlib.suppress(Exception):
            config = self.runtime_config_store.load()
            validate_runtime_config(config)
            self.requested_paper_mode = bool(config.paper_mode)
            self.capital_per_trade = float(config.capital_per_trade)
            self.solo_log = bool(config.solo_log)
            if hasattr(self.scanner, "set_enabled_markets"):
                self.scanner.set_enabled_markets(config.enabled_markets)
            elif hasattr(self.scanner, "configure"):
                self.scanner.configure(enabled_markets=config.enabled_markets)
            if hasattr(self.strategy, "config"):
                self.strategy.config.arbitrage_yes_no_sum = 1.0 - float(config.min_margin_for_arbitrage)
                self.strategy.config.entry_threshold = float(config.entry_threshold)
                self.strategy.config.max_sum_avg = float(config.max_sum_avg)
                self.strategy.config.max_buys_per_side = int(config.max_buys_per_side)
                self.strategy.config.reversal_delta = float(config.reversal_delta)
                self.strategy.config.depth_buy_discount_percent = float(config.depth_buy_discount_percent)
                self.strategy.config.second_side_buffer = float(config.second_side_buffer)
                self.strategy.config.second_side_time_threshold_ms = float(config.second_side_time_threshold_ms)
                self.strategy.config.dynamic_threshold_boost = float(config.dynamic_threshold_boost)
            if hasattr(self.strategy_registry, "configure"):
                self.strategy_registry.configure(config.strategy_groups, config.strategies)
            if hasattr(self.risk_manager, "config"):
                self.risk_manager.config.min_yes_no_sum = 1.0 - float(config.min_margin_for_arbitrage)
                self.risk_manager.config.hedge_min_yes_no_sum = 2.0 - float(config.min_margin_for_arbitrage)

    def _requested_paper_mode(self) -> bool:
        if self.runtime_config_store is None or not hasattr(self.runtime_config_store, "load"):
            return self.requested_paper_mode
        with contextlib.suppress(Exception):
            config = self.runtime_config_store.load()
            validate_runtime_config(config)
            self.requested_paper_mode = bool(config.paper_mode)
        return self.requested_paper_mode

    def _ensure_live_guard(self) -> None:
        live_env = os.getenv("POLYMARKET_LIVE_TRADING", "").strip().lower() in {"1", "true", "yes", "on"}
        if not self.paper and (not live_env or not getattr(self.settings, "live_trading", False)):
            raise RuntimeError("Live trading requires --live/paper=False and POLYMARKET_LIVE_TRADING=1")
