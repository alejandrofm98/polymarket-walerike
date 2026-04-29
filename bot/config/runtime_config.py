from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG_PATH = Path("data/runtime_config.json")


@dataclass(slots=True)
class RuntimeConfig:
    copy_wallets: list[dict[str, Any]] | None = None
    poll_interval_seconds: float = 5.0
    paper_mode: bool = True
    solo_log: bool = False

    def __post_init__(self) -> None:
        if self.copy_wallets is None:
            self.copy_wallets = []


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
    config.poll_interval_seconds = _float_range("poll_interval_seconds", config.poll_interval_seconds, minimum=1.0, maximum=300.0)
    config.solo_log = bool(config.solo_log)
    config.paper_mode = bool(config.paper_mode)
    config.copy_wallets = normalize_copy_wallets(config.copy_wallets)


def normalize_copy_wallets(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("copy_wallets must be a list")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("copy_wallets entries must be objects")
        address = str(entry.get("address", "")).strip().lower()
        if not address:
            raise ValueError("copy wallet address is required")
        if address in seen:
            continue
        seen.add(address)
        sizing_mode = str(entry.get("sizing_mode", "leader_percent")).strip().lower()
        if sizing_mode not in ("leader_percent", "fixed"):
            raise ValueError("sizing_mode must be leader_percent or fixed")
        fixed_amount = _float_range("fixed_amount", entry.get("fixed_amount", 0), minimum=0, maximum=1_000_000)
        if sizing_mode == "fixed" and fixed_amount <= 0:
            raise ValueError("fixed_amount must be greater than 0")
        normalized.append({
            "address": address,
            "enabled": bool(entry.get("enabled", True)),
            "sizing_mode": sizing_mode,
            "fixed_amount": fixed_amount,
        })
    return normalized


def normalize_strategies(value: Any, strategy_groups: Any = None) -> dict[str, dict[str, Any]]:
    return {}


def normalize_strategy_groups(value: Any) -> dict[str, dict[str, Any]]:
    return {}


def _float_range(name: str, value: Any, *, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number