"""Polymarket market discovery and CLOB book enrichment."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from bot.data.market_slug_resolver import build_short_slug, candidate_window_starts, select_active_event, series_slug

SHORT_TIMEFRAME_SECONDS = {"5m": 300, "15m": 900}
logger = logging.getLogger(__name__)


def _current_window_starts(timeframe: str, now_ts: int | float | None = None) -> list[int]:
    """Return [current, next, previous] window starts - prefer current first."""
    tf = timeframe.lower()
    if tf not in SHORT_TIMEFRAME_SECONDS:
        raise ValueError("_current_window_starts only supports 5m and 15m")
    from datetime import datetime, timezone
    now = int(datetime.now(timezone.utc).timestamp() if now_ts is None else now_ts)
    interval = SHORT_TIMEFRAME_SECONDS[tf]
    current = (now // interval) * interval
    return [current, current + interval, current - interval]


def _is_valid_window(candidate: MarketCandidate, now_ts: float) -> bool:
    """Check if market window is current or future (not past)."""
    if candidate.end_date is None:
        return True
    try:
        from datetime import datetime, timezone
        end = datetime.fromisoformat(candidate.end_date.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)
        return end.timestamp() >= now_ts
    except Exception:
        return True


def _append_candidates(candidates: list[MarketCandidate], seen: set[str], candidate: MarketCandidate | None, now_ts: float) -> None:
    """Append candidate if valid window and not duplicate."""
    if candidate is None:
        return
    if not _is_valid_window(candidate, now_ts):
        return
    key = candidate.condition_id or candidate.market_id or candidate.market_slug or candidate.event_slug or candidate.question
    if key in seen:
        return
    seen.add(key)
    candidates.append(candidate)


def _parse_price_to_beat(event: dict[str, Any] | None, market: dict[str, Any] | None) -> float | None:
    """Extract price threshold from event/market text fields."""
    texts = []
    for obj, keys in [
        (event, ["title", "description", "rules", "resolutionSource"]),
        (market, ["question", "description", "rules", "resolutionSource"]),
    ]:
        if not isinstance(obj, dict):
            continue
        for key in keys:
            val = obj.get(key)
            if val:
                texts.append(str(val))
    combined = " ".join(texts)
    if not combined:
        return None
    patterns = [
        r"\$\s*([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*USD",
        r"(?:btc|bitcoin)\s*(?:at|above|below|over|under)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        r"(?:eth|ethereum)\s*(?:at|above|below|over|under)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        r"(?:sol|solana)\s*(?:at|above|below|over|under)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        r"price\s*(?:at|above|below|over|under)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            try:
                num_str = (match.group(1) or match.group(2) or match.group(0)).replace(",", "")
                return float(num_str)
            except (ValueError, AttributeError, IndexError):
                continue
    return None


def _compute_edge(candidate: MarketCandidate) -> tuple[float | None, float | None]:
    """Compute gross edge and net edge after taker fees."""
    ask_up = candidate.best_ask_up
    ask_down = candidate.best_ask_down
    if ask_up is None or ask_down is None:
        return None, None
    gross_edge = 1.0 - ask_up - ask_down
    theta = 0.05
    p_up = ask_up
    p_down = ask_down
    fee_up = theta * p_up * (1 - p_up)
    fee_down = theta * p_down * (1 - p_down)
    net_edge = gross_edge - fee_up - fee_down
    return round(gross_edge, 4), round(net_edge, 4)


def _seconds_left(candidate: MarketCandidate) -> int | None:
    """Calculate seconds remaining until market ends."""
    if candidate.end_date is None:
        return None
    try:
        from datetime import datetime, timezone
        end = datetime.fromisoformat(candidate.end_date.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)
        remaining = int(end.timestamp() - time.time())
        return max(0, remaining)
    except Exception:
        return None


@dataclass(slots=True)
class MarketCandidate:
    market_id: str
    question: str
    asset: str
    timeframe: str | None = None
    slug: str | None = None
    market_slug: str | None = None
    condition_id: str | None = None
    event_slug: str | None = None
    series_slug: str | None = None
    event_start_time: str | None = None
    end_date: str | None = None
    accepting_orders: bool | None = None
    closed: bool | None = None
    active: bool | None = None
    up_token_id: str | None = None
    down_token_id: str | None = None
    up_price: float | None = None
    down_price: float | None = None
    best_bid_up: float | None = None
    best_ask_up: float | None = None
    best_bid_down: float | None = None
    best_ask_down: float | None = None
    bids_up: list[dict[str, float]] = field(default_factory=list)
    asks_up: list[dict[str, float]] = field(default_factory=list)
    bids_down: list[dict[str, float]] = field(default_factory=list)
    asks_down: list[dict[str, float]] = field(default_factory=list)
    book_updated_at: float | None = None
    liquidity: float | None = None
    spread: float | None = None
    tokens: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    current_price: float | None = None
    current_price_source: str | None = None
    price_to_beat: float | None = None
    first_price_for_slug: float | None = None
    window_start_timestamp: int | None = None
    target_price_source: str | None = None
    edge: float | None = None
    net_edge: float | None = None
    seconds_left: int | None = None

    def to_dict(self) -> dict[str, Any]:
        up = _first_token(self.tokens, "up") or _first_token(self.tokens, "yes")
        down = _first_token(self.tokens, "down") or _first_token(self.tokens, "no")
        return {
            "market_id": self.market_id,
            "question": self.question,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "slug": self.slug or self.market_slug or self.event_slug,
            "market_slug": self.market_slug or self.slug,
            "condition_id": self.condition_id,
            "event_slug": self.event_slug,
            "series_slug": self.series_slug,
            "event_start_time": self.event_start_time,
            "end_date": self.end_date,
            "accepting_orders": self.accepting_orders,
            "closed": self.closed,
            "active": self.active,
            "up_token_id": self.up_token_id,
            "down_token_id": self.down_token_id,
            "up_price": self.up_price,
            "down_price": self.down_price,
            "best_bid_up": self.best_bid_up,
            "best_ask_up": self.best_ask_up,
            "best_bid_down": self.best_bid_down,
            "best_ask_down": self.best_ask_down,
            "bids_up": self.bids_up,
            "asks_up": self.asks_up,
            "bids_down": self.bids_down,
            "asks_down": self.asks_down,
            "book_updated_at": self.book_updated_at,
            "spread": self.spread,
            "liquidity": self.liquidity,
            "tokens": self.tokens,
            "up": up,
            "down": down,
            "current_price": self.current_price,
            "current_price_source": self.current_price_source,
            "price_to_beat": self.price_to_beat,
            "window_start_timestamp": self.window_start_timestamp,
            "target_price_source": self.target_price_source,
            "edge": self.edge,
            "net_edge": self.net_edge,
            "seconds_left": self.seconds_left,
            "price_diff": round(self.current_price - self.price_to_beat, 2) if self.current_price is not None and self.price_to_beat is not None else None,
            "price_diff_pct": round((self.current_price - self.price_to_beat) / self.price_to_beat * 100, 2) if self.current_price is not None and self.price_to_beat and self.price_to_beat != 0 else None,
        }

    def to_tick_dict(self) -> dict[str, Any]:
        """Lightweight dict for realtime tick events - excludes heavy order book arrays."""
        return {
            "market_id": self.market_id,
            "question": self.question,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "slug": self.slug or self.market_slug or self.event_slug,
            "condition_id": self.condition_id,
            "event_slug": self.event_slug,
            "accepting_orders": self.accepting_orders,
            "closed": self.closed,
            "up_token_id": self.up_token_id,
            "down_token_id": self.down_token_id,
            "best_bid_up": self.best_bid_up,
            "best_ask_up": self.best_ask_up,
            "best_bid_down": self.best_bid_down,
            "best_ask_down": self.best_ask_down,
            "spread": self.spread,
            "liquidity": self.liquidity,
            "current_price": self.current_price,
            "current_price_source": self.current_price_source,
            "price_to_beat": self.price_to_beat,
            "window_start_timestamp": self.window_start_timestamp,
            "target_price_source": self.target_price_source,
            "edge": self.edge,
            "net_edge": self.net_edge,
            "seconds_left": self.seconds_left,
            "price_diff": round(self.current_price - self.price_to_beat, 2) if self.current_price is not None and self.price_to_beat is not None else None,
            "price_diff_pct": round((self.current_price - self.price_to_beat) / self.price_to_beat * 100, 2) if self.current_price is not None and self.price_to_beat and self.price_to_beat != 0 else None,
        }


class MarketScanner:
    def __init__(
        self,
        client: Any,
        assets: tuple[str, ...] = ("BTC", "ETH", "SOL"),
        timeframes: tuple[str, ...] = ("5m", "15m", "1h"),
        enabled_markets: dict[str, list[str]] | None = None,
    ) -> None:
        self.client = client
        self.assets = tuple(asset.upper() for asset in assets)
        self.timeframes = tuple(timeframe.lower() for timeframe in timeframes)
        self.enabled_markets = enabled_markets or {asset: list(self.timeframes) for asset in self.assets}
        self._first_price_for_slug: dict[str, float] = {}  # Track first binance price per slug

    def configure(self, *, enabled_markets: dict[str, list[str]] | None = None) -> None:
        if enabled_markets is not None:
            self.set_enabled_markets(enabled_markets)

    def set_enabled_markets(self, enabled_markets: dict[str, list[str]]) -> None:
        normalized: dict[str, list[str]] = {}
        for raw_asset, raw_timeframes in enabled_markets.items():
            asset = str(raw_asset).strip().upper()
            if asset not in self.assets:
                continue
            if not isinstance(raw_timeframes, list):
                continue
            timeframes = [str(tf).strip().lower() for tf in raw_timeframes if tf]
            normalized[asset] = list(dict.fromkeys(timeframes))
        self.enabled_markets = normalized

    async def scan(self) -> list[MarketCandidate]:
        if any(hasattr(self.client, name) for name in ("fetch_market_by_slug", "fetch_event_by_slug", "fetch_events")):
            return await self.scan_gamma()
        markets = await self.client.get_markets()
        return self.filter_markets(markets)

    def _current_window_starts(self, timeframe: str, now_ts: int | float | None = None) -> list[int]:
        """Return [current, next, previous] window starts - prefer current first."""
        return _current_window_starts(timeframe, now_ts)

    async def scan_gamma(self) -> list[MarketCandidate]:
        candidates: list[MarketCandidate] = []
        seen: set[str] = set()
        now_ts = time.time()
        for asset, timeframes in self.enabled_markets.items():
            for timeframe in timeframes:
                if timeframe in {"5m", "15m"} and hasattr(self.client, "fetch_market_by_slug"):
                    for window_start in self._current_window_starts(timeframe, now_ts):
                        candidate = await self._fetch_market_slug(build_short_slug(asset, timeframe, window_start))
                        if candidate is not None and _is_valid_window(candidate, now_ts):
                            candidate.window_start_timestamp = window_start
                            self._append_candidate(candidates, seen, candidate)
                            break
                elif timeframe == "1h" and hasattr(self.client, "fetch_events"):
                    slug = series_slug(asset, timeframe)
                    events = await self.client.fetch_events({"series_slug": slug, "seriesSlug": slug, "active": "true", "closed": "false", "limit": 20})
                    _append_candidates(candidates, seen, self.parse_gamma_event(select_active_event(events)), now_ts)
                else:
                    events = await self._fetch_pair_events(asset, timeframe)
                    for event in self._event_rows(events):
                        _append_candidates(candidates, seen, self.parse_gamma_event(event), now_ts)
        await self._enrich_books(candidates)
        return candidates

    def filter_markets(self, markets: Any) -> list[MarketCandidate]:
        rows = self._market_rows(markets)
        candidates: list[MarketCandidate] = []
        for row in rows:
            candidate = self.parse_market(row)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def parse_market(self, market: dict[str, Any] | None) -> MarketCandidate | None:
        if not isinstance(market, dict):
            return None
        if isinstance(market.get("markets"), list):
            return self.parse_gamma_event(market)
        question = str(market.get("question") or market.get("title") or market.get("name") or "")
        slug = str(market.get("slug") or market.get("market_slug") or "")
        text = f"{question} {slug} {market.get('seriesSlug') or ''}".lower()
        if not any(word in text for word in ("up", "down", "higher", "lower")):
            return None
        asset = self._asset(text)
        if asset is None:
            return None
        if asset not in self.enabled_markets:
            return None
        timeframe = self._timeframe(text)
        if timeframe is None:
            return None
        if timeframe not in self.enabled_markets.get(asset, []):
            return None
        tokens = self._gamma_tokens(market) or self._tokens(market)
        return self._candidate_from_market(market, None, asset, timeframe, tokens)

    def parse_gamma_event(self, event: dict[str, Any] | None) -> MarketCandidate | None:
        if not isinstance(event, dict):
            return None
        markets = event.get("markets")
        if not isinstance(markets, list) or not markets:
            return None
        market = next((row for row in markets if isinstance(row, dict)), None)
        if market is None:
            return None
        event_slug = str(event.get("slug") or "")
        market_slug = str(market.get("slug") or "")
        title = str(event.get("title") or market.get("question") or market.get("title") or "")
        tags = " ".join(str(tag.get("label") or tag.get("slug") or tag.get("name") or tag) for tag in event.get("tags", []) if isinstance(tag, (dict, str)))
        text = f"{event_slug} {market_slug} {title} {event.get('seriesSlug') or event.get('series_slug') or ''} {tags}".lower()
        asset = self._asset(text)
        timeframe = self._timeframe(text)
        if asset is None or timeframe is None:
            return None
        if asset not in self.enabled_markets:
            return None
        if timeframe not in self.enabled_markets.get(asset, []):
            return None
        tokens = self._gamma_tokens(market)
        return self._candidate_from_market(market, event, asset, timeframe, tokens)

    async def _fetch_market_slug(self, slug: str, *, strict: bool = True) -> MarketCandidate | None:
        try:
            market = await self.client.fetch_market_by_slug(slug)
        except Exception:
            if strict:
                return None
            raise
        if self._bool_or_none(market.get("active")) is False or self._bool_or_none(market.get("closed")) is True:
            return None
        return self.parse_market(market)

    async def _fetch_pair_events(self, asset: str, timeframe: str) -> Any:
        if hasattr(self.client, "fetch_crypto_updown_events"):
            return await self.client.fetch_crypto_updown_events(asset, timeframe, limit=20)
        slug = series_slug(asset, timeframe)
        return await self.client.fetch_events({"q": f"{asset} updown {timeframe}", "series_slug": slug, "limit": 20, "active": "true", "closed": "false"})

    async def _enrich_books(self, candidates: list[MarketCandidate]) -> None:
        if not candidates or not hasattr(self.client, "fetch_order_books"):
            return
        token_ids = [token_id for candidate in candidates for token_id in (candidate.up_token_id, candidate.down_token_id) if token_id]
        if not token_ids:
            return
        try:
            books = await self.client.fetch_order_books(token_ids)
        except Exception as exc:
            logger.warning("CLOB order book enrichment failed: %s", exc, exc_info=True)
            books = []
        by_token = self._books_by_token(books)
        for candidate in candidates:
            self._apply_book(candidate, "up", by_token.get(str(candidate.up_token_id)))
            self._apply_book(candidate, "down", by_token.get(str(candidate.down_token_id)))
            self._mirror_books(candidate)
            candidate.spread = self._spread(candidate)
            if candidate.best_ask_up is not None:
                candidate.up_price = candidate.best_ask_up
            if candidate.best_ask_down is not None:
                candidate.down_price = candidate.best_ask_down
            if candidate.book_updated_at is None and (candidate.bids_up or candidate.asks_up or candidate.bids_down or candidate.asks_down):
                candidate.book_updated_at = time.time()
            raw = candidate.raw or {}
            candidate.price_to_beat = _parse_price_to_beat(raw.get("event") or {}, raw.get("market") or {})
            gross_edge, net_edge = _compute_edge(candidate)
            candidate.edge = gross_edge
            candidate.net_edge = net_edge
            candidate.seconds_left = _seconds_left(candidate)

    def _candidate_from_market(self, market: dict[str, Any], event: dict[str, Any] | None, asset: str, timeframe: str | None, tokens: list[dict[str, Any]]) -> MarketCandidate:
        event = event or {}
        market_slug = str(market.get("slug") or market.get("market_slug") or "") or None
        event_slug = str(event.get("slug") or market.get("eventSlug") or "") or None
        condition_id = str(market.get("conditionId") or market.get("condition_id") or market.get("condition_id") or market.get("id") or market_slug or event_slug)
        up = _first_token(tokens, "up") or _first_token(tokens, "yes") or (tokens[0] if tokens else None)
        down = _first_token(tokens, "down") or _first_token(tokens, "no") or (tokens[1] if len(tokens) > 1 else None)
        best_bid = self._float(market.get("bestBid"))
        best_ask = self._float(market.get("bestAsk"))
        up_price = self._float(up.get("price") if up else None)
        down_price = self._float(down.get("price") if down else None)
        return MarketCandidate(
            market_id=condition_id,
            question=str(event.get("title") or market.get("question") or market.get("title") or ""),
            asset=asset,
            timeframe=timeframe,
            slug=market_slug or event_slug,
            market_slug=market_slug,
            condition_id=condition_id,
            event_slug=event_slug,
            series_slug=str(event.get("seriesSlug") or event.get("series_slug") or market.get("seriesSlug") or "") or None,
            event_start_time=str(event.get("eventStartTime") or event.get("startTime") or market.get("eventStartTime") or "") or None,
            end_date=str(event.get("endDate") or market.get("endDate") or "") or None,
            accepting_orders=self._bool_or_none(market.get("acceptingOrders")),
            active=self._bool_or_none(market.get("active")),
            closed=self._bool_or_none(market.get("closed")),
            up_token_id=self._token_id(up),
            down_token_id=self._token_id(down),
            up_price=up_price,
            down_price=down_price,
            best_bid_up=best_bid,
            best_ask_up=best_ask,
            liquidity=self._float(market.get("liquidityClob") or market.get("liquidityNum") or market.get("liquidity")),
            spread=self._float(market.get("spread")) if market.get("spread") is not None else (round(best_ask - best_bid, 6) if best_bid is not None and best_ask is not None else None),
            tokens=tokens,
            raw={"event": event, "market": market, **market},
        )

    @staticmethod
    def _append_candidate(candidates: list[MarketCandidate], seen: set[str], candidate: MarketCandidate | None) -> None:
        if candidate is None:
            return
        key = candidate.condition_id or candidate.market_id or candidate.market_slug or candidate.event_slug or candidate.question
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    def _asset(self, text: str) -> str | None:
        aliases = {"BTC": ("btc", "bitcoin"), "ETH": ("eth", "ethereum"), "SOL": ("sol", "solana")}
        for asset in self.assets:
            if any(re.search(rf"\b{re.escape(word)}\b", text) for word in aliases.get(asset, (asset.lower(),))):
                return asset
        return None

    def _timeframe(self, text: str) -> str | None:
        for timeframe in self.timeframes:
            compact = timeframe.lower()
            spaced = compact.replace("m", " minutes").replace("h", " hours")
            compact_match = re.search(rf"(?<![a-z0-9]){re.escape(compact)}(?![a-z0-9])", text)
            minute_match = re.search(rf"(?<![a-z0-9]){re.escape(compact.replace('m', 'min'))}(?![a-z0-9])", text)
            spaced_match = re.search(rf"(?<![a-z0-9]){re.escape(spaced)}(?![a-z0-9])", text)
            singular_match = re.search(rf"(?<![a-z0-9]){re.escape(spaced.rstrip('s'))}(?![a-z0-9])", text)
            if compact_match or minute_match or spaced_match or singular_match or (compact == "1h" and "hourly" in text):
                return timeframe
        return None

    @staticmethod
    def _market_rows(markets: Any) -> list[dict[str, Any]]:
        if isinstance(markets, dict):
            for key in ("events", "markets", "data", "results"):
                value = markets.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            return [markets]
        if isinstance(markets, list):
            return [row for row in markets if isinstance(row, dict)]
        return []

    @classmethod
    def _event_rows(cls, events: Any) -> list[dict[str, Any]]:
        return cls._market_rows(events)

    @staticmethod
    def _tokens(market: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("tokens", "clobTokenIds", "outcomes"):
            value = market.get(key)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = [item.strip() for item in value.split(",") if item.strip()]
            if isinstance(value, list):
                return [item if isinstance(item, dict) else {"value": item} for item in value]
        return []

    @classmethod
    def _gamma_tokens(cls, market: dict[str, Any]) -> list[dict[str, Any]]:
        outcomes = cls._json_list(market.get("outcomes"))
        prices = cls._json_list(market.get("outcomePrices"))
        token_ids = cls._json_list(market.get("clobTokenIds"))
        tokens: list[dict[str, Any]] = []
        for index, outcome in enumerate(outcomes):
            token = {"outcome": str(outcome)}
            if index < len(token_ids):
                token["token_id"] = str(token_ids[index])
            if index < len(prices):
                price = cls._float(prices[index])
                if price is not None:
                    token["price"] = price
            tokens.append(token)
        return tokens

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [item.strip() for item in value.split(",") if item.strip()]
        return value if isinstance(value, list) else []

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _token_id(token: dict[str, Any] | None) -> str | None:
        if not token:
            return None
        value = token.get("token_id") or token.get("asset_id") or token.get("id") or token.get("value")
        return str(value) if value is not None else None

    @classmethod
    def _books_by_token(cls, books: Any) -> dict[str, dict[str, Any]]:
        rows = cls._market_rows(books)
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            token_id = row.get("token_id") or row.get("asset_id") or row.get("assetId") or row.get("id")
            if token_id is not None:
                result[str(token_id)] = row
        return result

    def _apply_book(self, candidate: MarketCandidate, side: str, book: dict[str, Any] | None) -> None:
        if not book:
            return
        bids = self._levels(book.get("bids") or book.get("buys"), reverse=True)
        asks = self._levels(book.get("asks") or book.get("sells"), reverse=False)
        if side == "up":
            candidate.bids_up = bids
            candidate.asks_up = asks
            candidate.best_bid_up = bids[0]["price"] if bids else candidate.best_bid_up
            candidate.best_ask_up = asks[0]["price"] if asks else candidate.best_ask_up
        else:
            candidate.bids_down = bids
            candidate.asks_down = asks
            candidate.best_bid_down = bids[0]["price"] if bids else candidate.best_bid_down
            candidate.best_ask_down = asks[0]["price"] if asks else candidate.best_ask_down

    @classmethod
    def _levels(cls, levels: Any, *, reverse: bool) -> list[dict[str, float]]:
        rows = levels if isinstance(levels, list) else []
        parsed = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = cls._float(row.get("price"))
            size = cls._float(row.get("size"))
            if price is not None and size is not None:
                parsed.append({"price": price, "size": size})
        return sorted(parsed, key=lambda level: level["price"], reverse=reverse)

    @staticmethod
    def _mirror_books(candidate: MarketCandidate) -> None:
        if candidate.best_ask_down is None and candidate.best_bid_up is not None:
            candidate.best_ask_down = round(1 - candidate.best_bid_up, 6)
        if candidate.best_bid_down is None and candidate.best_ask_up is not None:
            candidate.best_bid_down = round(1 - candidate.best_ask_up, 6)
        if candidate.best_ask_up is None and candidate.best_bid_down is not None:
            candidate.best_ask_up = round(1 - candidate.best_bid_down, 6)
        if candidate.best_bid_up is None and candidate.best_ask_down is not None:
            candidate.best_bid_up = round(1 - candidate.best_ask_down, 6)

    @staticmethod
    def _spread(candidate: MarketCandidate) -> float | None:
        spreads = []
        if candidate.best_bid_up is not None and candidate.best_ask_up is not None:
            spreads.append(candidate.best_ask_up - candidate.best_bid_up)
        if candidate.best_bid_down is not None and candidate.best_ask_down is not None:
            spreads.append(candidate.best_ask_down - candidate.best_bid_down)
        return round(min(spreads), 6) if spreads else candidate.spread


def _first_token(tokens: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for token in tokens:
        outcome = str(token.get("outcome") or token.get("name") or token.get("value") or "").lower()
        if outcome == name or name in outcome:
            return token
    return None
