"""FastAPI application factory for dashboard server."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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


def _apply_cached_target(market: Any, scanner: Any) -> None:
    """Apply cached target price to market if available, always runs."""
    asset = getattr(market, "asset", None)
    if not asset:
        return
    timeframe = getattr(market, "timeframe", "")
    event_slug = getattr(market, "event_slug", "") or getattr(market, "slug", "") or ""
    slug_key = f"{asset}:{timeframe}:{event_slug}"
    target_cache_key = f"target:{slug_key}"
    if not hasattr(scanner, "_target_price_for_slug"):
        scanner._target_price_for_slug = {}
    stored = scanner._target_price_for_slug.get(target_cache_key)
    if stored:
        market.price_to_beat = stored.get("price")
        market.target_price_source = stored.get("source", "window_start")
    else:
        window_ts = getattr(market, "window_start_timestamp", None)
        if window_ts is not None and window_ts > 0 and getattr(market, "price_to_beat", None) is None:
            market.target_price_source = "no_data"


def _update_spot_fields(market: Any, scanner: Any, price_feed: Any) -> None:
    _apply_cached_target(market, scanner)

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
    elif price_feed is not None and hasattr(price_feed, "assets"):
        market.current_price_source = "polymarket_rtds_pending"


def _refresh_computed_fields(market: Any) -> None:
    from bot.data.market_scanner import _compute_edge, _seconds_left

    gross_edge, net_edge = _compute_edge(market)
    market.edge = gross_edge
    market.net_edge = net_edge
    market.seconds_left = _seconds_left(market)


def _historical_source_label(price_feed: Any) -> str:
    price_source = type(price_feed).__name__ if price_feed is not None else "Unknown"
    if "PolymarketRTDS" in price_source:
        return "polymarket_rtds_chainlink"
    if "Binance" in price_source:
        return "binance_historical_window_start"
    return "unknown"


async def _price_at(price_feed: Any, asset: str, window_ts: float) -> float | None:
    if price_feed is None or not hasattr(price_feed, "price_at"):
        return None
    price_at_method = price_feed.price_at
    result = price_at_method(asset, window_ts)
    if inspect.isawaitable(result):
        result = await result
    return float(result) if result is not None else None


async def _fetch_historical_target_price(
    asset: str,
    window_ts: float,
    price_feed: Any,
    fallback_price_feed: Any = None,
) -> tuple[float | None, str | None]:
    seen: set[int] = set()
    for feed in (price_feed, fallback_price_feed):
        if feed is None or id(feed) in seen:
            continue
        seen.add(id(feed))
        price = await _price_at(feed, asset, window_ts)
        if price is not None:
            return price, _historical_source_label(feed)
    return None, None


async def _fetch_crypto_price_api_target(market: Any, client: Any) -> tuple[float | None, str | None]:
    if client is None:
        return None, None
    timeframe = str(getattr(market, "timeframe", "")).lower()
    window_ts = getattr(market, "window_start_timestamp", None)
    asset = getattr(market, "asset", None)
    if window_ts is None or not asset:
        return None, None

    start = datetime.fromtimestamp(float(window_ts), timezone.utc)

    crypto_price_variants = {
        "5m": ("fiveminute", timedelta(minutes=5)),
        "15m": ("fifteen", timedelta(minutes=15)),
    }
    variant = crypto_price_variants.get(timeframe)
    if variant is not None and hasattr(client, "fetch_crypto_price"):
        variant_name, duration = variant
        end = start + duration
        payload = await client.fetch_crypto_price(
            str(asset).upper(),
            start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            variant_name,
            end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if not isinstance(payload, dict):
            return None, None
        price = payload.get("openPrice")
        if price is None:
            return None, None
        return float(price), "polymarket_crypto_price_api"

    if timeframe == "1h" and hasattr(client, "fetch_past_results"):
        end = start + timedelta(hours=1)
        payload = await client.fetch_past_results(
            str(asset).upper(),
            start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if not isinstance(payload, dict):
            return None, None
        data = payload.get("data")
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return None, None
        last = results[-1]
        price = last.get("closePrice") if isinstance(last, dict) else None
        if price is None:
            return None, None
        return float(price), "polymarket_past_results_api"

    return None, None


def _scrape_target_price_from_html(html: str | None, slug: str) -> tuple[float | None, str | None]:
    """Extract target price from Polymarket page HTML using strict anchors.

    For recurring markets (5m, 15m): finds crypto-prices query matching slug timestamp.
    For one-off events: finds eventMetadata priceToBeat anchored to slug/ticker.
    No generic text fallbacks. Returns (price, source) or (None, None).
    """
    if not html:
        return None, None

    import json as _json
    import re as _re

    asset = "SOL"
    if "btc" in slug.lower() or "bitcoin" in slug.lower():
        asset = "BTC"
    elif "eth" in slug.lower() or "ethereum" in slug.lower():
        asset = "ETH"

    asset_limits = {
        "BTC": (1000.0, 500000.0),
        "ETH": (100.0, 50000.0),
        "SOL": (1.0, 10000.0),
    }
    low, high = asset_limits.get(asset, (1.0, 500000.0))

    def valid_price(p: float) -> bool:
        return low < p < high

    ts_match = _re.search(r"-(\d{10})$", slug)
    has_timestamp = ts_match is not None

    if has_timestamp:
        ts = int(ts_match.group(1))
        try:
            from datetime import datetime, timezone
            start = datetime.fromtimestamp(ts, timezone.utc)
            tf = "5m"
            if "-15m-" in slug:
                tf = "15m"
            elif ("-1h-" in slug) or ("april-" in slug.lower()) or ((slug.startswith(("btc-", "eth-", "sol-"))) and "or-down" in slug):
                tf = "1h"
            start_iso = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            key = f'"{start_iso}"'
            key_idx = html.find(key) if key else -1
            if key_idx > 0:
                start_idx = key_idx + len(key)
                after_key = html[start_idx:start_idx + 300]
                price_match = _re.search(r'"openPrice"\s*:\s*([0-9.]+)', after_key)
                if price_match:
                    p = float(price_match.group(1))
                    if valid_price(p):
                        return p, "polymarket_page_scrape"
        except Exception:
            pass

    for anchor in (f'"slug":"{_re.escape(slug)}"', f'"ticker":"{_re.escape(slug)}"'):
        pos = html.find(anchor)
        if pos < 0:
            continue
        window = html[pos:pos + 3000]
        meta_match = _re.search(r'"eventMetadata"[^}]*"priceToBeat"\s*:\s*([0-9.]+)', window)
        if meta_match:
            p = float(meta_match.group(1))
            if valid_price(p):
                return p, "polymarket_page_scrape"

    if has_timestamp:
        ts = int(ts_match.group(1))
        try:
            from datetime import datetime, timezone
            start = datetime.fromtimestamp(ts, timezone.utc)
            start_iso = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            for variant in [start_iso, start_iso.replace("000Z", "Z"), start_iso.replace(".000Z", "Z")]:
                key = f'"{variant}"'
                key_idx = html.find(key)
                if key_idx > 0:
                    after = html[key_idx + len(key):key_idx + len(key) + 200]
                    price_match = _re.search(r'"openPrice"\s*:\s*([0-9.]+)', after)
                    if price_match:
                        p = float(price_match.group(1))
                        if valid_price(p):
                            return p, "polymarket_page_scrape"
        except Exception:
            pass

    idx = html.find('"openPrice":')
    if idx > 0:
        before = html[max(0, idx - 150):idx + 150]
        price_match = _re.search(r'"openPrice"\s*:\s*([0-9.]+)', before)
        if price_match:
            p = float(price_match.group(1))
            if valid_price(p):
                return p, "polymarket_page_scrape"

    return None, None


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


async def _realtime_market_loop(
    broadcaster,
    scanner,
    price_feed,
    settings,
    stop_event: asyncio.Event,
    target_price_feed: Any = None,
):
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

    async def fetch_target_price(market: Any, price_feed: Any, client: Any) -> None:
        window_ts = getattr(market, "window_start_timestamp", None)
        if window_ts is None:
            _apply_cached_target(market, scanner)
            return

        slug_key = f"{market.asset}:{market.timeframe}:{market.event_slug or market.slug or ''}"
        target_cache_key = f"target:{slug_key}"

        if target_cache_key in target_fetched and target_fetched[target_cache_key]:
            _apply_cached_target(market, scanner)
            return

        # If scan() already extracted price_to_beat from market text, cache and done.
        existing_price = getattr(market, "price_to_beat", None)
        if existing_price is not None:
            if not hasattr(scanner, "_target_price_for_slug"):
                scanner._target_price_for_slug = {}
            scanner._target_price_for_slug[target_cache_key] = {
                "price": existing_price,
                "timestamp": window_ts,
                "source": getattr(market, "target_price_source", None) or "text_extraction",
            }
            target_fetched[target_cache_key] = True
            return

        try:
            target_price: float | None = None
            source_label: str | None = None

            # 1) For 5m markets, ask the same web API the Polymarket page uses.
            try:
                target_price, source_label = await _fetch_crypto_price_api_target(market, client)
                if target_price is not None:
                    logger.info("Fetched target price for {} from crypto-price API: {}", market.asset, target_price)
            except Exception as exc:
                logger.warning("Crypto price API target fetch failed for {}: {}", market.asset, exc)

            # 2) Scrape Polymarket page as fallback — gets the exact openPrice used
            #    for resolution (Chainlink oracle value at window start).
            if target_price is None and client is not None and hasattr(client, "fetch_page_html"):
                slug = getattr(market, "event_slug", None) or getattr(market, "slug", None) or getattr(market, "market_slug", None)
                if slug:
                    try:
                        html = await client.fetch_page_html(slug)
                        target_price, source_label = _scrape_target_price_from_html(html, slug)
                        if target_price is not None:
                            logger.info("Scraped target price for {} from page: {}", market.asset, target_price)
                    except Exception as exc:
                        logger.warning("Page scrape failed for {}: {}", market.asset, exc)

            if target_price is not None:
                if not hasattr(scanner, "_target_price_for_slug"):
                    scanner._target_price_for_slug = {}
                scanner._target_price_for_slug[target_cache_key] = {
                    "price": target_price,
                    "timestamp": window_ts,
                    "source": source_label,
                }
                market.price_to_beat = target_price
                market.target_price_source = source_label
            else:
                _apply_cached_target(market, scanner)
            target_fetched[target_cache_key] = True
        except Exception as exc:
            logger.warning("Failed to fetch target price for {}: {}", market.asset, exc)
            _apply_cached_target(market, scanner)
            target_fetched[target_cache_key] = True

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
                    await fetch_target_price(market, price_feed, client)
                    _update_spot_fields(market, scanner, price_feed)
                    _refresh_computed_fields(market)

            if active_markets:
                await broadcaster.publish("market_tick", {
                    "markets": [m.to_tick_dict() if hasattr(m, "to_tick_dict") else m.to_dict() if hasattr(m, "to_dict") else dict(m) for m in active_markets]
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
        target_price_feed = services.get("target_price_feed")
        scanner = services.get("market_scanner")

        # Start price feed
        if price_feed is not None and hasattr(price_feed, "run"):
            price_task = asyncio.create_task(price_feed.run())
        else:
            price_task = None

        # Start realtime market loop
        if scanner is not None:
            realtime_task = asyncio.create_task(
                _realtime_market_loop(broadcaster, scanner, price_feed, settings, stop_event, target_price_feed)
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
