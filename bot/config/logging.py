"""Logging setup with loguru when available and stdlib fallback otherwise."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


def configure_logging(log_file: str | Path = "logs/bot.log") -> Any:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from loguru import logger
    except ImportError:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(path, encoding="utf-8")],
            force=True,
        )
        return logging.getLogger("walerike")

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(path, level="INFO", rotation="5 MB", retention=5)
    return logger
