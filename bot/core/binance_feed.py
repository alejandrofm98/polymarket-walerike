"""Async Binance price feed with testable message parsing."""

from __future__ import annotations

import asyncio
import contextlib
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

try:
    import httpx
except ImportError:  # pragma: no cover - optional until REST historical use
    httpx = None  # type: ignore[assignment]


@dataclass(slots=True)
class PriceTick:
    asset: str
    symbol: str
    price: float
    change_24h: float
    change_pct_24h: float
    volume_24h: float
    timestamp: float


class BinanceTickerFeed:
    DEFAULT_SYMBOLS = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}

    def __init__(self, symbols: dict[str, str] | None = None, history_limit: int = 120) -> None:
        self.symbols = symbols or self.DEFAULT_SYMBOLS.copy()
        self.history_limit = history_limit
        self.latest: dict[str, PriceTick] = {}
        self.history: dict[str, Deque[PriceTick]] = {
            asset: deque(maxlen=history_limit) for asset in self.symbols
        }
        self._closed = False

    async def run(self) -> None:
        if websockets is None:
            raise RuntimeError("Live Binance feed requires optional package websockets")

        backoff = 1.0
        self._closed = False
        while not self._closed:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    backoff = 1.0
                    async for message in ws:
                        self.parse_update(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - feed should reconnect, not crash bot
                logger.warning("Binance price feed error: {}", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def close(self) -> None:
        self._closed = True

    @property
    def url(self) -> str:
        streams = "/".join(f"{symbol.lower()}@aggTrade" for symbol in self.symbols.values())
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    def parse_update(self, message: Any) -> PriceTick | None:
        try:
            payload = self._loads(message)
            data = payload.get("data", payload)
            symbol = str(data.get("s") or data.get("symbol") or "").lower()
            asset = self._asset_for_symbol(symbol)
            if not asset:
                return None
            price = data.get("p") if data.get("e") == "aggTrade" else data.get("c") or data.get("price") or data.get("p")

            tick = PriceTick(
                asset=asset,
                symbol=symbol.upper(),
                price=float(price),
                change_24h=0.0 if data.get("e") == "aggTrade" else float(data.get("p") or data.get("change_24h") or 0.0),
                change_pct_24h=float(data.get("P") or data.get("change_pct_24h") or 0.0),
                volume_24h=float(data.get("v") or data.get("volume_24h") or 0.0),
                timestamp=float(data.get("T") or data.get("E") or data.get("timestamp") or time.time() * 1000) / 1000.0,
            )
        except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Binance price update parse failed: {}", exc)
            return None

        self.latest[asset] = tick
        self.history.setdefault(asset, deque(maxlen=self.history_limit)).append(tick)
        return tick

    def momentum_pct(self, asset: str, window_count: int = 5) -> float:
        points = self.history.get(asset.upper())
        if not points or len(points) < 2:
            return 0.0
        window = list(points)[-(window_count + 1) :]
        if len(window) < 2 or window[0].price == 0:
            return 0.0
        return ((window[-1].price - window[0].price) / window[0].price) * 100.0

    def acceleration_pct(self, asset: str, window_count: int = 3) -> float:
        points = self.history.get(asset.upper())
        if not points or len(points) < (window_count * 2 + 1):
            return 0.0
        values = list(points)
        current = self._momentum_for(values[-(window_count + 1) :])
        previous = self._momentum_for(values[-(window_count * 2 + 1) : -(window_count)])
        return current - previous

    def _asset_for_symbol(self, symbol: str) -> str | None:
        for asset, configured in self.symbols.items():
            if configured.lower() == symbol:
                return asset.upper()
        return None

    @staticmethod
    def _loads(message: Any) -> dict[str, Any]:
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        if isinstance(message, str):
            parsed = json.loads(message)
            return parsed if isinstance(parsed, dict) else {}
        return message if isinstance(message, dict) else {}

    @staticmethod
    def _momentum_for(points: list[PriceTick]) -> float:
        if len(points) < 2 or points[0].price == 0:
            return 0.0
        return ((points[-1].price - points[0].price) / points[0].price) * 100.0

    async def price_at(self, symbol: str, timestamp: float) -> float | None:
        """Get historical price at a specific timestamp via Binance REST API.
        
        Args:
            symbol: Asset symbol (e.g., 'BTC', 'ETH', 'SOL')
            timestamp: Unix timestamp in seconds
            
        Returns:
            Price at the given timestamp, or None if unavailable
        """
        if httpx is None:
            logger.warning("httpx required for historical price lookup")
            return None
        
        asset = symbol.upper()
        binance_symbol = self.symbols.get(asset)
        if not binance_symbol:
            logger.warning("No Binance symbol mapping for {}", asset)
            return None
        
        binance_symbol = binance_symbol.upper()
        
        params = {
            "symbol": binance_symbol,
            "startTime": int(timestamp * 1000),
            "endTime": int(timestamp * 1000) + 1000,
            "limit": 1,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.binance.com/api/v3/aggTrades",
                    params=params,
                )
                if response.status_code != 200:
                    return None
                trades = response.json()
                if trades and isinstance(trades, list) and len(trades) > 0:
                    price = trades[0].get("p")
                    if price is not None:
                        return float(price)
        except Exception as exc:
            logger.warning("Failed to fetch historical price for {} at {}: {}", symbol, timestamp, exc)
        return None


async def run_feed_until_closed(feed: BinanceTickerFeed) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        await feed.run()
