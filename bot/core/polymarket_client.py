"""Async Polymarket CLOB client wrapper with paper trading support."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import logging
import time
import json
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Awaitable, Callable

try:
    from loguru import logger
except ImportError:  # pragma: no cover - keeps paper/tests usable before deps install
    class _FallbackLogger:
        def __init__(self) -> None:
            self._logger = logging.getLogger(__name__)

        def info(self, message: str, *args: Any) -> None:
            self._logger.info(message.format(*args))

        def warning(self, message: str, *args: Any) -> None:
            self._logger.warning(message.format(*args))

    logger = _FallbackLogger()

POLYMARKET_WEB_URL = "https://polymarket.com"

from bot.config.settings import Settings

try:
    import websockets
except ImportError:  # pragma: no cover - optional until websocket use
    websockets = None  # type: ignore[assignment]


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    GTC = "GTC"
    FOK = "FOK"
    GTD = "GTD"


@dataclass(slots=True)
class OrderRequest:
    market: str
    asset_id: str
    side: OrderSide
    price: float
    size: float
    order_type: OrderType = OrderType.GTD
    expiration: int | None = None
    client_order_id: str | None = None


@dataclass(slots=True)
class OrderResponse:
    order_id: str
    status: str
    market: str
    asset_id: str
    side: OrderSide
    price: float
    size: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WebSocketEvent:
    channel: str
    event_type: str
    payload: dict[str, Any]
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventCallback = Callable[[WebSocketEvent], Awaitable[None] | None]


class PolymarketClient:
    def __init__(self, settings: Settings | None = None, paper_mode: bool | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.paper_mode = self.settings.paper_mode if paper_mode is None else paper_mode
        self._clob_client: Any | None = None
        self._sdk: dict[str, Any] = {}
        self._paper_orders: dict[str, OrderResponse] = {}
        self._event_queue: asyncio.Queue[WebSocketEvent] = asyncio.Queue(maxsize=500)
        self._callbacks: list[EventCallback] = []
        self._ws_tasks: list[asyncio.Task[None]] = []
        self._closed = False

    async def connect(self) -> None:
        self._closed = False
        if self.paper_mode:
            logger.info("Polymarket client connected in paper mode")
            return
        self._ensure_live_trading_enabled()
        self._clob_client = self._build_clob_client()
        self._log_live_signing_config(self._clob_client)
        logger.info("Polymarket client connected in live mode")

    async def close(self) -> None:
        self._closed = True
        for task in self._ws_tasks:
            task.cancel()
        for task in self._ws_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._ws_tasks.clear()
        logger.info("Polymarket client closed")

    async def get_markets(self) -> Any:
        if self.paper_mode:
            return []
        client = self._require_clob_client()
        return await self._call_sync(client.get_markets)

    async def fetch_event_by_slug(self, slug: str) -> dict[str, Any]:
        clean_slug = slug.strip().rstrip("/").split("/")[-1]
        if not clean_slug:
            raise ValueError("slug must be non-empty")
        base = self.settings.polymarket_gamma_api_url.rstrip("/")
        url = f"{base}/events/slug/{urllib.parse.quote(clean_slug)}"
        return await self._call_sync(self._fetch_json_url, url)

    async def fetch_market_by_slug(self, slug: str) -> dict[str, Any]:
        clean_slug = slug.strip().rstrip("/").split("/")[-1]
        if not clean_slug:
            raise ValueError("slug must be non-empty")
        base = self.settings.polymarket_gamma_api_url.rstrip("/")
        url = f"{base}/markets/slug/{urllib.parse.quote(clean_slug)}"
        return await self._call_sync(self._fetch_json_url, url)

    async def fetch_events(self, params: dict[str, Any] | None = None) -> Any:
        base = self.settings.polymarket_gamma_api_url.rstrip("/")
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base}/events"
        if query:
            url = f"{url}?{query}"
        return await self._call_sync(self._fetch_json_url, url)

    async def fetch_crypto_updown_events(self, asset: str, timeframe: str, limit: int = 20) -> Any:
        query = f"{asset.upper()} updown {timeframe.lower()}"
        return await self.fetch_events({"q": query, "limit": limit, "active": "true", "closed": "false"})

    async def fetch_order_books(self, token_ids: list[str]) -> Any:
        clean = [str(token_id) for token_id in token_ids if str(token_id)]
        if not clean:
            return []
        url = f"{self.settings.polymarket_host.rstrip('/')}/books"
        return await self._call_sync(self._post_json_url, url, [{"token_id": token_id} for token_id in clean])

    async def fetch_order_book(self, token_id: str) -> Any:
        if not str(token_id):
            raise ValueError("token_id must be non-empty")
        query = urllib.parse.urlencode({"token_id": str(token_id)})
        url = f"{self.settings.polymarket_host.rstrip('/')}/book?{query}"
        return await self._call_sync(self._fetch_json_url, url)

    async def get_orders(self) -> Any:
        if self.paper_mode:
            return list(self._paper_orders.values())
        client = self._require_clob_client()
        return await self._call_sync(client.get_orders)

    async def get_trades(self) -> Any:
        if self.paper_mode:
            return []
        client = self._require_clob_client()
        return await self._call_sync(client.get_trades)

    async def get_positions(self) -> Any:
        if self.paper_mode:
            return []
        if not self.settings.funder:
            logger.warning("POLYMARKET_FUNDER required for positions Data API")
            return []
        return await self._call_sync(self._fetch_positions, self.settings.funder)

    async def get_account_balances(self) -> dict[str, Any]:
        if self.paper_mode:
            return {"available": False, "reason": "live account data requires live mode"}
        client = self._require_clob_client()
        if not hasattr(client, "get_balance_allowance"):
            return {"available": False, "reason": "CLOB client does not expose balance reads"}
        raw = await self._call_sync(client.get_balance_allowance, self._balance_allowance_params())
        data = raw if isinstance(raw, dict) else {"raw": raw}
        return {
            "available": True,
            "cash_balance": self._usdc_amount(data.get("balance")),
            "allowance": self._usdc_amount(data.get("allowance")),
            "raw": data,
        }

    async def get_account_trades(self) -> list[dict[str, Any]]:
        if self.paper_mode:
            return []
        raw = await self.get_trades()
        if not isinstance(raw, list):
            return []
        return [self._normalize_account_trade(item) for item in raw if isinstance(item, dict)]

    async def fetch_page_html(self, path_or_slug: str) -> str | None:
        """Fetch HTML page content for a Polymarket event/market slug."""
        clean_slug = path_or_slug.strip().rstrip("/").split("/")[-1]
        if not clean_slug:
            return None
        url = f"{POLYMARKET_WEB_URL}/event/{urllib.parse.quote(clean_slug)}"
        try:
            result = await self._call_sync(self._fetch_text_url, url)
            return result
        except Exception as exc:
            logger.warning("Failed to fetch page HTML for {}: {}", clean_slug, exc)
            return None

    async def fetch_crypto_price(self, symbol: str, event_start_time: str, variant: str, end_date: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "symbol": symbol.upper(),
            "eventStartTime": event_start_time,
            "variant": variant,
            "endDate": end_date,
        })
        url = f"{POLYMARKET_WEB_URL}/api/crypto/crypto-price?{query}"
        return await self._call_sync(self._fetch_json_url, url)

    async def fetch_past_results(self, symbol: str, current_event_start_time: str, end_date: str, count: int = 4) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "symbol": symbol.upper(),
            "variant": "hourly",
            "assetType": "crypto",
            "currentEventStartTime": current_event_start_time,
            "count": count,
            "endDate": end_date,
            "includeOutcomesBySlug": "true",
        })
        url = f"{POLYMARKET_WEB_URL}/api/past-results?{query}"
        return await self._call_sync(self._fetch_json_url, url)

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        self._validate_order(request)
        if self.paper_mode:
            order_id = f"paper-{uuid.uuid4().hex}"
            response = OrderResponse(
                order_id=order_id,
                status="OPEN",
                market=request.market,
                asset_id=request.asset_id,
                side=request.side,
                price=request.price,
                size=request.size,
                raw={"paper": True, "client_order_id": request.client_order_id},
            )
            self._paper_orders[order_id] = response
            logger.info("Paper order placed: {}", order_id)
            return response

        client = self._require_clob_client()
        sdk = self._require_sdk()
        side = sdk["BUY"] if request.side is OrderSide.BUY else sdk["SELL"]
        args = {
            "token_id": request.asset_id,
            "price": request.price,
            "size": request.size,
            "side": side,
        }
        if request.expiration is not None:
            args["expiration"] = request.expiration
        signed = await self._call_sync(client.create_order, sdk["OrderArgs"](**args))
        raw = await self._call_sync(client.post_order, signed, self._sdk_order_type(request.order_type))
        return self._order_response_from_raw(request, raw)

    async def cancel_order(self, order_id: str) -> bool:
        if self.paper_mode:
            order = self._paper_orders.pop(order_id, None)
            if order is None:
                return False
            logger.info("Paper order canceled: {}", order_id)
            return True
        client = self._require_clob_client()
        await self._call_sync(client.cancel, order_id)
        return True

    async def subscribe_market(self, market: str, asset_ids: list[str] | None = None) -> asyncio.Queue[WebSocketEvent]:
        payload = self.build_market_subscribe_payload(asset_ids or [market])
        self._start_ws(payload, "market")
        return self._event_queue

    async def subscribe_user(self, markets: list[str] | None = None) -> asyncio.Queue[WebSocketEvent]:
        payload = self.build_user_subscribe_payload(markets or [])
        self._start_ws(payload, "user")
        return self._event_queue

    def build_market_subscribe_payload(self, asset_ids: list[str]) -> dict[str, Any]:
        return {"type": "market", "assets_ids": asset_ids}

    def build_user_subscribe_payload(self, markets: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "user", "markets": markets}
        if self.settings.api_key:
            payload["auth"] = {"apiKey": self.settings.api_key}
        return payload

    def register_callback(self, callback: EventCallback) -> None:
        self._callbacks.append(callback)

    @property
    def events(self) -> asyncio.Queue[WebSocketEvent]:
        return self._event_queue

    def _build_clob_client(self) -> Any:
        try:
            client_module = importlib.import_module("py_clob_client.client")
            types_module = importlib.import_module("py_clob_client.clob_types")
            constants_module = importlib.import_module("py_clob_client.order_builder.constants")
        except ImportError as exc:
            raise RuntimeError("Live mode requires optional package py-clob-client") from exc
        self._sdk = {
            "ApiCreds": types_module.ApiCreds,
            "BalanceAllowanceParams": getattr(types_module, "BalanceAllowanceParams", None),
            "OrderArgs": types_module.OrderArgs,
            "OrderType": types_module.OrderType,
            "OpenOrderParams": types_module.OpenOrderParams,
            "TradeParams": types_module.TradeParams,
            "BUY": constants_module.BUY,
            "SELL": constants_module.SELL,
        }
        kwargs: dict[str, Any] = {
            "host": self.settings.polymarket_host,
            "key": self.settings.private_key,
            "chain_id": self.settings.chain_id,
        }
        if self.settings.funder:
            kwargs["funder"] = self.settings.funder
        if self.settings.signature_type is not None:
            kwargs["signature_type"] = self.settings.signature_type
        env_creds = self._env_api_creds(types_module)
        if env_creds is not None:
            kwargs["creds"] = env_creds
        client = client_module.ClobClient(**kwargs)
        if env_creds is None and self.settings.live_trading and self.settings.private_key and hasattr(client, "create_or_derive_api_creds"):
            client.set_api_creds(client.create_or_derive_api_creds())
        return client

    def _env_api_creds(self, types_module: Any) -> Any | None:
        if not any((self.settings.api_secret, self.settings.api_passphrase)):
            return None
        values = (self.settings.api_key, self.settings.api_secret, self.settings.api_passphrase)
        if not all(values):
            missing = [
                name
                for name, value in (
                    ("POLYMARKET_API_KEY", self.settings.api_key),
                    ("POLYMARKET_API_SECRET", self.settings.api_secret),
                    ("POLYMARKET_API_PASSPHRASE", self.settings.api_passphrase),
                )
                if not value
            ]
            raise RuntimeError(f"Incomplete CLOB API credentials: missing {', '.join(missing)}")
        return types_module.ApiCreds(
            api_key=str(self.settings.api_key),
            api_secret=str(self.settings.api_secret),
            api_passphrase=str(self.settings.api_passphrase),
        )

    def _log_live_signing_config(self, client: Any) -> None:
        signer = None
        with contextlib.suppress(Exception):
            signer = client.get_address() if hasattr(client, "get_address") else None
        funder = str(self.settings.funder or signer or "") or None
        signature_type = self.settings.signature_type
        if signature_type is None:
            signature_type = 0
        auth_mode = "env_creds" if all((self.settings.api_key, self.settings.api_secret, self.settings.api_passphrase)) else "derived_creds"
        logger.info(
            "live signing config signer={} funder={} signature_type={} api_key_address={} auth_mode={}",
            self._mask_address(signer),
            self._mask_address(funder),
            signature_type,
            self._mask_address(self.settings.api_key_address),
            auth_mode,
        )
        self._warn_live_signing_config(signer, funder, signature_type)

    def _warn_live_signing_config(self, signer: str | None, funder: str | None, signature_type: int) -> None:
        signer_l = str(signer or "").lower()
        funder_l = str(funder or "").lower()
        api_key_l = str(self.settings.api_key_address or "").lower()
        external_l = str(self.settings.external_wallet_address or "").lower()
        if api_key_l and signer_l and api_key_l != signer_l:
            logger.warning(
                "CLOB API key address does not match signer address: api_key_address={} signer={}",
                self._mask_address(self.settings.api_key_address),
                self._mask_address(signer),
            )
        if external_l and signer_l and external_l != signer_l:
            logger.warning(
                "POLYMARKET_EXTERNAL_WALLET_ADDRESS does not match signer private key: external={} signer={}",
                self._mask_address(self.settings.external_wallet_address),
                self._mask_address(signer),
            )
        if signature_type == 0 and funder_l and signer_l and funder_l != signer_l:
            logger.warning("signature_type=0 expects funder to equal signer or be empty")
        if signature_type in {1, 2} and not funder_l:
            logger.warning("signature_type={} expects POLYMARKET_FUNDER to be set", signature_type)

    @staticmethod
    def _mask_address(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= 14:
            return text
        return f"{text[:8]}...{text[-6:]}"

    def _require_clob_client(self) -> Any:
        self._ensure_live_trading_enabled()
        if self._clob_client is None:
            try:
                self._clob_client = self._build_clob_client()
            except ImportError as exc:
                raise RuntimeError("Live mode requires optional package py-clob-client") from exc
        return self._clob_client

    def _validate_order(self, request: OrderRequest) -> None:
        if not 0.01 <= request.price <= 0.99:
            raise ValueError("price must be between 0.01 and 0.99")
        if request.size < 0.01:
            raise ValueError("size must be >= 0.01")
        if request.order_type is OrderType.GTD and request.expiration is None:
            raise ValueError("GTD orders require expiration")
        if request.order_type is OrderType.GTD and request.expiration <= int(time.time()):
            raise ValueError("GTD expiration must be in the future")

    def _require_sdk(self) -> dict[str, Any]:
        if not self._sdk:
            self._require_clob_client()
        return self._sdk

    def _ensure_live_trading_enabled(self) -> None:
        if not self.paper_mode and not self.settings.live_trading:
            raise RuntimeError("POLYMARKET_LIVE_TRADING=true required for live CLOB access")

    @staticmethod
    def live_sdk_available() -> bool:
        try:
            return importlib.util.find_spec("py_clob_client.client") is not None
        except ModuleNotFoundError:
            return False

    def _sdk_order_type(self, order_type: OrderType) -> Any:
        sdk_order_type = self._require_sdk()["OrderType"]
        return getattr(sdk_order_type, order_type.value, order_type.value)

    def _ws_url(self, channel: str) -> str:
        if channel == "market":
            return self.settings.polymarket_market_ws_url
        if channel == "user":
            return self.settings.polymarket_user_ws_url
        base = self.settings.polymarket_ws_url.rstrip("/")
        if base.endswith(f"/{channel}"):
            return base
        return f"{base}/{channel}"

    def _fetch_positions(self, funder: str) -> Any:
        query = urllib.parse.urlencode({"user": funder})
        url = f"{self.settings.polymarket_data_api_url.rstrip('/')}/positions?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; polymarket-walerike/0.1)",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - endpoint configurable for tests
            return self._json_loads(response.read())

    def _balance_allowance_params(self) -> Any:
        params_cls = self._sdk.get("BalanceAllowanceParams")
        if params_cls is None:
            try:
                params_cls = getattr(importlib.import_module("py_clob_client.clob_types"), "BalanceAllowanceParams")
            except (ImportError, AttributeError):
                params_cls = None
        if params_cls is None:
            return {"asset_type": "COLLATERAL"}
        return params_cls(asset_type="COLLATERAL")

    def _fetch_json_url(self, url: str) -> Any:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; polymarket-walerike/0.1)",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - endpoint configurable for tests
                return self._json_loads(response.read())
        except Exception as exc:  # noqa: BLE001 - expose public data read failures clearly
            raise RuntimeError(f"Polymarket Gamma request failed for {url}: {exc}") from exc

    def _fetch_text_url(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 (compatible; polymarket-walerike/0.1)",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - public Polymarket pages
            return response.read().decode("utf-8", errors="replace")

    def _post_json_url(self, url: str, payload: Any) -> Any:
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; polymarket-walerike/0.1)",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - endpoint configurable for tests
                return self._json_loads(response.read())
        except Exception as exc:  # noqa: BLE001 - expose public data read failures clearly
            raise RuntimeError(f"Polymarket CLOB request failed for {url}: {exc}") from exc

    def _start_ws(self, payload: dict[str, Any], channel: str) -> None:
        task = asyncio.create_task(self._ws_loop(payload, channel))
        self._ws_tasks.append(task)

    async def _ws_loop(self, payload: dict[str, Any], channel: str) -> None:
        if websockets is None:
            logger.warning("websockets package not installed; websocket subscription disabled")
            return
        backoff = 1.0
        while not self._closed:
            try:
                async with websockets.connect(self._ws_url(channel), ping_interval=None) as ws:
                    await ws.send(self._json_dumps(payload))
                    logger.info("Subscribed to Polymarket {} websocket", channel)
                    backoff = 1.0
                    heartbeat = asyncio.create_task(self._heartbeat(ws))
                    try:
                        async for message in ws:
                            await self._handle_ws_message(channel, message)
                    finally:
                        heartbeat.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await heartbeat
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep websocket loop alive
                logger.warning("Polymarket websocket error on {}: {}", channel, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _heartbeat(self, ws: Any) -> None:
        while not self._closed:
            await asyncio.sleep(10)
            with contextlib.suppress(Exception):
                await ws.send("PING")

    async def _handle_ws_message(self, channel: str, message: Any) -> None:
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            if not message or message in ("PING", "PONG", "ping", "pong"):
                return
            payload = self._json_loads(message)
        except (ValueError, json.JSONDecodeError):
            return
        if payload is None:
            return
        if isinstance(payload, list):
            payload = {"data": payload}
        if not isinstance(payload, dict):
            return
        event = WebSocketEvent(channel=channel, event_type=str(payload.get("event_type", "message")), payload=payload)
        if self._event_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._event_queue.get_nowait()
        self._event_queue.put_nowait(event)
        for callback in self._callbacks:
            try:
                result = callback(event)
                if result is not None:
                    await result
            except Exception as exc:  # noqa: BLE001 - callbacks must not kill socket
                logger.warning("Polymarket websocket callback failed: {}", exc)

    @staticmethod
    async def _call_sync(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    @staticmethod
    def _order_response_from_raw(request: OrderRequest, raw: Any) -> OrderResponse:
        data = raw if isinstance(raw, dict) else {"raw": raw}
        return OrderResponse(
            order_id=str(data.get("orderID") or data.get("order_id") or data.get("id", "")),
            status=str(data.get("status", "SUBMITTED")),
            market=request.market,
            asset_id=request.asset_id,
            side=request.side,
            price=request.price,
            size=request.size,
            raw=data,
        )

    @staticmethod
    def _json_dumps(value: dict[str, Any]) -> str:
        return json.dumps(value)

    @staticmethod
    def _json_loads(value: Any) -> Any:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(value)
        return parsed

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _usdc_amount(cls, value: Any) -> float | None:
        amount = cls._float_or_none(value)
        if amount is None:
            return None
        return amount / 1_000_000 if amount > 10_000 else amount

    @classmethod
    def _normalize_account_trade(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or item.get("trade_id") or item.get("transactionHash") or ""),
            "market": str(item.get("market") or item.get("conditionId") or item.get("condition_id") or ""),
            "side": str(item.get("side") or item.get("takerSide") or ""),
            "size": cls._float_or_none(item.get("size") or item.get("amount")),
            "price": cls._float_or_none(item.get("price")),
            "fee": cls._float_or_none(item.get("fee") or item.get("feeAmount")),
            "timestamp": cls._float_or_none(item.get("timestamp") or item.get("createdAt")),
            "raw": item,
        }


async def paper_smoke() -> None:
    client = PolymarketClient(paper_mode=True)
    await client.connect()
    expiration = int(time.time()) + 3600
    order = await client.place_order(
        OrderRequest(
            market="paper-market",
            asset_id="paper-asset",
            side=OrderSide.BUY,
            price=0.5,
            size=1,
            expiration=expiration,
        )
    )
    await client.cancel_order(order.order_id)
    await client.close()
