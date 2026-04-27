"""FastAPI API routes for dashboard state and bot controls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import suppress
import asyncio
import importlib.util
import logging
import time
from pathlib import Path
from typing import Any

from bot.config.runtime_config import RuntimeConfigStore, validate_runtime_config

logger = logging.getLogger("walerike.api")

try:
    from fastapi import APIRouter, HTTPException, Response
except ImportError:  # pragma: no cover - optional until web server use
    APIRouter = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]


@dataclass(slots=True)
class BotRuntimeState:
    running: bool = False
    paused: bool = False
    paper_mode: bool = True
    status: str = "stopped"


def create_api_router(settings: Any, services: dict[str, Any]) -> Any:
    if APIRouter is None or Response is None:
        raise RuntimeError("FastAPI required for API routes")
    router = APIRouter(prefix="/api")
    runtime: BotRuntimeState = services.setdefault("runtime_state", BotRuntimeState(paper_mode=settings.paper_mode))
    engine = services.get("bot_engine")
    trade_logger = services.get("trade_logger")
    config_store = services.setdefault("runtime_config_store", RuntimeConfigStore())

    def scanner_service() -> Any:
        scanner = services.get("market_scanner")
        if scanner is not None:
            return scanner
        if engine is not None:
            return getattr(engine, "scanner", None)
        return None

    def price_feed_service() -> Any:
        return services.get("price_feed")

    def get_price_feed_status() -> dict[str, Any]:
        pf = services.get("price_feed")
        if pf is None:
            return {"available": False}
        feed_type = type(pf).__name__
        latest = getattr(pf, "latest", {})
        assets = getattr(pf, "assets", [])
        now = time.time()
        last_update_at = getattr(pf, "_last_update_at", {})
        last_live_update = getattr(pf, "_last_live_update", {})
        snapshot_seen = getattr(pf, "_snapshot_seen", {})
        return {
            "available": True,
            "feed_type": feed_type,
            "assets": assets,
            "topic": getattr(pf, "topic", None),
            "closed": bool(getattr(pf, "_closed", False)),
            "latest": {k: {"price": getattr(v, "price", None), "timestamp": getattr(v, "timestamp", None)} for k, v in latest.items()} if isinstance(latest, dict) else {},
            "snapshot_seen": dict(snapshot_seen) if isinstance(snapshot_seen, dict) else {},
            "last_update_age_seconds": {
                str(asset): round(now - float(updated_at), 3) if updated_at else None
                for asset, updated_at in last_update_at.items()
            } if isinstance(last_update_at, dict) else {},
            "last_live_update_age_seconds": {
                str(asset): round(now - float(updated_at), 3) if updated_at else None
                for asset, updated_at in last_live_update.items()
            } if isinstance(last_live_update, dict) else {},
        }

    def runtime_mode_status(runtime_payload: dict[str, Any]) -> dict[str, Any]:
        requested_paper_mode = runtime_payload.get("requested_paper_mode")
        if requested_paper_mode is None:
            with suppress(Exception):
                requested_paper_mode = bool(config_store.load().paper_mode)
        if requested_paper_mode is None:
            requested_paper_mode = bool(runtime_payload.get("paper_mode", settings.paper_mode))
        paper_mode = bool(runtime_payload.get("paper_mode", settings.paper_mode))
        live_trading = bool(getattr(settings, "live_trading", False))
        try:
            live_sdk_available = importlib.util.find_spec("py_clob_client.client") is not None
        except ModuleNotFoundError:
            live_sdk_available = False
        live_block_reason = None
        if requested_paper_mode is False and not live_trading:
            live_block_reason = "POLYMARKET_LIVE_TRADING=true required for live mode"
        elif requested_paper_mode is False and not live_sdk_available:
            live_block_reason = "Live mode requires optional package py-clob-client"
        live_blocked = live_block_reason is not None
        can_live_trade = not paper_mode and live_trading
        return {
            "requested_paper_mode": requested_paper_mode,
            "paper_mode": paper_mode,
            "live_trading": live_trading,
            "live_sdk_available": live_sdk_available,
            "can_live_trade": can_live_trade,
            "live_blocked": live_blocked,
            "live_block_reason": live_block_reason,
            "mode_label": "Live blocked" if live_blocked else "Paper" if paper_mode else "Live",
        }

    def _enrich_market_with_price(market: Any, price_feed: Any, scanner: Any) -> None:
        if price_feed is None or scanner is None:
            return
        asset = getattr(market, "asset", None)
        if not asset:
            return
        price_source = type(price_feed).__name__ if price_feed is not None else "Unknown"
        
        has_latest = hasattr(price_feed, "latest") and isinstance(price_feed.latest, dict) and price_feed.latest
        if has_latest:
            tick = price_feed.latest.get(asset.upper()) or price_feed.latest.get(asset.lower())
            if tick is not None and hasattr(tick, "price"):
                market.current_price = float(tick.price)
                if "PolymarketRTDS" in price_source:
                    topic = getattr(price_feed, "topic", "")
                    market.current_price_source = "polymarket_rtds_chainlink" if topic == "crypto_prices_chainlink" else "polymarket_rtds"
                elif "Binance" in price_source:
                    market.current_price_source = "binance_live"
                else:
                    market.current_price_source = price_source.lower()
        elif hasattr(price_feed, "assets"):
            if hasattr(price_feed, "fetch_latest_http") and price_feed.latest:
                pass_synced_price = price_feed.latest.get(asset.upper())
                if pass_synced_price and hasattr(pass_synced_price, "price"):
                    market.current_price = float(pass_synced_price.price)
                    topic = getattr(price_feed, "topic", "")
                    market.current_price_source = "polymarket_rtds_chainlink" if topic == "crypto_prices_chainlink" else "polymarket_rtds"
                else:
                    market.current_price_source = "polymarket_rtds_pending"
            else:
                market.current_price_source = "polymarket_rtds_pending"
        
        slug_key = f"{asset}:{getattr(market, 'timeframe', '')}:{getattr(market, 'event_slug', '') or getattr(market, 'slug', '')}"
        window_ts = getattr(market, "window_start_timestamp", None)
        
        if window_ts is not None:
            target_cache_key = f"target:{slug_key}"
            if hasattr(scanner, "_target_price_for_slug"):
                stored = scanner._target_price_for_slug.get(target_cache_key)
                if stored:
                    market.price_to_beat = stored.get("price")
                    market.target_price_source = stored.get("source", "window_start")
        
        if getattr(market, "price_to_beat", None) is None:
            if window_ts is not None and window_ts > 0:
                market.target_price_source = "no_data"

    def serialize_market(candidate: Any) -> dict[str, Any]:
        if hasattr(candidate, "to_dict"):
            return candidate.to_dict()
        if hasattr(candidate, "__dataclass_fields__"):
            return asdict(candidate)
        return dict(candidate) if isinstance(candidate, dict) else {"value": candidate}

    @router.get("/health")
    async def health() -> dict[str, Any]:
        runtime_payload = engine.status() if engine is not None and hasattr(engine, "status") else asdict(runtime)
        return {"ok": True, "runtime": runtime_payload, "price_feed": get_price_feed_status()}

    @router.get("/status")
    async def status() -> dict[str, Any]:
        pf_status = get_price_feed_status()
        runtime_payload = engine.status() if engine is not None and hasattr(engine, "status") else asdict(runtime)
        mode_status = runtime_mode_status(runtime_payload)
        runtime_payload.update(mode_status)
        base = {"runtime": runtime_payload, **mode_status}
        if engine is None or not hasattr(engine, "status"):
            base = {"runtime": runtime_payload, **mode_status}
        base["price_feed"] = pf_status
        return base

    @router.get("/config")
    async def get_config() -> dict[str, Any]:
        config = config_store.load()
        validate_runtime_config(config)
        return asdict(config)

    @router.put("/config")
    async def update_config(payload: dict[str, Any]) -> dict[str, Any]:
        previous_config = config_store.load()
        try:
            config = config_store.update(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        mode_changed = "paper_mode" in payload and bool(config.paper_mode) != bool(previous_config.paper_mode)
        if mode_changed and engine is not None and hasattr(engine, "set_paper_mode"):
            try:
                await engine.set_paper_mode(bool(config.paper_mode))
            except Exception as exc:  # noqa: BLE001 - restore safe persisted mode on failed live switch
                if hasattr(config_store, "save"):
                    config_store.save(previous_config)
                elif hasattr(config_store, "update"):
                    config_store.update({"paper_mode": previous_config.paper_mode})
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            services["polymarket_client"] = getattr(engine, "client", services.get("polymarket_client"))
            services["market_scanner"] = getattr(engine, "scanner", services.get("market_scanner"))
        elif engine is not None and hasattr(engine, "_apply_runtime_config"):
            engine._apply_runtime_config()
        return asdict(config)

    @router.post("/config")
    async def post_config(payload: dict[str, Any]) -> dict[str, Any]:
        return await update_config(payload)

    @router.get("/trades")
    async def list_trades() -> list[dict[str, Any]]:
        if trade_logger is None:
            return []
        return [asdict(record) for record in trade_logger.list_trades()]

    @router.get("/positions")
    async def list_positions() -> list[dict[str, Any]]:
        if trade_logger is not None and hasattr(trade_logger, "list_positions"):
            return [asdict(record) for record in trade_logger.list_positions()]
        client = services.get("polymarket_client") or getattr(engine, "client", None)
        if client is not None and hasattr(client, "get_positions"):
            return await client.get_positions()
        return []

    @router.get("/markets")
    async def list_markets() -> list[dict[str, Any]]:
        scanner = scanner_service()
        price_feed = price_feed_service()
        if scanner is None or not hasattr(scanner, "scan"):
            return []
        try:
            markets = await scanner.scan()
        except Exception as exc:  # noqa: BLE001 - keep dashboard alive and surface read failures
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        for market in markets:
            _enrich_market_with_price(market, price_feed, scanner)
        return [serialize_market(candidate) for candidate in markets]

    @router.get("/markets/slug/{slug}")
    async def get_market_slug(slug: str) -> dict[str, Any]:
        scanner = scanner_service()
        client = services.get("polymarket_client") or getattr(engine, "client", None)
        if scanner is None or client is None:
            raise HTTPException(status_code=404, detail="market scanner unavailable")
        try:
            candidate = None
            if hasattr(client, "fetch_market_by_slug") and hasattr(scanner, "parse_market"):
                try:
                    candidate = scanner.parse_market(await client.fetch_market_by_slug(slug))
                except Exception:
                    candidate = None
            if candidate is None and hasattr(client, "fetch_event_by_slug") and hasattr(scanner, "parse_gamma_event"):
                candidate = scanner.parse_gamma_event(await client.fetch_event_by_slug(slug))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if candidate is None:
            raise HTTPException(status_code=404, detail="market not found")
        return serialize_market(candidate)

    @router.get("/trades/export")
    async def export_trades() -> Any:
        if trade_logger is None:
            return Response("", media_type="text/csv")
        path = Path(trade_logger.export_csv())
        return Response(path.read_text(encoding="utf-8"), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=trades.csv"})

    @router.get("/trades/export.csv")
    async def export_trades_csv() -> Any:
        return await export_trades()

    @router.post("/trades/clear-open-paper")
    async def clear_open_paper_trades() -> dict[str, Any]:
        if trade_logger is None or not hasattr(trade_logger, "cancel_open_paper_trades"):
            return {"ok": False, "cleared": 0, "trades": [], "error": "trade logger unavailable"}

        cancelled = trade_logger.cancel_open_paper_trades()
        positions = []
        if hasattr(trade_logger, "list_positions"):
            positions = [asdict(record) for record in trade_logger.list_positions()]
        if engine is not None and hasattr(engine, "_publish"):
            await engine._publish("positions", {"positions": positions})
            if hasattr(engine, "status"):
                await engine._publish("bot_status", engine.status())
        return {"ok": True, "cleared": len(cancelled), "trades": [asdict(record) for record in cancelled], "positions": positions}

    @router.post("/trades/clear")
    async def clear_trades() -> dict[str, Any]:
        if trade_logger is None or not hasattr(trade_logger, "clear_trades"):
            return {"ok": False, "cleared": 0, "positions": [], "error": "trade logger unavailable"}

        cleared = trade_logger.clear_trades()
        positions = []
        if hasattr(trade_logger, "list_positions"):
            positions = [asdict(record) for record in trade_logger.list_positions()]
        if engine is not None and hasattr(engine, "_publish"):
            await engine._publish("positions", {"positions": positions})
            if hasattr(engine, "status"):
                await engine._publish("bot_status", engine.status())
        return {"ok": True, "cleared": cleared, "positions": positions}

    @router.post("/bot/{action}")
    async def control_bot(action: str) -> dict[str, Any]:
        if engine is not None:
            try:
                if action == "start":
                    timeout = float(getattr(settings, "bot_start_timeout_seconds", 20.0))
                    logger.info("bot start requested timeout=%s", timeout)
                    state = await asyncio.wait_for(engine.start(), timeout=timeout)
                    logger.info("bot start completed running=%s paper_mode=%s live_trading=%s", state.get("running"), state.get("paper_mode"), state.get("live_trading"))
                elif action == "pause":
                    state = await engine.pause()
                elif action == "stop":
                    state = await engine.stop()
                elif action == "solo-log":
                    state = await engine.set_solo_log(True)
                else:
                    return {"ok": False, "error": f"unknown action: {action}", "runtime": engine.status()}
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except asyncio.TimeoutError as exc:
                logger.error("bot start timed out")
                raise HTTPException(status_code=504, detail="bot start timed out") from exc
            return {"ok": True, "runtime": state}

        if action == "start":
            runtime.running = True
            runtime.paused = False
            runtime.status = "running"
        elif action == "pause":
            runtime.paused = True
            runtime.status = "paused"
        elif action == "stop":
            runtime.running = False
            runtime.paused = False
            runtime.status = "stopped"
        elif action == "solo-log":
            runtime.status = "solo-log"
        else:
            return {"ok": False, "error": f"unknown action: {action}", "runtime": asdict(runtime)}
        return {"ok": True, "runtime": asdict(runtime)}

    return router
