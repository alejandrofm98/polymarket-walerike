"""Application entry point for local dashboard server."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from bot.config.logging import configure_logging
from bot.config.runtime_config import RuntimeConfigStore
from bot.config.settings import Settings
from bot.core.binance_feed import BinanceTickerFeed
from bot.core.chainlink_oracle import ChainlinkOracle
from bot.core.polymarket_client import PolymarketClient
from bot.core.polymarket_rtds_feed import PolymarketRTDSFeed
from bot.data.market_scanner import MarketScanner
from bot.data.trade_logger import TradeLogger
from bot.runtime import BotEngine
from bot.web.api_routes import BotRuntimeState
from bot.web.server import create_app
from bot.web.websocket_server import WebSocketBroadcaster


def create_price_feed(settings: Settings) -> Any:
    """Create price feed based on PRICE_FEED_SOURCE config."""
    source = getattr(settings, "price_feed_source", "binance")
    
    if source == "polymarket_rtds_chainlink":
        return PolymarketRTDSFeed(assets=list(settings.market_assets))
    elif source == "binance":
        return BinanceTickerFeed()
    else:
        return BinanceTickerFeed()


def create_target_price_feed(price_feed: Any) -> Any:
    """Create a historical lookup feed for window-start targets.
    
    Returns None when using PolymarketRTDSFeed since Binance historical
    prices are not a good proxy for Polymarket's window-start price.
    """
    if isinstance(price_feed, BinanceTickerFeed):
        return price_feed
    return None


def build_services(settings: Settings) -> dict[str, Any]:
    runtime_config_store = RuntimeConfigStore()
    runtime_config = runtime_config_store.load()
    client = PolymarketClient(settings=settings, paper_mode=settings.paper_mode)
    trade_logger = TradeLogger(settings.database_path)
    broadcaster = WebSocketBroadcaster()
    price_feed = create_price_feed(settings)
    target_price_feed = create_target_price_feed(price_feed)
    oracle = ChainlinkOracle(settings=settings)
    scanner = MarketScanner(client, settings.market_assets, settings.market_timeframes, runtime_config.enabled_markets)
    engine = BotEngine(
        settings=settings,
        client=client,
        trade_logger=trade_logger,
        broadcaster=broadcaster,
        runtime_config_store=runtime_config_store,
        scanner=scanner,
        price_feed=price_feed,
        oracle=oracle,
        paper=settings.paper_mode,
        scan_interval=settings.scan_interval,
        realtime_interval=settings.realtime_interval,
    )
    return {
        "polymarket_client": client,
        "trade_logger": trade_logger,
        "runtime_state": BotRuntimeState(paper_mode=settings.paper_mode),
        "runtime_config_store": runtime_config_store,
        "runtime_config": runtime_config,
        "broadcaster": broadcaster,
        "price_feed": price_feed,
        "target_price_feed": target_price_feed,
        "oracle": oracle,
        "market_scanner": scanner,
        "bot_engine": engine,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Polymarket Walerike dashboard")
    parser.add_argument("--paper", action="store_true", help="force paper mode")
    parser.add_argument("--live", action="store_true", help="enable live mode only with POLYMARKET_LIVE_TRADING=1")
    parser.add_argument("--host", default=None, help="web bind host")
    parser.add_argument("--port", type=int, default=None, help="web bind port")
    parser.add_argument("--smoke", action="store_true", help="build services and exit without starting server")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = configure_logging()
    settings = Settings.from_env()
    if args.paper:
        settings.paper_mode = True
        settings.live_trading = False
    if args.live:
        settings.paper_mode = False
    if args.host:
        settings.web_host = args.host
    if args.port:
        settings.web_port = args.port

    services = build_services(settings)
    feed_type = getattr(settings, "price_feed_source", "binance")
    logger.info("startup paper_mode=%s live_trading=%s price_feed=%s", settings.paper_mode, settings.live_trading, feed_type) if isinstance(logger, logging.Logger) else logger.info(
        "startup paper_mode={} live_trading={} price_feed={}", settings.paper_mode, settings.live_trading, feed_type
    )
    app = create_app(settings, services)
    if args.smoke:
        if isinstance(logger, logging.Logger):
            logger.info("smoke startup ok")
        else:
            logger.info("smoke startup ok")
        return
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise RuntimeError("uvicorn required to run web server") from exc
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


if __name__ == "__main__":
    main()
