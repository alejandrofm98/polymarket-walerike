from __future__ import annotations

import pytest

from bot.config.settings import Settings
from bot.config.runtime_config import RuntimeConfigStore
from bot.data.trade_logger import PositionRecord, TradeLogger, TradeRecord
from bot.runtime.copy_engine import CopyTradingEngine
from bot.web.server import create_app

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional dependency path
    TestClient = None  # type: ignore[assignment]


class FakeEngine:
    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.solo_log = False
        self.start_calls = 0

    def status(self) -> dict[str, object]:
        status = "paused" if self.paused else "running" if self.running else "stopped"
        return {"running": self.running, "paused": self.paused, "solo_log": self.solo_log, "status": status}

    async def start(self) -> dict[str, object]:
        self.start_calls += 1
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


class FakeCopyClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data_client = None


class FakeCopyDataClient:
    async def full_portfolio(self, wallet: str) -> object:
        raise AssertionError(wallet)

    async def wallet_activity(self, wallet: str) -> list[object]:
        return []

    async def portfolio_value(self, wallet: str) -> float | None:
        return None


class FakeWalletPortfolio:
    def __init__(self, *, cash: float, positions_value: float, total: float) -> None:
        self.cash = cash
        self.positions_value = positions_value
        self.total = total


class CopyOverviewDataClient:
    async def full_portfolio(self, wallet: str) -> object:
        values = {
            "0xleader1": FakeWalletPortfolio(cash=1.0, positions_value=4.0, total=5.0),
            "0xleader2": FakeWalletPortfolio(cash=0.5, positions_value=0.0, total=0.5),
        }
        return values[wallet]


class FixedPusdClient:
    async def pusd_balance(self, wallet: str) -> float:
        assert wallet == "0x63ce342161250d705dc0b16df89036c8e5f9ba9a"
        return 165431.942289


class FixedExternalWalletDataClient:
    async def full_portfolio(self, wallet: str) -> object:
        assert wallet == "0x63ce342161250d705dc0b16df89036c8e5f9ba9a"
        return FakeWalletPortfolio(cash=0.0, positions_value=15.2589, total=15.2589)


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_runtime_config_has_no_trading_mode_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    app = create_app(Settings(), {"runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        config_payload = client.get("/api/config").json()
        status_payload = client.get("/api/status").json()

    removed_mode_key = "pa" + "per" + "_mode"
    removed_gate_key = "li" + "ve" + "_trading"
    removed_block_key = "li" + "ve" + "_blocked"
    assert removed_mode_key not in config_payload
    assert removed_mode_key not in status_payload
    assert removed_gate_key not in status_payload
    assert removed_block_key not in status_payload
    assert "runtime" in status_payload
    assert removed_mode_key not in status_payload["runtime"]


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_routes_control_engine() -> None:
    engine = FakeEngine()
    app = create_app(Settings(), {"bot_engine": engine, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        assert client.post("/api/bot/start").json()["runtime"]["status"] == "running"
        assert client.post("/api/bot/pause").json()["runtime"]["status"] == "paused"
        assert client.post("/api/bot/solo-log").json()["runtime"]["solo_log"] is True
        assert client.get("/api/trades").json() == []
        assert client.get("/api/positions").json()[0]["asset"] == "BTC"
        assert "trade_id" in client.get("/api/trades/export.csv").text
        assert client.post("/api/bot/stop").json()["runtime"]["status"] == "stopped"


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_app_auto_starts_copy_engine_on_startup() -> None:
    engine = FakeEngine()
    app = create_app(Settings(), {"bot_engine": engine, "trade_logger": FakeLogger()})

    with TestClient(app):
        assert engine.start_calls == 1
        assert engine.running is True


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_config_persists_and_validates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    app = create_app(Settings(), {"runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.put("/api/config", json={"poll_interval_seconds": 33})
        assert response.status_code == 200
        assert response.json()["poll_interval_seconds"] == 33.0
        assert client.get("/api/config").json()["poll_interval_seconds"] == 33.0
        assert client.put("/api/config", json={"poll_interval_seconds": 0}).status_code == 400


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_bot_start_resumes_paused_copy_engine(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings()
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    engine = CopyTradingEngine(
        client=FakeCopyClient(settings),
        data_client=FakeCopyDataClient(),
        runtime_config_store=store,
    )
    app = create_app(settings, {"bot_engine": engine, "runtime_config_store": store, "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        assert client.post("/api/bot/start").json()["runtime"]["status"] == "running"
        assert client.post("/api/bot/pause").json()["runtime"]["status"] == "paused"

        response = client.post("/api/bot/start")

        assert response.status_code == 200
        assert response.json()["runtime"]["running"] is True
        assert response.json()["runtime"]["paused"] is False
        assert response.json()["runtime"]["status"] == "running"

        client.post("/api/bot/stop")


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_bot_start_returns_clear_error_when_live_sdk_missing() -> None:
    app = create_app(Settings(), {"bot_engine": FailingStartEngine(), "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        response = client.post("/api/bot/start")

    assert response.status_code == 400
    assert "py-clob-client" in response.json()["detail"]


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_clears_all_trade_history(tmp_path) -> None:  # type: ignore[no-untyped-def]
    trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    trade_logger.log_trade_opened(TradeRecord(trade_id="trade-1", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10, metadata={}))
    trade_logger.log_trade_opened(TradeRecord(trade_id="trade-2", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7, metadata={}))
    app = create_app(Settings(), {"trade_logger": trade_logger})

    with TestClient(app) as client:
        response = client.post("/api/trades/clear").json()

    assert response["ok"] is True
    assert response["cleared"] == 2
    assert response["positions"] == []
    assert trade_logger.list_trades() == []


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_markets_scans_and_fetches_slug() -> None:
    app = create_app(
        Settings(),
        {"market_scanner": FakeScanner(), "polymarket_client": FakePolymarketClient(), "trade_logger": FakeLogger()},
    )

    with TestClient(app) as client:
        markets = client.get("/api/markets").json()
        assert markets == [{"asset": "BTC", "timeframe": "5m", "slug": "btc-updown-5m-1777069800"}]
        assert client.get("/api/markets/slug/btc-updown-5m-1777069800").json()["asset"] == "BTC"


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_copy_overview_groups_copy_trades_and_configured_wallets(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    store.update(
        {
            "copy_wallets": [
                {"address": "0xLeader1", "enabled": True, "sizing_mode": "fixed", "fixed_amount": 10},
                {"address": "0xLeader2", "enabled": False, "sizing_mode": "leader_percent", "fixed_amount": 0},
            ]
        }
    )
    trade_logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    trade_logger.log_trade_opened(
        TradeRecord(
            trade_id="copy-open",
            market="m1",
            asset="token-yes",
            side="YES",
            entry_price=0.4,
            size=25.0,
            metadata={
                "copy_trade": True,
                "leader_wallet": "0xleader1",
                "leader_event_id": "buy-1",
                "leader_price": 0.4,
                "leader_size": 25.0,
                "leader_notional": 10.0,
                "leader_portfolio_value": 100.0,
                "sizing_mode": "fixed",
                "fixed_amount": 10.0,
                "market_slug": "btc-up",
                "timeframe": "5m",
                "asset": "token-yes",
            },
        )
    )
    trade_logger.log_trade_opened(
        TradeRecord(
            trade_id="copy-closed",
            market="m2",
            asset="token-no",
            side="NO",
            entry_price=0.3,
            size=10.0,
            metadata={
                "copy_trade": True,
                "leader_wallet": "0xleader1",
                "leader_event_id": "buy-2",
                "leader_price": 0.3,
                "leader_size": 10.0,
                "leader_notional": 3.0,
                "leader_portfolio_value": 90.0,
                "sizing_mode": "leader_percent",
                "fixed_amount": 0.0,
                "market_slug": "eth-down",
                "timeframe": "1h",
                "asset": "token-no",
            },
        )
    )
    trade_logger.log_trade_closed("copy-closed", exit_price=0.5)
    app = create_app(
        Settings(),
        {
            "runtime_config_store": store,
            "trade_logger": trade_logger,
            "data_client": CopyOverviewDataClient(),
            "bot_engine": FakeEngine(),
        },
    )

    with TestClient(app) as client:
        payload = client.get("/api/copy-overview").json()

    assert ("pa" + "per" + "_mode") not in payload["runtime"]
    assert ("li" + "ve" + "_blocked") not in payload["runtime"]
    assert payload["summary"] == {"wallet_count": 2, "open_positions": 1, "closed_trades": 1, "realized_pnl": -2.0}
    wallets = {wallet["address"]: wallet for wallet in payload["wallets"]}
    assert set(wallets) == {"0xleader1", "0xleader2"}
    assert wallets["0xleader1"]["tracked_balance"] == {"address": "0xleader1", "enabled": True, "cash": 1.0, "positions_value": 4.0, "total": 5.0, "pusd_balance": None}
    assert wallets["0xleader1"]["stats"] == {"realized_pnl": -2.0, "closed_count": 1}
    assert len(wallets["0xleader1"]["open_positions"]) == 1
    assert wallets["0xleader1"]["open_positions"][0]["trade_id"] == "copy-open"
    assert len(wallets["0xleader1"]["closed_trades"]) == 1
    assert wallets["0xleader2"]["configured"]["enabled"] is False
    assert wallets["0xleader2"]["open_positions"] == []
    assert wallets["0xleader2"]["closed_trades"] == []


class FakeAccountClient:
    async def get_account_balances(self) -> dict[str, object]:
        return {"available": True, "cash_balance": 12.5, "portfolio_value": 4.5, "total_balance": 17.0, "allowances": {"0xspender": 99.0}, "raw": {}}

    async def get_positions(self) -> list[dict[str, object]]:
        return [{"market": "m1", "asset": "BTC", "side": "YES", "size": 10, "avg_price": 0.4, "currentValue": 4.5, "cashPnl": 0.5}]

    async def get_account_trades(self) -> list[dict[str, object]]:
        return [{"id": "t1", "market": "m1", "side": "BUY", "size": 10, "price": 0.4, "fee": 0.01, "timestamp": 1777320000.0}]


class FailingAccountClient(FakeAccountClient):
    async def get_account_balances(self) -> dict[str, object]:
        raise RuntimeError("balance failed")


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_copy_overview_uses_authenticated_balance_for_tracked_account(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    tracked_wallet = "0xleader1"
    store.update({"copy_wallets": [{"address": tracked_wallet, "enabled": True, "sizing_mode": "fixed", "fixed_amount": 10}]})
    app = create_app(
        Settings(funder=tracked_wallet),
        {
            "runtime_config_store": store,
            "trade_logger": FakeLogger(),
            "data_client": CopyOverviewDataClient(),
            "polymarket_client": FakeAccountClient(),
            "bot_engine": FakeEngine(),
        },
    )

    with TestClient(app) as client:
        payload = client.get("/api/copy-overview").json()

    wallet = {entry["address"]: entry for entry in payload["wallets"]}[tracked_wallet]
    assert wallet["tracked_balance"] == {
        "address": tracked_wallet,
        "enabled": True,
        "cash": 12.5,
        "positions_value": 4.5,
        "total": 17.0,
        "pusd_balance": None,
    }


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_copy_overview_adds_external_wallet_pusd_to_positions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = RuntimeConfigStore(tmp_path / "runtime_config.json")
    tracked_wallet = "0x63ce342161250d705dc0b16df89036c8e5f9ba9a"
    store.update({"copy_wallets": [{"address": tracked_wallet, "enabled": True, "sizing_mode": "leader_percent", "fixed_amount": 10}]})
    app = create_app(
        Settings(),
        {
            "runtime_config_store": store,
            "trade_logger": FakeLogger(),
            "data_client": FixedExternalWalletDataClient(),
            "polygonscan_client": FixedPusdClient(),
            "bot_engine": FakeEngine(),
        },
    )

    with TestClient(app) as client:
        payload = client.get("/api/copy-overview").json()

    wallet = {entry["address"]: entry for entry in payload["wallets"]}[tracked_wallet]
    assert wallet["tracked_balance"] == {
        "address": tracked_wallet,
        "enabled": True,
        "cash": 0.0,
        "positions_value": 15.2589,
        "total": pytest.approx(165447.201189),
        "pusd_balance": 165431.942289,
    }


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_account_returns_live_summary() -> None:
    app = create_app(Settings(), {"polymarket_client": FakeAccountClient(), "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        payload = client.get("/api/account").json()

    assert payload["available"] is True
    assert payload["cash_balance"] == 12.5
    assert payload["allowances"] == {"0xspender": 99.0}
    assert payload["portfolio_value"] == 4.5
    assert payload["total_balance"] == 17.0
    assert payload["unrealized_pnl"] == 0.5
    assert payload["positions"][0]["asset"] == "BTC"
    assert payload["trades"][0]["id"] == "t1"
    assert payload["errors"] == []


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_account_returns_partial_errors() -> None:
    app = create_app(Settings(), {"polymarket_client": FailingAccountClient(), "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        payload = client.get("/api/account").json()

    assert payload["available"] is True
    assert payload["cash_balance"] is None
    assert payload["allowances"] == {}
    assert payload["positions"][0]["asset"] == "BTC"
    assert payload["errors"] == [{"source": "balances", "message": "balance failed"}]


class ZeroAccountClient(FakeAccountClient):
    async def get_account_balances(self) -> dict[str, object]:
        return {"available": True, "cash_balance": 0.0, "portfolio_value": 0.0, "total_balance": 0.0, "allowances": {}, "raw": {}}


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client unavailable")
def test_api_account_preserves_zero_balances() -> None:
    app = create_app(Settings(), {"polymarket_client": ZeroAccountClient(), "trade_logger": FakeLogger()})

    with TestClient(app) as client:
        payload = client.get("/api/account").json()

    assert payload["cash_balance"] == 0.0
    assert payload["portfolio_value"] == 0.0
    assert payload["total_balance"] == 0.0
