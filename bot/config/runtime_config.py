"""Editable runtime configuration persisted as local JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG_PATH = Path("data/runtime_config.json")
DEFAULT_ASSETS = ("BTC", "ETH", "SOL")
DEFAULT_TIMEFRAMES = ("5m", "15m", "1h")


@dataclass(slots=True)
class RuntimeConfig:
    capital_per_trade: float = 10.0
    min_margin_for_arbitrage: float = 0.02
    entry_threshold: float = 0.499
    max_sum_avg: float = 0.98
    max_buys_per_side: int = 4
    shares_per_order: float = 5.0
    reversal_delta: float = 0.02
    depth_buy_discount_percent: float = 0.05
    second_side_buffer: float = 0.01
    second_side_time_threshold_ms: float = 200.0
    dynamic_threshold_boost: float = 0.04
    enabled_markets: dict[str, list[str]] | list[str] | None = None
    email_loss_alert_pct: float = 0.0
    solo_log: bool = False
    paper_mode: bool = True

    def __post_init__(self) -> None:
        if self.enabled_markets is None:
            self.enabled_markets = {asset: list(DEFAULT_TIMEFRAMES) for asset in DEFAULT_ASSETS}


class RuntimeConfigStore:
    def __init__(self, path: str | Path = DEFAULT_RUNTIME_CONFIG_PATH) -> None:
        self.path = Path(path)

    def load(self) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("runtime config must be a JSON object")
        allowed = {field.name for field in fields(RuntimeConfig)}
        return RuntimeConfig(**{key: value for key, value in data.items() if key in allowed})

    def save(self, config: RuntimeConfig) -> RuntimeConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return config

    def update(self, payload: dict[str, Any]) -> RuntimeConfig:
        config = self.load()
        for key, value in payload.items():
            if not hasattr(config, key):
                continue
            setattr(config, key, value)
        validate_runtime_config(config)
        return self.save(config)


def validate_runtime_config(config: RuntimeConfig) -> None:
    config.capital_per_trade = _float_range("capital_per_trade", config.capital_per_trade, minimum=1.0, maximum=1_000_000.0)
    config.min_margin_for_arbitrage = _float_range("min_margin_for_arbitrage", config.min_margin_for_arbitrage, minimum=0.0, maximum=1.0)
    config.entry_threshold = _float_range("entry_threshold", config.entry_threshold, minimum=0.01, maximum=0.99)
    config.max_sum_avg = _float_range("max_sum_avg", config.max_sum_avg, minimum=0.01, maximum=1.0)
    config.max_buys_per_side = int(_float_range("max_buys_per_side", config.max_buys_per_side, minimum=1.0, maximum=100.0))
    config.shares_per_order = _float_range("shares_per_order", config.shares_per_order, minimum=1.0, maximum=1_000_000.0)
    config.reversal_delta = _float_range("reversal_delta", config.reversal_delta, minimum=0.0, maximum=1.0)
    config.depth_buy_discount_percent = _float_range("depth_buy_discount_percent", config.depth_buy_discount_percent, minimum=0.0, maximum=1.0)
    config.second_side_buffer = _float_range("second_side_buffer", config.second_side_buffer, minimum=0.0, maximum=1.0)
    config.second_side_time_threshold_ms = _float_range("second_side_time_threshold_ms", config.second_side_time_threshold_ms, minimum=0.0, maximum=60_000.0)
    config.dynamic_threshold_boost = _float_range("dynamic_threshold_boost", config.dynamic_threshold_boost, minimum=0.0, maximum=1.0)
    config.email_loss_alert_pct = _float_range("email_loss_alert_pct", config.email_loss_alert_pct, minimum=0.0, maximum=100.0)
    config.solo_log = bool(config.solo_log)
    config.paper_mode = bool(config.paper_mode)
    config.enabled_markets = normalize_enabled_markets(config.enabled_markets)


def normalize_enabled_markets(value: Any) -> dict[str, list[str]]:
    if isinstance(value, list):
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("enabled_markets list must contain non-empty strings")
        return {_asset(item): list(DEFAULT_TIMEFRAMES) for item in value}
    if not isinstance(value, dict):
        raise ValueError("enabled_markets must be an asset-to-timeframes object")
    normalized: dict[str, list[str]] = {}
    for raw_asset, raw_timeframes in value.items():
        asset = _asset(raw_asset)
        if not isinstance(raw_timeframes, list) or not all(isinstance(item, str) and item.strip() for item in raw_timeframes):
            raise ValueError("enabled_markets values must be lists of timeframes")
        timeframes = [_timeframe(item) for item in raw_timeframes]
        normalized[asset] = list(dict.fromkeys(timeframes))
    return normalized


def enabled_market_pairs(value: dict[str, list[str]] | list[str] | None) -> list[tuple[str, str]]:
    normalized = normalize_enabled_markets(value)
    return [(asset, timeframe) for asset, timeframes in normalized.items() for timeframe in timeframes]


def _asset(value: Any) -> str:
    asset = str(value).strip().upper()
    if asset not in DEFAULT_ASSETS:
        raise ValueError(f"asset must be one of {', '.join(DEFAULT_ASSETS)}")
    return asset


def _timeframe(value: Any) -> str:
    timeframe = str(value).strip().lower()
    if timeframe not in DEFAULT_TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {', '.join(DEFAULT_TIMEFRAMES)}")
    return timeframe


def _slug(value: str) -> str:
    return value.strip().rstrip("/").split("/")[-1]


def _float_range(name: str, value: Any, *, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number
