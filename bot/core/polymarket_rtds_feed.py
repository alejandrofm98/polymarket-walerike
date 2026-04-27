"""Polymarket Real-Time Data Socket (RTDS) feed for crypto prices."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    class _FallbackLogger:
        def __init__(self) -> None:
            self._logger = logging.getLogger(__name__)

        def warning(self, message: str, *args: Any) -> None:
            self._logger.warning(message.format(*args))

    logger = _FallbackLogger()

try:
    import websockets
except ImportError:  # pragma: no cover - optional until live feed use
    websockets = None  # type: ignore[assignment]


@dataclass(slots=True)
class PriceTick:
    asset: str
    symbol: str
    price: float
    timestamp: float


class PolymarketRTDSFeed:
    """Polymarket RTDS feed for crypto prices."""

    SUPPORTED_TOPICS = {"crypto_prices_chainlink", "crypto_prices"}

    SYMBOL_MAP = {
        "BTC": "btc/usd",
        "ETH": "eth/usd",
        "SOL": "sol/usd",
        "XRP": "xrp/usd",
    }
    
    REVERSE_SYMBOL_MAP = {
        "btc/usd": "BTC",
        "eth/usd": "ETH",
        "sol/usd": "SOL",
        "xrp/usd": "XRP",
    }

    def __init__(self, assets: list[str] | None = None, history_limit: int = 120, topic: str = "crypto_prices_chainlink") -> None:
        self.assets = assets or ["BTC", "ETH", "SOL"]
        self.history_limit = history_limit
        self.topic = topic if topic in self.SUPPORTED_TOPICS else "crypto_prices_chainlink"
        self.latest: dict[str, PriceTick] = {}
        self.history: dict[str, Deque[PriceTick]] = {
            asset: deque(maxlen=history_limit) for asset in self.assets
        }
        self._closed = False
        self._last_ping = 0.0
        self._last_update_at: dict[str, float] = {asset: 0.0 for asset in self.assets}
        self._snapshot_seen: dict[str, bool] = {asset: False for asset in self.assets}
        self._last_live_update: dict[str, float] = {asset: 0.0 for asset in self.assets}

    async def run(self) -> None:
        if websockets is None:
            raise RuntimeError("Live Polymarket RTDS feed requires optional package websockets")

        backoff = 1.0
        self._closed = False
        
        symbols_to_subscribe = [self.SYMBOL_MAP.get(asset, asset.lower()) for asset in self.assets]
        tasks = [asyncio.create_task(self._run_symbol(symbol)) for symbol in symbols_to_subscribe if symbol]
        if not tasks:
            return
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_symbol(self, symbol: str) -> None:
        backoff = 1.0
        asset = self.REVERSE_SYMBOL_MAP.get(symbol.lower())
        reconnect_interval = 0.2
        while not self._closed:
            try:
                async with websockets.connect(self.url, ping_interval=None, ping_timeout=None) as ws:
                    backoff = 1.0
                    self._snapshot_seen[asset] = False
                    await self._subscribe(ws, [symbol])
                    snapshot_time = 0.0
                    
                    recv_timeout = 1.0
                    while not self._closed:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                        except asyncio.TimeoutError:
                            now = time.time()
                            if self._snapshot_seen.get(asset):
                                if now - snapshot_time > reconnect_interval:
                                    break
                            continue
                        
                        if isinstance(message, str):
                            text = message.strip()
                            if not text:
                                await ws.send("PONG")
                                continue
                            upper_text = text.upper()
                            if upper_text == "PONG":
                                continue
                            if upper_text == "PING":
                                await ws.send("PONG")
                                continue
                            if not text.startswith(("{", "[")):
                                continue
                        
                        tick = self.parse_update(message, default_symbol=symbol)
                        if tick is not None:
                            self._last_update_at[asset] = time.time()
                            if not self._snapshot_seen.get(asset):
                                self._snapshot_seen[asset] = True
                                snapshot_time = time.time()
                            else:
                                self._last_live_update[asset] = time.time()
                        
                        now = time.time()
                        if self._last_ping == 0 or now - self._last_ping >= 5.0:
                            await ws.send("PING")
                            self._last_ping = now
                            
            
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - feed should reconnect, not crash bot
                logger.warning("Polymarket RTDS feed error for {}: {}", symbol, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _subscribe(self, ws: Any, symbols: list[str]) -> None:
        filters = [json.dumps({"symbol": sym}) for sym in symbols if sym]
        
        subscribe_msg = {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": self.topic,
                    "type": "*",
                    "filters": f
                }
                for f in filters
            ]
        }
        
        await ws.send(json.dumps(subscribe_msg))

    def close(self) -> None:
        self._closed = True

    @property
    def url(self) -> str:
        return "wss://ws-live-data.polymarket.com"
    
    @property
    def http_url(self) -> str:
        return "https://clob.polymarket.com"
    
    async def fetch_latest_http(self, asset: str) -> float | None:
        """Fetch latest price via HTTP CLOB API."""
        import httpx
        clob_url = self.http_url
        if asset.upper() == "BTC":
            token_id = "18602659456496182356797711773549015648785398833357911118911730227476645870512"
        elif asset.upper() == "ETH":
            token_id = "13652656186878011544734895284087483759937041640570733735454121919445287753779"
        elif asset.upper() == "SOL":
            token_id = "13652714401975934804278854934037247120941810770733735454121919445287753779"
        else:
            return None
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{clob_url}/prices-history?token_id={token_id}&interval=1m&limit=1")
                if resp.status_code == 200:
                    data = resp.json()
                    history = data.get("history", [])
                    if history and len(history) > 0:
                        return float(history[0].get("price", 0))
        except Exception:
            pass
        return None
    
    @property
    def http_url(self) -> str:
        return "https://clob.polymarket.com"
    
    async def fetch_latest_price(self, asset: str) -> float | None:
        """Fetch latest price via HTTP for when WebSocket updates don't work."""
        import httpx
        symbol = self.SYMBOL_MAP.get(asset.upper(), asset.lower())
        url = f"{self.http_url}/prices?symbol={symbol}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    price = data.get("price") or data.get("value")
                    if price:
                        return float(price)
        except Exception:
            pass
        return None

    def parse_update(self, message: Any, default_symbol: str | None = None) -> PriceTick | None:
        try:
            payload = self._loads(message)
            
            topic = payload.get("topic", "")
            data = payload.get("payload", {})
            if topic and topic not in self.SUPPORTED_TOPICS:
                return None

            msg_type = payload.get("type")
            if msg_type == "subscribe" and not data.get("data") and data.get("value") is None:
                return None

            symbol = str(data.get("symbol") or default_symbol or "").lower()
            asset = self.REVERSE_SYMBOL_MAP.get(symbol)
            
            if not asset or asset not in self.assets:
                return None
            
            value = data.get("value")
            if value is None:
                batch = data.get("data")
                if batch and isinstance(batch, list) and len(batch) > 0:
                    tick = None
                    history = self.history.setdefault(asset, deque(maxlen=self.history_limit))
                    for item in batch:
                        value = item.get("value")
                        if value is None:
                            continue
                        timestamp_ms = item.get("timestamp")
                        timestamp = float(timestamp_ms) / 1000.0 if timestamp_ms else time.time()
                        tick = PriceTick(
                            asset=asset,
                            symbol=symbol.upper(),
                            price=float(value),
                            timestamp=timestamp,
                        )
                        history.append(tick)
                    if tick is not None:
                        self.latest[asset] = tick
                        self._last_update_at[asset] = time.time()
                    return tick
                return None
            
            self._last_live_update[asset] = time.time()
            price = float(value)
            timestamp_ms = data.get("timestamp")
            timestamp = float(timestamp_ms) / 1000.0 if timestamp_ms else time.time()
            
            tick = PriceTick(
                asset=asset,
                symbol=symbol.upper(),
                price=price,
                timestamp=timestamp,
            )
            
        except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Polymarket RTDS parse failed: {}", exc)
            return None

        self.latest[asset] = tick
        self.history.setdefault(asset, deque(maxlen=self.history_limit)).append(tick)
        return tick

    def momentum_pct(self, asset: str, window_count: int = 5) -> float:
        points = self.history.get(asset.upper())
        if not points or len(points) < 2:
            return 0.0
        window = list(points)[-(window_count + 1):]
        if len(window) < 2 or window[0].price == 0:
            return 0.0
        return ((window[-1].price - window[0].price) / window[0].price) * 100.0

    def price_at(self, symbol: str, timestamp: float, max_seconds_gap: float = 5.0) -> float | None:
        """Get price at or closest to a specific timestamp from local history.
        
        Args:
            symbol: Asset symbol (e.g., 'BTC', 'ETH', 'SOL')
            timestamp: Unix timestamp in seconds
            max_seconds_gap: If oldest point is later than timestamp + gap, return None
            
        Returns:
            Price at the given timestamp or closest available, or None if unavailable
        """
        asset = symbol.upper()
        history = self.history.get(asset)
        
        if not history:
            return None
        
        points = list(history)
        
        if not points:
            return None
        
        if points[0].timestamp > timestamp + max_seconds_gap:
            return None
        
        if points[0].timestamp >= timestamp:
            return points[0].price
        
        if points[-1].timestamp <= timestamp:
            return points[-1].price
        
        closest = min(points, key=lambda p: abs(p.timestamp - timestamp))
        return closest.price if closest else None

    @staticmethod
    def _loads(message: Any) -> dict[str, Any]:
        if message is None:
            return {}
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        if isinstance(message, str):
            message = message.strip()
            if not message:
                return {}
            try:
                parsed = json.loads(message)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return message if isinstance(message, dict) else {}


async def run_feed_until_closed(feed: PolymarketRTDSFeed) -> None:
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await feed.run()
