"""Template step is disabled (prefer miss → series/Decisions)."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.knowability_templates import (
    ALLOWLIST_REGIMES,
    CRYPTO_UP_OR_DOWN_WINDOW,
    EARNINGS_BEAT_EPS,
    SPORTS_MATCHUP_WINNER,
    TEMPLATE_ALLOWLIST_VERSION,
    TEMPLATE_MATCHING_ENABLED,
    match_template,
)


def test_allowlist_version_and_reserved_ids() -> None:
    assert TEMPLATE_ALLOWLIST_VERSION == "knowability.templates.v1"
    assert TEMPLATE_MATCHING_ENABLED is False
    assert set(ALLOWLIST_REGIMES) == {
        CRYPTO_UP_OR_DOWN_WINDOW,
        SPORTS_MATCHUP_WINNER,
        EARNINGS_BEAT_EPS,
    }


def test_template_matching_disabled_even_for_seed_phrases() -> None:
    samples = (
        "Will Bitcoin be up or down on 2026-11-24?",
        "Lakers vs Celtics — who will win?",
        "Will AAPL beat EPS estimates for Q1 2026?",
        "Who will win the Oscar for Best Picture?",
    )
    for question in samples:
        assert match_template(question) is None
        assert match_template(question, category="crypto") is None
        assert match_template(question, category="sports") is None
