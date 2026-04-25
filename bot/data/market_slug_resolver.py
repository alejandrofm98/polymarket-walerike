"""Deterministic Polymarket crypto up/down market slug helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ASSETS = ("BTC", "ETH", "SOL")
TIMEFRAMES = ("5m", "15m", "1h")
SHORT_TIMEFRAME_SECONDS = {"5m": 300, "15m": 900}
HOURLY_SERIES_SLUGS = {
    "BTC": "btc-up-or-down-hourly",
    "ETH": "eth-up-or-down-hourly",
    "SOL": "sol-up-or-down-hourly",
}


def candidate_window_starts(timeframe: str, now_ts: int | float | None = None) -> list[int]:
    """Return previous/current/next window starts for short fixed-interval markets."""
    tf = timeframe.lower()
    if tf not in SHORT_TIMEFRAME_SECONDS:
        raise ValueError("candidate_window_starts only supports 5m and 15m")
    now = int(datetime.now(timezone.utc).timestamp() if now_ts is None else now_ts)
    interval = SHORT_TIMEFRAME_SECONDS[tf]
    current = (now // interval) * interval
    return [current - interval, current, current + interval]


def build_short_slug(asset: str, timeframe: str, window_start_timestamp: int) -> str:
    return f"{asset.lower()}-updown-{timeframe.lower()}-{int(window_start_timestamp)}"


def series_slug(asset: str, timeframe: str) -> str | None:
    symbol = asset.upper()
    tf = timeframe.lower()
    if tf == "1h":
        return HOURLY_SERIES_SLUGS.get(symbol)
    if tf in SHORT_TIMEFRAME_SECONDS:
        return f"{symbol.lower()}-updown-{tf}"
    return None


def select_active_event(events: Any, now_ts: int | float | None = None) -> dict[str, Any] | None:
    rows = _rows(events)
    active = [row for row in rows if _not_false(row.get("active")) and not _true(row.get("closed"))]
    if not active:
        return None
    now = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() if now_ts is None else float(now_ts), timezone.utc)

    current: list[tuple[datetime, dict[str, Any]]] = []
    future: list[tuple[datetime, dict[str, Any]]] = []
    for row in active:
        start = _parse_iso(row.get("eventStartTime") or row.get("startTime") or row.get("startDate"))
        end = _parse_iso(row.get("endDate") or row.get("endTime"))
        if start is not None and end is not None and start <= now < end:
            current.append((start, row))
        elif start is not None and start > now:
            future.append((start, row))
    if current:
        return sorted(current, key=lambda item: item[0])[0][1]
    if future:
        return sorted(future, key=lambda item: item[0])[0][1]
    return active[0]


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("events", "data", "results", "markets"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _not_false(value: Any) -> bool:
    return value is not False and str(value).strip().lower() != "false"


def _true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}
