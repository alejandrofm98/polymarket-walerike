"""FastAPI API routes for dashboard state and bot controls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bot.config.runtime_config import RuntimeConfigStore, validate_runtime_config

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
        return {
            "available": True,
            "feed_type": feed_type,
            "assets": assets,
            "latest": {k: {"price": v.price, "timestamp": v.timestamp} for k, v in latest.items()} if latest else {},
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
                    market.current_price_source = "polymarket_rtds_chainlink"
                elif "Binance" in price_source:
                    market.current_price_source = "binance_live"
                else:
                    market.current_price_source = price_source.lower()
        elif hasattr(price_feed, "assets"):
            if hasattr(price_feed, "fetch_latest_http") and price_feed.latest:
                pass_synced_price = price_feed.latest.get(asset.upper())
                if pass_synced_price and hasattr(pass_synced_price, "price"):
                    market.current_price = float(pass_synced_price.price)
                    market.current_price_source = "polymarket_rtds_chainlink"
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

    @router.get("/status")
    async def status() -> dict[str, Any]:
        pf_status = get_price_feed_status()
        base = {"runtime": engine.status(), "paper_mode": engine.paper, "live_trading": settings.live_trading}
        if engine is None or not hasattr(engine, "status"):
            base = {"runtime": asdict(runtime), "paper_mode": settings.paper_mode, "live_trading": settings.live_trading}
        base["price_feed"] = pf_status
        return base

    @router.get("/config")
    async def get_config() -> dict[str, Any]:
        config = config_store.load()
        validate_runtime_config(config)
        return asdict(config)

    @router.put("/config")
    async def update_config(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            config = config_store.update(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if engine is not None and hasattr(engine, "_apply_runtime_config"):
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

    @router.post("/bot/{action}")
    async def control_bot(action: str) -> dict[str, Any]:
        if engine is not None:
            if action == "start":
                state = await engine.start()
            elif action == "pause":
                state = await engine.pause()
            elif action == "stop":
                state = await engine.stop()
            elif action == "solo-log":
                state = await engine.set_solo_log(True)
            else:
                return {"ok": False, "error": f"unknown action: {action}", "runtime": engine.status()}
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
