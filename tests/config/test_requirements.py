from pathlib import Path

from bot.config.settings import Settings


def test_requirements_include_live_clob_sdk() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    active_lines = [line.strip() for line in requirements.splitlines() if line.strip() and not line.lstrip().startswith("#")]

    assert any(line.startswith("py-clob-client-v2>=") for line in active_lines)


def test_copy_engine_auto_starts_by_default() -> None:
    assert Settings().auto_start_bot is True
