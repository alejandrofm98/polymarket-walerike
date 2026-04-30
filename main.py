"""Application entry point for local dashboard server."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from bot.config.logging import configure_logging
from bot.config.runtime_config import RuntimeConfigStore
from bot.config.runtime_config import validate_runtime_config
from bot.config.settings import Settings
from bot.core.binance_feed import BinanceTickerFeed
from bot.core.polymarket_client import PolymarketClient
from bot.core.polymarket_rtds_feed import PolymarketRTDSFeed
from bot.data.polymarket_data_client import PolymarketDataClient
from bot.data.trade_logger import TradeLogger
from bot.runtime.copy_engine import CopyTradingEngine
from bot.web.api_routes import BotRuntimeState
from bot.web.server import create_app
from bot.web.websocket_server import WebSocketBroadcaster


def create_price_feed(settings: Settings) -> Any:
    """Create price feed based on PRICE_FEED_SOURCE config."""
    source = getattr(settings, "price_feed_source", "binance")
    
    if source == "polymarket_rtds_chainlink":
        return PolymarketRTDSFeed(assets=list(settings.market_assets), topic="crypto_prices_chainlink")
    elif source == "polymarket_rtds":
        return PolymarketRTDSFeed(assets=list(settings.market_assets), topic="crypto_prices")
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
    validate_runtime_config(runtime_config)
    requested_paper_mode = bool(runtime_config.paper_mode)
    can_live_trade = not requested_paper_mode and bool(settings.live_trading)
    effective_paper_mode = requested_paper_mode or not can_live_trade
    settings.paper_mode = effective_paper_mode
    client = PolymarketClient(settings=settings, paper_mode=effective_paper_mode)
    trade_logger = TradeLogger(settings.database_path)
    broadcaster = WebSocketBroadcaster()
    price_feed = create_price_feed(settings)
    data_client = PolymarketDataClient(
        settings.polymarket_data_api_url,
        gamma_url=settings.polymarket_gamma_api_url,
    )
    client.data_client = data_client
    engine = CopyTradingEngine(
        client=client,
        data_client=data_client,
        broadcaster=broadcaster,
        runtime_config_store=runtime_config_store,
        trade_logger=trade_logger,
        paper=effective_paper_mode,
    )
    engine._funder_address = settings.funder or settings.external_wallet_address
    return {
        "polymarket_client": client,
        "trade_logger": trade_logger,
        "runtime_state": BotRuntimeState(paper_mode=effective_paper_mode),
        "runtime_config_store": runtime_config_store,
        "runtime_config": runtime_config,
        "broadcaster": broadcaster,
        "price_feed": price_feed,
        "data_client": data_client,
        "bot_engine": engine,
    }


def create_application(settings: Settings | None = None) -> Any:
    logger = configure_logging()
    settings = settings or Settings.from_env()
    services = build_services(settings)
    feed_type = getattr(settings, "price_feed_source", "binance")
    if isinstance(logger, logging.Logger):
        logger.info("startup paper_mode=%s live_trading=%s price_feed=%s", settings.paper_mode, settings.live_trading, feed_type)
    else:
        logger.info("startup paper_mode={} live_trading={} price_feed={}", settings.paper_mode, settings.live_trading, feed_type)
    return create_app(settings, services)


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

    app = create_application(settings)
    if args.smoke:
        logger = logging.getLogger("walerike")
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


app = None if __name__ == "__main__" else create_application()


if __name__ == "__main__":
    main()
