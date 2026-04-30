from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger("walerike.data_client")

BUY_ACTIONS = ("buy", "sell")
YES_NO_SIDES = ("YES", "NO")
DEFAULT_GAMMA_API_URL = "https://gamma-api.polymarket.com"


@dataclass(slots=True)
class WalletActivity:
    event_id: str
    wallet: str
    action: str
    market_id: str
    side: str
    price: float
    size: float
    timestamp: float
    token_id: str | None = None

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(slots=True)
class WalletPortfolio:
    cash: float
    positions_value: float
    total: float


class PolymarketDataClient:
    def __init__(self, base_url: str, gamma_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.gamma_url = (gamma_url or DEFAULT_GAMMA_API_URL).rstrip("/")
        self.timeout = timeout

    async def wallet_activity(self, wallet: str, limit: int = 100) -> list[WalletActivity]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/activity", params={"user": wallet, "limit": limit})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error fetching activity for {wallet}: {exc}")
            return []
        except httpx.RequestError as exc:
            logger.error(f"Network error fetching activity for {wallet}: {exc}")
            return []
        rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            logger.warning(f"wallet_activity expected list, got {type(rows).__name__}")
            return []
        return parse_activity(rows)

    async def portfolio_value(self, wallet: str) -> float | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/value", params={"user": wallet})
                payload = response.json() if response.status_code < 400 else []
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error fetching portfolio for {wallet}: {exc}")
            return None
        except httpx.RequestError as exc:
            logger.error(f"Network error fetching portfolio for {wallet}: {exc}")
            return None
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                return _num(first.get("value"))
        if isinstance(payload, dict):
            return _num(payload.get("value"))
        return 0.0

    async def full_portfolio(self, wallet: str) -> WalletPortfolio:
        positions_value = await self.portfolio_value(wallet) or 0.0
        return WalletPortfolio(cash=0.0, positions_value=positions_value, total=positions_value)


def parse_activity(rows: list[dict[str, Any]]) -> list[WalletActivity]:
    events: list[WalletActivity] = []
    for row in rows:
        action = str(row.get("type") or row.get("action") or "").strip().lower()
        if action not in BUY_ACTIONS:
            continue
        event_id = str(row.get("id") or row.get("transactionHash") or row.get("transaction_hash") or "").strip()
        market_id = str(row.get("market") or row.get("conditionId") or row.get("condition_id") or "").strip()
        side = str(row.get("asset") or row.get("outcome") or row.get("side") or "").strip().upper()
        price = _num(row.get("price"))
        size = _num(row.get("size"))
        timestamp = _num(row.get("timestamp"))
        if not event_id:
            logger.debug(f"skipping row: missing event_id")
            continue
        if not market_id:
            logger.debug(f"skipping row: missing market_id")
            continue
        if side not in YES_NO_SIDES:
            logger.debug(f"skipping row: invalid side {side}")
            continue
        if price <= 0 or size <= 0:
            logger.debug(f"skipping row: invalid price/size {price}/{size}")
            continue
        events.append(WalletActivity(
            event_id=event_id,
            wallet=str(row.get("proxyWallet") or row.get("wallet") or "").strip().lower(),
            action=action,
            market_id=market_id,
            side=side,
            price=price,
            size=size,
            timestamp=timestamp,
            token_id=str(row.get("assetId") or row.get("token_id") or "").strip() or None,
        ))
    return sorted(events, key=lambda event: event.timestamp)


def parse_portfolio_value(payload: dict[str, Any]) -> float:
    cash = _num(payload.get("cash")) if payload.get("cash") is not None else _num(payload.get("cash_balance"))
    positions = payload.get("positions", [])
    total = cash
    if isinstance(positions, list):
        for position in positions:
            if isinstance(position, dict):
                total += _num(position.get("currentValue") or position.get("current_value") or position.get("value"))
    return max(total, 0.0)


def _sum_positions(positions: list[dict[str, Any]]) -> float:
    total = 0.0
    if isinstance(positions, list):
        for position in positions:
            if isinstance(position, dict):
                total += _num(position.get("currentValue") or position.get("current_value") or position.get("value"))
    return total


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cannot convert {value!r} to float") from exc
