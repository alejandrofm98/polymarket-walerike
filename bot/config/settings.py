"""Environment-backed settings for local paper runs and live CLOB access."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


DEFAULT_POLYMARKET_HOST = "https://clob.polymarket.com"
DEFAULT_POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/"
DEFAULT_POLYMARKET_MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DEFAULT_POLYMARKET_USER_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
DEFAULT_POLYMARKET_DATA_API_URL = "https://data-api.polymarket.com"
DEFAULT_POLYMARKET_GAMMA_API_URL = "https://gamma-api.polymarket.com"
DEFAULT_CHAIN_ID = 137
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8000
DEFAULT_DATABASE_PATH = "data/trades.db"
DEFAULT_FRONTEND_DIR = "frontend"
DEFAULT_SCAN_INTERVAL = 10.0
DEFAULT_REALTIME_INTERVAL = 0.2
DEFAULT_PRICE_FEED_SOURCE = "polymarket_rtds"


@dataclass(slots=True)
class Settings:
    paper_mode: bool = True
    live_trading: bool = False
    scan_interval: float = DEFAULT_SCAN_INTERVAL
    realtime_interval: float = DEFAULT_REALTIME_INTERVAL
    polymarket_host: str = DEFAULT_POLYMARKET_HOST
    polymarket_ws_url: str = DEFAULT_POLYMARKET_WS_URL
    polymarket_market_ws_url: str = DEFAULT_POLYMARKET_MARKET_WS_URL
    polymarket_user_ws_url: str = DEFAULT_POLYMARKET_USER_WS_URL
    polymarket_data_api_url: str = DEFAULT_POLYMARKET_DATA_API_URL
    polymarket_gamma_api_url: str = DEFAULT_POLYMARKET_GAMMA_API_URL
    chain_id: int = DEFAULT_CHAIN_ID
    external_wallet_address: str | None = None
    private_key: str | None = None
    api_key: str | None = None
    funder: str | None = None
    signature_type: int | None = None
    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT
    database_path: str = DEFAULT_DATABASE_PATH
    frontend_dir: str = DEFAULT_FRONTEND_DIR
    market_assets: tuple[str, ...] = ("BTC", "ETH", "SOL")
    market_timeframes: tuple[str, ...] = ("5m", "15m", "1h")
    require_live_confirmation: bool = True
    price_feed_source: str = DEFAULT_PRICE_FEED_SOURCE

    @classmethod
    def from_env(cls, load_dotenv: bool = True) -> "Settings":
        if load_dotenv:
            _load_dotenv()

        signature_type = os.getenv("POLYMARKET_SIGNATURE_TYPE")
        return cls(
            paper_mode=_env_bool("PAPER_MODE", True),
            live_trading=_env_bool("POLYMARKET_LIVE_TRADING", False),
            scan_interval=float(os.getenv("SCAN_INTERVAL", str(DEFAULT_SCAN_INTERVAL))),
            realtime_interval=float(os.getenv("REALTIME_INTERVAL", str(DEFAULT_REALTIME_INTERVAL))),
            polymarket_host=os.getenv("POLYMARKET_HOST", DEFAULT_POLYMARKET_HOST),
            polymarket_ws_url=os.getenv("POLYMARKET_WS_URL", DEFAULT_POLYMARKET_WS_URL),
            polymarket_market_ws_url=os.getenv("POLYMARKET_MARKET_WS_URL", DEFAULT_POLYMARKET_MARKET_WS_URL),
            polymarket_user_ws_url=os.getenv("POLYMARKET_USER_WS_URL", DEFAULT_POLYMARKET_USER_WS_URL),
            polymarket_data_api_url=os.getenv("POLYMARKET_DATA_API_URL", DEFAULT_POLYMARKET_DATA_API_URL),
            polymarket_gamma_api_url=os.getenv("POLYMARKET_GAMMA_API_URL", DEFAULT_POLYMARKET_GAMMA_API_URL),
            chain_id=int(os.getenv("POLYMARKET_CHAIN_ID", str(DEFAULT_CHAIN_ID))),
            external_wallet_address=os.getenv("POLYMARKET_EXTERNAL_WALLET_ADDRESS") or None,
            private_key=os.getenv("POLYMARKET_PRIVATE_KEY") or None,
            api_key=os.getenv("POLYMARKET_API_KEY") or None,
            funder=os.getenv("POLYMARKET_FUNDER") or None,
            signature_type=int(signature_type) if signature_type else None,
            web_host=os.getenv("WEB_HOST", DEFAULT_WEB_HOST),
            web_port=int(os.getenv("WEB_PORT", str(DEFAULT_WEB_PORT))),
            database_path=os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH),
            frontend_dir=os.getenv("FRONTEND_DIR", DEFAULT_FRONTEND_DIR),
            market_assets=_env_tuple("MARKET_ASSETS", ("BTC", "ETH", "SOL")),
            market_timeframes=_env_tuple("MARKET_TIMEFRAMES", ("5m", "15m", "1h")),
            require_live_confirmation=_env_bool("REQUIRE_LIVE_CONFIRMATION", True),
            price_feed_source=os.getenv("PRICE_FEED_SOURCE", DEFAULT_PRICE_FEED_SOURCE),
        )
