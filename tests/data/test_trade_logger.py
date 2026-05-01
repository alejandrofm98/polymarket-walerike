from __future__ import annotations

from bot.data.trade_logger import TradeLogger, TradeRecord


def test_trade_logger_open_close_list_stats_and_export(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)

    opened = logger.log_trade_opened(
        TradeRecord(
            trade_id="t1",
            market="btc-up",
            asset="BTC",
            side="BUY",
            entry_price=0.4,
            size=10,
            metadata={"source": "test"},
        )
    )
    closed = logger.log_trade_closed("t1", exit_price=0.6)

    assert opened.opened_at is not None
    assert closed is not None
    assert closed.pnl == 2.0
    assert logger.list_trades()[0].metadata == {"source": "test"}
    assert logger.account_stats()["realized_pnl"] == 2.0
    csv_path = logger.export_csv(tmp_path / "trades.csv")
    assert "trade_id" in csv_path.read_text()


def test_missing_trade_close_returns_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)

    assert logger.log_trade_closed("missing", exit_price=0.5) is None


def test_trade_logger_lists_open_positions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    logger.log_trade_opened(TradeRecord(trade_id="t1", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10))
    logger.log_trade_opened(TradeRecord(trade_id="t2", market="m1", asset="BTC", side="YES", entry_price=0.6, size=5))
    logger.log_trade_opened(TradeRecord(trade_id="t3", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7))
    logger.log_trade_closed("t3", exit_price=0.5)

    positions = logger.list_positions()

    assert len(positions) == 1
    assert positions[0].market == "m1"
    assert positions[0].asset == "BTC"
    assert positions[0].side == "YES"
    assert positions[0].size == 15
    assert positions[0].avg_price == (0.4 * 10 + 0.6 * 5) / 15


def test_trade_logger_resolves_market_winner_and_loser(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    logger.log_trade_opened(TradeRecord(trade_id="yes", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10))
    logger.log_trade_opened(TradeRecord(trade_id="no", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7))

    resolved = logger.resolve_market("m1", "YES", resolved_price=101, price_to_beat=100)

    assert len(resolved) == 2
    yes = logger.get_trade("yes")
    no = logger.get_trade("no")
    assert yes is not None and yes.status == "RESOLVED" and yes.exit_price == 1.0 and yes.pnl == 6.0
    assert no is not None and no.status == "RESOLVED" and no.exit_price == 0.0 and no.pnl == -2.1
    assert logger.list_positions() == []


def test_trade_logger_clears_all_trades(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = TradeLogger(tmp_path / "trades.db", use_sqlalchemy=False)
    logger.log_trade_opened(TradeRecord(trade_id="open", market="m1", asset="BTC", side="YES", entry_price=0.4, size=10))
    logger.log_trade_opened(TradeRecord(trade_id="closed", market="m1", asset="BTC", side="NO", entry_price=0.3, size=7))
    logger.log_trade_closed("closed", exit_price=0.5)

    cleared = logger.clear_trades()

    assert cleared == 2
    assert logger.list_trades() == []
    assert logger.list_positions() == []
