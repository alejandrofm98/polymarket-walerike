from __future__ import annotations

from bot.data.market_slug_resolver import build_short_slug, candidate_window_starts, select_active_event, series_slug


def test_candidate_window_starts_for_fixed_timestamps() -> None:
    assert candidate_window_starts("5m", 1777070100) == [1777069800, 1777070100, 1777070400]
    assert candidate_window_starts("15m", 1777070100) == [1777068900, 1777069800, 1777070700]
    assert candidate_window_starts("15m", 1777069800) == [1777068900, 1777069800, 1777070700]


def test_build_short_and_hourly_series_slugs() -> None:
    assert build_short_slug("BTC", "5m", 1777069800) == "btc-updown-5m-1777069800"
    assert series_slug("BTC", "1h") == "btc-up-or-down-hourly"
    assert series_slug("ETH", "1h") == "eth-up-or-down-hourly"
    assert series_slug("SOL", "1h") == "sol-up-or-down-hourly"


def test_select_active_event_prefers_current_then_future() -> None:
    events = [
        {"slug": "old", "active": True, "closed": False, "eventStartTime": "2026-04-24T09:00:00Z", "endDate": "2026-04-24T10:00:00Z"},
        {"slug": "next", "active": True, "closed": False, "eventStartTime": "2026-04-24T11:00:00Z", "endDate": "2026-04-24T12:00:00Z"},
        {"slug": "current", "active": True, "closed": False, "eventStartTime": "2026-04-24T10:00:00Z", "endDate": "2026-04-24T11:00:00Z"},
    ]

    assert select_active_event(events, 1777026600)["slug"] == "current"
    assert select_active_event(events, 1777030200)["slug"] == "next"
