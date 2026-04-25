"""FastAPI application factory for dashboard server."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional until web server use
    FastAPI = None  # type: ignore[assignment]
    StaticFiles = None  # type: ignore[assignment]
    WebSocket = Any  # type: ignore[misc,assignment]
    WebSocketDisconnect = Exception  # type: ignore[assignment]

from bot.web.api_routes import create_api_router
from bot.web.websocket_server import WebSocketBroadcaster
from bot.config.settings import Settings


logger = logging.getLogger(__name__)


def _market_token_ids(markets: list[Any]) -> list[str]:
    token_ids: list[str] = []
    for market in markets:
        for attr in ("up_token_id", "down_token_id"):
            token_id = getattr(market, attr, None)
            if token_id:
                token_ids.append(str(token_id))
    return token_ids


def _update_spot_fields(market: Any, scanner: Any, price_feed: Any) -> None:
    tick = None
    price_source = type(price_feed).__name__ if price_feed is not None else "Unknown"
    
    if price_feed is not None and hasattr(price_feed, "latest"):
        latest = getattr(price_feed, "latest", {})
        if isinstance(latest, dict):
            asset = getattr(market, "asset", None)
            if asset:
                tick = latest.get(asset.upper()) or latest.get(asset.lower()) or latest.get(asset)
    if tick is not None:
        current_price = float(getattr(tick, "price", 0) or 0)
        market.current_price = current_price
        
        if "PolymarketRTDS" in price_source:
            market.current_price_source = "polymarket_rtds_chainlink"
        elif "Binance" in price_source:
            market.current_price_source = "binance_live"
        else:
            market.current_price_source = price_source.lower()
        
        window_ts = getattr(market, "window_start_timestamp", None)
        slug_key = f"{market.asset}:{market.timeframe}:{market.event_slug or market.slug or ''}"
        
        if window_ts is not None:
            target_cache_key = f"target:{slug_key}"
            if not hasattr(scanner, "_target_price_for_slug"):
                scanner._target_price_for_slug = {}
            
            stored = scanner._target_price_for_slug.get(target_cache_key)
            if stored:
                market.price_to_beat = stored.get("price")
                market.target_price_source = stored.get("source", "window_start")
        
        if getattr(market, "price_to_beat", None) is None:
            if window_ts is not None and window_ts > 0:
                market.target_price_source = "no_data"
    elif price_feed is not None and hasattr(price_feed, "assets"):
        market.current_price_source = "polymarket_rtds_pending"


def _refresh_computed_fields(market: Any) -> None:
    from bot.data.market_scanner import _compute_edge, _seconds_left

    gross_edge, net_edge = _compute_edge(market)
    market.edge = gross_edge
    market.net_edge = net_edge
    market.seconds_left = _seconds_left(market)


def _apply_book_event(scanner: Any, markets: list[Any], payload: dict[str, Any]) -> None:
    rows = payload.get("books") or payload.get("data") or payload.get("changes") or [payload]
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        token_id = row.get("asset_id") or row.get("assetId") or row.get("token_id") or row.get("tokenId") or row.get("id")
        if token_id is None:
            continue
        token_id = str(token_id)
        for market in markets:
            side = "up" if token_id == str(getattr(market, "up_token_id", "")) else "down" if token_id == str(getattr(market, "down_token_id", "")) else None
            if side is None:
                continue
            if hasattr(scanner, "_apply_book") and (row.get("bids") or row.get("buys") or row.get("asks") or row.get("sells")):
                scanner._apply_book(market, side, row)
            price = row.get("price") or row.get("best_ask") or row.get("bestAsk")
            if price is not None:
                with contextlib.suppress(TypeError, ValueError):
                    setattr(market, f"{side}_price", float(price))
            if hasattr(scanner, "_mirror_books"):
                scanner._mirror_books(market)
            if hasattr(scanner, "_spread"):
                market.spread = scanner._spread(market)
            market.book_updated_at = time.time()


async def _realtime_market_loop(broadcaster, scanner, price_feed, settings, stop_event: asyncio.Event):
    """Realtime market updates independent of bot state."""
    scan_interval = getattr(settings, "scan_interval", 10.0)
    realtime_interval = getattr(settings, "realtime_interval", 0.5)
    last_scan = 0
    active_markets: list[Any] = []
    subscribed_tokens: set[str] = set()
    target_fetched: dict[str, bool] = {}

    async def handle_market_ws(event: Any) -> None:
        payload = getattr(event, "payload", None)
        if isinstance(payload, dict):
            _apply_book_event(scanner, active_markets, payload)

    async def fetch_target_price(market: Any, price_feed: Any) -> None:
        window_ts = getattr(market, "window_start_timestamp", None)
        if window_ts is None:
            return
        
        slug_key = f"{market.asset}:{market.timeframe}:{market.event_slug or market.slug or ''}"
        target_cache_key = f"target:{slug_key}"
        
        if target_cache_key in target_fetched and target_fetched[target_cache_key]:
            return
        
        price_source = type(price_feed).__name__ if price_feed is not None else "Unknown"
        
        if "PolymarketRTDS" in price_source:
            source_label = "polymarket_rtds_chainlink"
        elif "Binance" in price_source:
            source_label = "binance"
        else:
            source_label = "unknown"
        
        if price_feed is not None and hasattr(price_feed, "price_at"):
            try:
                price_at_method = price_feed.price_at
                result = price_at_method(market.asset, float(window_ts))
                if inspect.isawaitable(result):
                    historical_price = await result
                else:
                    historical_price = result
                if historical_price is not None:
                    if not hasattr(scanner, "_target_price_for_slug"):
                        scanner._target_price_for_slug = {}
                    scanner._target_price_for_slug[target_cache_key] = {
                        "price": historical_price,
                        "timestamp": window_ts,
                        "source": source_label,
                    }
                    market.price_to_beat = historical_price
                    market.target_price_source = source_label
                    target_fetched[target_cache_key] = True
            except Exception as exc:
                logger.warning("Failed to fetch historical price for {}: {}", market.asset, exc)

    client = getattr(scanner, "client", None)
    if client is not None and hasattr(client, "register_callback"):
        client.register_callback(handle_market_ws)

    while not stop_event.is_set():
        try:
            now = time.time()
            # Discovery scan every scan_interval
            if now - last_scan >= scan_interval:
                if hasattr(scanner, "scan"):
                    scanned = await scanner.scan()
                    if isinstance(scanned, list):
                        active_markets = scanned
                        token_ids = set(_market_token_ids(active_markets))
                        new_token_ids = sorted(token_ids - subscribed_tokens)
                        if new_token_ids and client is not None and hasattr(client, "subscribe_market"):
                            try:
                                await client.subscribe_market("", new_token_ids)
                                subscribed_tokens.update(new_token_ids)
                                logger.info("Subscribed to Polymarket market websocket for %s tokens", len(new_token_ids))
                            except Exception as exc:  # noqa: BLE001 - keep dashboard updates alive without CLOB WS
                                logger.warning("Polymarket market websocket subscription failed: %s", exc, exc_info=True)
                last_scan = now

            if active_markets:
                for market in active_markets:
                    await fetch_target_price(market, price_feed)
                    _update_spot_fields(market, scanner, price_feed)
                    _refresh_computed_fields(market)

            if active_markets:
                await broadcaster.publish("market_tick", {
                    "markets": [m.to_dict() if hasattr(m, "to_dict") else dict(m) for m in active_markets]
                })

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Realtime market loop failed: %s", exc, exc_info=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=realtime_interval)
        except asyncio.TimeoutError:
            pass


def create_app(settings: Any, services: dict[str, Any] | None = None) -> Any:
    if FastAPI is None or StaticFiles is None:
        raise RuntimeError("FastAPI required for web server")
    services = services or {}
    broadcaster: WebSocketBroadcaster = services.setdefault("broadcaster", WebSocketBroadcaster())

    @asynccontextmanager
    async def lifespan(_app: Any) -> Any:
        # Start realtime services
        stop_event = asyncio.Event()
        price_feed = services.get("price_feed")
        scanner = services.get("market_scanner")

        # Start price feed
        if price_feed is not None and hasattr(price_feed, "run"):
            price_task = asyncio.create_task(price_feed.run())
        else:
            price_task = None

        # Start realtime market loop
        if scanner is not None:
            realtime_task = asyncio.create_task(
                _realtime_market_loop(broadcaster, scanner, price_feed, settings, stop_event)
            )
        else:
            realtime_task = None

        yield

        # Stop services
        stop_event.set()
        if realtime_task is not None:
            realtime_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await realtime_task
        if price_task is not None:
            price_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await price_task

        engine = services.get("bot_engine")
        if engine is not None and hasattr(engine, "stop"):
            await engine.stop()
        client = services.get("polymarket_client")
        if client is not None and hasattr(client, "close"):
            await client.close()

    app = FastAPI(title="Polymarket Walerike", version="0.1.0", lifespan=lifespan)
    app.include_router(create_api_router(settings, services))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            broadcaster.disconnect(websocket)
        except Exception:
            broadcaster.disconnect(websocket)
            with contextlib.suppress(Exception):
                await websocket.close()

    frontend_dir = Path(settings.frontend_dir)
    static_dir = frontend_dir / "dist" if (frontend_dir / "dist").exists() else frontend_dir
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app
