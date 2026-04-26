from __future__ import annotations

import asyncio

from bot.data.market_scanner import MarketScanner


class FakeClient:
    async def get_markets(self) -> dict[str, list[dict[str, object]]]:
        return {
            "markets": [
                {"id": "1", "question": "Will Bitcoin go up in 1h?", "tokens": '["yes", "no"]'},
                {"id": "2", "question": "Will oil close green?"},
            ]
        }


class FakeGammaClient:
    async def fetch_event_by_slug(self, slug: str) -> dict[str, object]:
        return gamma_event(slug)

    async def fetch_crypto_updown_events(self, asset: str, timeframe: str, limit: int = 20) -> dict[str, list[dict[str, object]]]:
        assert asset == "BTC"
        assert timeframe == "5m"
        assert limit == 20
        return {"events": [gamma_event("btc-updown-5m-1777069800")]}


class FakeBookClient:
    async def fetch_order_books(self, token_ids: list[str]) -> list[dict[str, object]]:
        assert token_ids == ["token-up", "token-down"]
        return [
            {"asset_id": "token-up", "bids": [{"price": "0.52", "size": "10"}, {"price": "0.55", "size": "2"}], "asks": [{"price": "0.58", "size": "4"}]},
        ]


def test_filter_crypto_up_down_markets_from_loose_payload() -> None:
    scanner = MarketScanner(FakeClient())

    result = asyncio.run(scanner.scan())

    assert len(result) == 1
    assert result[0].asset == "BTC"
    assert result[0].timeframe == "1h"
    assert result[0].tokens == [{"value": "yes"}, {"value": "no"}]


def test_parser_ignores_non_directional_markets() -> None:
    scanner = MarketScanner(FakeClient(), assets=("ETH",))

    assert scanner.parse_market({"question": "Ethereum weekly volume"}) is None


def test_parse_gamma_event_updown_payload() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["5m"]})

    result = scanner.parse_gamma_event(gamma_event("btc-updown-5m-1777069800"))

    assert result is not None
    assert result.asset == "BTC"
    assert result.timeframe == "5m"
    assert result.event_slug == "btc-updown-5m-1777069800"
    assert result.market_id == "0xcondition"
    assert result.tokens == [
        {"outcome": "Up", "token_id": "token-up", "price": 0.56},
        {"outcome": "Down", "token_id": "token-down", "price": 0.44},
    ]
    assert result.spread == 0.03
    assert result.liquidity == 1234.5
    assert result.to_dict()["up"]["token_id"] == "token-up"


def test_parse_gamma_market_by_slug_payload() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["5m"]})

    result = scanner.parse_market(gamma_event("btc-updown-5m-1777069800")["markets"][0])

    assert result is not None
    assert result.market_slug == "btc-updown-5m-1777069800"
    assert result.condition_id == "0xcondition"
    assert result.up_token_id == "token-up"
    assert result.down_token_id == "token-down"
    assert result.up_price == 0.56
    assert result.down_price == 0.44


def test_timeframe_does_not_match_5m_inside_15m_slug() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["15m"]})
    payload = gamma_event("btc-updown-15m-1777069800")
    payload["title"] = "Bitcoin Up or Down - 15 minutes"
    payload["seriesSlug"] = "btc-updown-15m"
    payload["tags"] = [{"label": "15m"}]

    result = scanner.parse_gamma_event(payload)

    assert result is not None
    assert result.timeframe == "15m"


def test_book_normalization_and_mirror_math() -> None:
    scanner = MarketScanner(FakeBookClient())
    candidate = scanner.parse_gamma_event(gamma_event("btc-updown-5m-1777069800"))
    assert candidate is not None

    asyncio.run(scanner._enrich_books([candidate]))

    assert candidate.bids_up == [{"price": 0.55, "size": 2.0}, {"price": 0.52, "size": 10.0}]
    assert candidate.asks_up == [{"price": 0.58, "size": 4.0}]
    assert candidate.best_bid_up == 0.55
    assert candidate.best_ask_up == 0.58
    assert candidate.best_ask_down == 0.45
    assert candidate.best_bid_down == 0.42
    assert candidate.spread == 0.03
    assert candidate.edge == -0.03
    assert candidate.net_edge == -0.0654


def test_scan_gamma_uses_enabled_pairs_and_dedupes() -> None:
    scanner = MarketScanner(FakeGammaClient(), enabled_markets={"BTC": ["5m"]})

    result = asyncio.run(scanner.scan())

    assert len(result) == 1
    assert result[0].slug == "btc-updown-5m-1777069800"


def gamma_event(slug: str) -> dict[str, object]:
    return {
        "slug": slug,
        "title": "Bitcoin Up or Down - April 2026, 5 minutes",
        "startTime": "2099-04-24T10:00:00Z",
        "endDate": "2099-04-24T10:05:00Z",
        "seriesSlug": "btc-updown-5m",
        "tags": [{"slug": "crypto"}, {"label": "5m"}],
        "markets": [
            {
                "conditionId": "0xcondition",
                "slug": slug,
                "question": "Bitcoin Up or Down?",
                "outcomes": '["Up", "Down"]',
                "outcomePrices": '["0.56", "0.44"]',
                "clobTokenIds": '["token-up", "token-down"]',
                "liquidity": "1000",
                "liquidityClob": "1234.5",
                "bestBid": "0.54",
                "bestAsk": "0.57",
                "acceptingOrders": True,
                "active": True,
                "closed": False,
            }
        ],
    }


def test_set_enabled_markets_filters_scanner() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["5m", "15m"], "ETH": ["5m"]})

    scanner.set_enabled_markets({"BTC": ["5m"], "SOL": ["15m"]})

    assert "BTC" in scanner.enabled_markets
    assert "5m" in scanner.enabled_markets["BTC"]
    assert "15m" not in scanner.enabled_markets.get("BTC", [])
    assert "ETH" not in scanner.enabled_markets
    assert "SOL" in scanner.enabled_markets
    assert "15m" in scanner.enabled_markets["SOL"]


def test_parse_market_respects_enabled_markets() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["5m"]})

    btc_market = {
        "question": "Will Bitcoin go up in 5m?",
        "slug": "btc-updown-5m",
    }
    eth_market = {
        "question": "Will Ethereum go up in 5m?",
        "slug": "eth-updown-5m",
    }

    result_btc = scanner.parse_market(btc_market)
    result_eth = scanner.parse_market(eth_market)

    assert result_btc is not None
    assert result_btc.asset == "BTC"
    assert result_eth is None


def test_configure_updates_enabled_markets() -> None:
    scanner = MarketScanner(FakeClient(), enabled_markets={"BTC": ["5m", "15m"], "ETH": ["5m"]})

    scanner.configure(enabled_markets={"BTC": ["5m"], "SOL": ["1h"]})

    assert scanner.enabled_markets == {"BTC": ["5m"], "SOL": ["1h"]}
