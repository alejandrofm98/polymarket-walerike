"""SQLite trade logger with optional SQLAlchemy engine support."""

from __future__ import annotations

import csv
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


@dataclass(slots=True)
class TradeRecord:
    trade_id: str
    market: str
    asset: str
    side: str
    entry_price: float
    size: float
    status: str = "OPEN"
    opened_at: float | None = None
    closed_at: float | None = None
    exit_price: float | None = None
    pnl: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class PositionRecord:
    market: str
    asset: str
    side: str
    size: float
    avg_price: float
    unrealized_pnl: float = 0.0
    timeframe: str | None = None
    market_slug: str | None = None
    end_date: str | None = None
    window_start_timestamp: int | None = None


class TradeLogger:
    def __init__(self, db_path: str | Path = "data/trades.db", use_sqlalchemy: bool = True) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: Any | None = None
        self._text: Any | None = None
        if use_sqlalchemy:
            self._init_sqlalchemy()
        self._init_schema()

    def log_trade_opened(self, record: TradeRecord) -> TradeRecord:
        opened = record.opened_at or time.time()
        data = asdict(record) | {"opened_at": opened, "status": record.status or "OPEN"}
        self._execute(
            """
            INSERT OR REPLACE INTO trades (
                trade_id, market, asset, side, entry_price, size, status,
                opened_at, closed_at, exit_price, pnl, metadata
            ) VALUES (
                :trade_id, :market, :asset, :side, :entry_price, :size, :status,
                :opened_at, :closed_at, :exit_price, :pnl, :metadata
            )
            """,
            self._serialize(data),
        )
        return TradeRecord(**data)

    def log_trade_closed(
        self,
        trade_id: str,
        exit_price: float,
        status: str = "CLOSED",
        closed_at: float | None = None,
        pnl: float | None = None,
    ) -> TradeRecord | None:
        existing = self.get_trade(trade_id)
        if existing is None:
            return None
        realized = pnl if pnl is not None else round(self._pnl(existing.side, existing.entry_price, exit_price, existing.size), 10)
        self._execute(
            """
            UPDATE trades
            SET status = :status, closed_at = :closed_at, exit_price = :exit_price, pnl = :pnl
            WHERE trade_id = :trade_id
            """,
            {
                "trade_id": trade_id,
                "status": status,
                "closed_at": closed_at or time.time(),
                "exit_price": exit_price,
                "pnl": realized,
            },
        )
        return self.get_trade(trade_id)

    def log_trade_resolved(self, trade_id: str, exit_price: float, pnl: float | None = None) -> TradeRecord | None:
        return self.log_trade_closed(trade_id, exit_price=exit_price, status="RESOLVED", pnl=pnl)

    def cancel_open_paper_trades(self) -> list[TradeRecord]:
        cancelled: list[TradeRecord] = []
        for trade in self.list_trades(status="OPEN"):
            metadata = trade.metadata or {}
            if metadata.get("paper") is not True:
                continue
            closed = self.log_trade_closed(trade.trade_id, exit_price=trade.entry_price, status="CANCELLED", pnl=0.0)
            if closed is not None:
                cancelled.append(closed)
        return cancelled

    def clear_trades(self) -> int:
        count = len(self.list_trades(limit=None))
        self._execute("DELETE FROM trades", {})
        return count

    def resolve_market(
        self,
        market: str,
        winning_side: str,
        *,
        resolved_price: float,
        price_to_beat: float,
    ) -> list[TradeRecord]:
        winner = winning_side.upper()
        resolved: list[TradeRecord] = []
        for trade in self.list_trades(status="OPEN"):
            if trade.market != market:
                continue
            exit_price = 1.0 if trade.side.upper() == winner else 0.0
            metadata = trade.metadata or {}
            fee_paid = float(metadata.get("fee_paid") or 0.0)
            pnl = round((exit_price - float(trade.entry_price)) * float(trade.size) - fee_paid, 10)
            closed = self.log_trade_closed(trade.trade_id, exit_price=exit_price, status="RESOLVED", pnl=pnl)
            if closed is not None:
                resolved.append(closed)
        return resolved

    def get_trade(self, trade_id: str) -> TradeRecord | None:
        rows = self._query("SELECT * FROM trades WHERE trade_id = :trade_id", {"trade_id": trade_id})
        return self._record(rows[0]) if rows else None

    def list_trades(self, status: str | None = None, limit: int | None = None) -> list[TradeRecord]:
        sql = "SELECT * FROM trades"
        params: dict[str, Any] = {}
        if status:
            sql += " WHERE status = :status"
            params["status"] = status
        sql += " ORDER BY opened_at DESC"
        if limit:
            sql += " LIMIT :limit"
            params["limit"] = limit
        return [self._record(row) for row in self._query(sql, params)]

    def list_positions(self) -> list[PositionRecord]:
        grouped: dict[tuple[str, str, str], dict[str, float | str | None]] = {}
        for trade in self.list_trades(status="OPEN"):
            key = (trade.market, trade.asset, trade.side)
            item = grouped.setdefault(key, {"size": 0.0, "cost": 0.0, "timeframe": None, "market_slug": None, "end_date": None, "window_start_timestamp": None})
            item["size"] += float(trade.size)
            item["cost"] += float(trade.entry_price) * float(trade.size)
            if trade.metadata:
                if item["timeframe"] is None:
                    item["timeframe"] = trade.metadata.get("timeframe")
                if item["market_slug"] is None:
                    item["market_slug"] = trade.metadata.get("market_slug")
                if item["end_date"] is None:
                    item["end_date"] = trade.metadata.get("end_date")
                if item["window_start_timestamp"] is None and trade.metadata.get("window_start_timestamp"):
                    item["window_start_timestamp"] = trade.metadata.get("window_start_timestamp")

        positions: list[PositionRecord] = []
        for (market, asset, side), item in grouped.items():
            size = item["size"]
            if size <= 0:
                continue
            positions.append(
                PositionRecord(
                    market=market,
                    asset=asset,
                    side=side,
                    size=size,
                    avg_price=item["cost"] / size,
                    timeframe=item.get("timeframe"),
                    market_slug=item.get("market_slug"),
                    end_date=item.get("end_date"),
                    window_start_timestamp=item.get("window_start_timestamp"),
                )
            )
        return positions

    def export_csv(self, path: str | Path | None = None) -> Path:
        if path is None:
            with NamedTemporaryFile(prefix="trades-", suffix=".csv", delete=False) as tmp:
                path = tmp.name
        csv_path = Path(path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        records = self.list_trades(limit=None)
        fields = [field for field in TradeRecord.__dataclass_fields__]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in records:
                row = asdict(record)
                row["metadata"] = json.dumps(row["metadata"] or {}, sort_keys=True)
                writer.writerow(row)
        return csv_path

    def account_stats(self) -> dict[str, float | int]:
        rows = self._query("SELECT status, size, pnl FROM trades", {})
        total = len(rows)
        open_count = sum(1 for row in rows if row["status"] == "OPEN")
        closed = [row for row in rows if row["status"] != "OPEN"]
        realized = sum(float(row["pnl"] or 0.0) for row in closed)
        wins = sum(1 for row in closed if float(row["pnl"] or 0.0) > 0)
        volume = sum(float(row["size"] or 0.0) for row in rows)
        return {
            "total_trades": total,
            "open_trades": open_count,
            "closed_trades": len(closed),
            "realized_pnl": realized,
            "win_rate": (wins / len(closed)) if closed else 0.0,
            "volume": volume,
        }

    def _init_sqlalchemy(self) -> None:
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            return
        self._engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        self._text = text

    def _init_schema(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                asset TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                size REAL NOT NULL,
                status TEXT NOT NULL,
                opened_at REAL NOT NULL,
                closed_at REAL,
                exit_price REAL,
                pnl REAL,
                metadata TEXT
            )
            """,
            {},
        )

    def _execute(self, sql: str, params: dict[str, Any]) -> None:
        if self._engine is not None and self._text is not None:
            with self._engine.begin() as conn:
                conn.execute(self._text(sql), params)
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, params)

    def _query(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self._engine is not None and self._text is not None:
            with self._engine.connect() as conn:
                result = conn.execute(self._text(sql), params)
                return [dict(row._mapping) for row in result]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params)]

    @staticmethod
    def _serialize(data: dict[str, Any]) -> dict[str, Any]:
        serialized = data.copy()
        serialized["metadata"] = json.dumps(serialized.get("metadata") or {}, sort_keys=True)
        return serialized

    @staticmethod
    def _record(row: dict[str, Any]) -> TradeRecord:
        data = row.copy()
        metadata = data.get("metadata")
        if isinstance(metadata, str):
            data["metadata"] = json.loads(metadata) if metadata else {}
        return TradeRecord(**data)

    @staticmethod
    def _pnl(side: str, entry_price: float, exit_price: float, size: float) -> float:
        direction = 1.0 if side.upper() == "BUY" else -1.0
        return (exit_price - entry_price) * size * direction
