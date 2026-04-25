from __future__ import annotations

from bot.config.logging import configure_logging


def test_configure_logging_no_crash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    logger = configure_logging(tmp_path / "bot.log")

    logger.info("test log line")
    assert logger is not None
