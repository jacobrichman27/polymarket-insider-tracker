"""Public config/docs must not expose order-placement / execution settings (FR-018/021)."""

from __future__ import annotations

from pathlib import Path

from polymarket_insider_tracker.config import ArchiveSettings, Settings

FORBIDDEN_TOKENS = (
    "ORDER_PLACE",
    "PLACE_ORDER",
    "EXECUTION_ENABLED",
    "TRADING_ENABLED",
    "CANCEL_ORDER",
    "PRIVATE_KEY",
    "WALLET_MNEMONIC",
    "PLACE_BET",
    "SUBMIT_ORDER",
)


def test_settings_have_no_execution_fields() -> None:
    names = set(Settings.model_fields) | set(ArchiveSettings.model_fields)
    lowered = {name.lower() for name in names}
    assert "archive" in lowered
    assert not any("order" in name for name in lowered)
    assert not any("execution" in name for name in lowered)
    assert not any("trading" in name and name != "trades_coverage" for name in lowered)


def test_env_example_and_readme_omit_order_placement() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".env.example").read_text(encoding="utf-8")
    text += (root / "README.md").read_text(encoding="utf-8")
    upper = text.upper()
    for token in FORBIDDEN_TOKENS:
        assert token not in upper
