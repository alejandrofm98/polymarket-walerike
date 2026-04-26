from __future__ import annotations

import pytest

from bot.config.settings import Settings
from bot.config.runtime_config import RuntimeConfigStore
from bot.data.trade_logger import PositionRecord, TradeLogger, TradeRecord
import bot.web.api_routes as api_routes_module
from bot.web.server import create_app

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional dependency path
    TestClient = None  # type: ignore[assignment]


class FakeEngine:
    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.paper = True
        self.solo_log = False

    def status(self) -> dict[str, object]:
        status = "paused" if self.paused else "running" if self.running else "stopped"
        return {"running": self.running, "paused": self.paused, "paper_mode": self.paper, "solo_log": self.solo_log, "status": status}

    async def start(self) -> dict[str, object]:
        self.running = True
        self.paused = False
        return self.status()

    async def pause(self) -> dict[str, object]:
        self.paused = True
        return self.status()

    async def stop(self) -> dict[str, object]:
        self.running = False
        self.paused = False
        return self.status()

    async def set_solo_log(self, enabled: bool) -> dict[str, object]:
        self.solo_log = enabled
        return self.status()

    async def set_paper_mode(self, paper_mode: bool) -> dict[str, object]:
        self.paper = paper_mode
        return self.status()


class FailingModeEngine(FakeEngine):
    async def set_paper_mode(self, paper_mode: bool) -> dict[str, object]:
        raise RuntimeError("POLYMARKET_LIVE_TRADING=true required for live mode")


class FailingStartEngine(FakeEngine):
    async def start(self) -> dict[str, object]:
        raise RuntimeError("Live mode requires optional package py-clob-client")


class FakeLogger:
    def list_trades(self) -> list[object]:
        return []

    def list_positions(self) -> list[object]:
        return [PositionRecord(market="m1", asset="BTC", side="YES", size=10, avg_price=0.4)]

    def export_csv(self) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        handle.write("trade_id\n")
        handle.close()
        return handle.name


class FakeScanner:
    async def scan(self) -> list[object]:
        return [FakeCandidate()]

    def parse_gamma_event(self, event: dict[str, object]) -> object:
        assert event["slug"] == "btc-updown-5m-1777069800"
        return FakeCandidate()


class FakeCandidate:
    def to_dict(self) -> dict[str, object]:
        return {"asset": "BTC", "timeframe": "5m", "slug": "btc-updown-5m-1777069800"}


class FakePolymarketClient:
    async def fetch_event_by_slug(self, slug: str) -> dict[str, object]:
        return {"slug": slug, "markets": []}


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_routes_control_engine() -> None:
    engine = FakeEngine()
    app = create_app(Settings(paper_mode=True, live_trading=False), {"bot_engine": engine, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        assert client.post("/api/bot/start").json()["runtime"]["status"] == "running"
        assert client.post("/api/bot/pause").json()["runtime"]["status"] == "paused"
        assert client.post("/api/bot/solo-log").json()["runtime"]["solo_log"] is True
        assert client.get("/api/status").json()["runtime"]["paper_mode"] is True
        assert client.get("/api/trades").json() == []
        assert client.get("/api/positions").json()[0]["asset"] == "BTC"
        assert "trade_id" in client.get("/api/trades/export.csv").text
        assert client.post("/api/bot/stop").json()["runtime"]["status"] == "stopped"


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_config_persists_and_validates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    app = create_app(Settings(paper_mode=True, live_trading=False), {"runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.put("/api/config", json={"capital_per_trade": 33, "min_margin_for_arbitrage": 0.04})
        assert response.status_code == 200
        assert response.json()["capital_per_trade"] == 33.0
        assert client.get("/api/config").json()["min_margin_for_arbitrage"] == 0.04
        assert client.put("/api/config", json={"capital_per_trade": 0}).status_code == 400


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_status_marks_requested_live_without_env_as_blocked(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    store.update({"paper_mode": False})
    app = create_app(Settings(paper_mode=True, live_trading=False), {"runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        payload = client.get("/api/status").json()

    assert payload["paper_mode"] is True
    assert payload["requested_paper_mode"] is False
    assert payload["live_blocked"] is True
    assert payload["live_block_reason"] == "POLYMARKET_LIVE_TRADING=true required for live mode"
    assert payload["mode_label"] == "Live blocked"
    assert payload["runtime"]["live_blocked"] is True


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_config_switches_mode_without_restart(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(api_routes_module.importlib.util, "find_spec", lambda name: object() if name == "py_clob_client.client" else None)
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    engine = FakeEngine()
    app = create_app(Settings(paper_mode=True, live_trading=True), {"bot_engine": engine, "runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.put("/api/config", json={"paper_mode": False})
        assert response.status_code == 200
        payload = client.get("/api/status").json()

    assert engine.paper is False
    assert payload["paper_mode"] is False
    assert payload["requested_paper_mode"] is False
    assert payload["live_blocked"] is False
    assert payload["mode_label"] == "Live"


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_config_rolls_back_mode_when_switch_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    app = create_app(Settings(paper_mode=True, live_trading=False), {"bot_engine": FailingModeEngine(), "runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.put("/api/config", json={"paper_mode": False})
        persisted = client.get("/api/config").json()

    assert response.status_code == 400
    assert persisted["paper_mode"] is True


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_bot_start_returns_clear_error_when_live_sdk_missing() -> None:
    app = create_app(Settings(paper_mode=False, live_trading=True), {"bot_engine": FailingStartEngine(), "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.post("/api/bot/start")

    assert response.status_code == 400
    assert "py-clob-client" in response.json()["detail"]


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_clears_open_paper_trades(tmp_path) -> None:  # type: ignore[no-untyped-def]
    trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    trade_logger.log_trade_opened(TradeRecord(trade_id="paper", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10, metadata={"paper": True}))
    trade_logger.log_trade_opened(TradeRecord(trade_id="live", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7, metadata={"paper": False}))
    app = create_app(Settings(paper_mode=True, live_trading=False), {"trade_logger": trade_logger})

    with TestClient(app) as client:
        response = client.post("/api/trades/clear-open-paper").json()

    assert response["ok"] is True
    assert response["cleared"] == 1
    assert response["trades"][0]["status"] == "CANCELLED"
    assert trade_logger.get_trade("paper").status == "CANCELLED"  # type: ignore[union-attr]
    assert trade_logger.get_trade("live").status == "OPEN"  # type: ignore[union-attr]


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_clears_all_trade_history(tmp_path) -> None:  # type: ignore[no-untyped-def]
    trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    trade_logger.log_trade_opened(TradeRecord(trade_id="paper", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10, metadata={"paper": True}))
    trade_logger.log_trade_opened(TradeRecord(trade_id="live", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7, metadata={"paper": False}))
    app = create_app(Settings(paper_mode=True, live_trading=False), {"trade_logger": trade_logger})

    with TestClient(app) as client:
        response = client.post("/api/trades/clear").json()

    assert response["ok"] is True
    assert response["cleared"] == 2
    assert response["positions"] == []
    assert trade_logger.list_trades() == []


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_markets_scans_and_fetches_slug() -> None:
    app = create_app(
        Settings(paper_mode=True, live_trading=False),
        {"market_scanner": FakeScanner(), "polymarket_client": FakePolymarketClient(), "trade_logger": FakeLogger()},
    )

    with TestClient(app) as client:
        markets = client.get("/api/markets").json()
        assert markets == [{"asset": "BTC", "timeframe": "5m", "slug": "btc-updown-5m-1777069800"}]
        assert client.get("/api/markets/slug/btc-updown-5m-1777069800").json()["asset"] == "BTC"
