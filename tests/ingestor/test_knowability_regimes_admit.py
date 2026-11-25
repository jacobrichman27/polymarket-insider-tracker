"""windowed may lack onset (provisional); never_early/unknown remain admitted."""

from __future__ import annotations

from datetime import UTC, datetime

from polymarket_insider_tracker.ingestor.archive.knowability import VALID_REGIMES, onset_for


def test_windowed_keeps_null_onset() -> None:
    assert onset_for("windowed", None) is None


def test_windowed_keeps_onset() -> None:
    onset = datetime(2026, 11, 24, tzinfo=UTC)
    assert onset_for("windowed", onset) is onset


def test_non_windowed_clears_onset() -> None:
    onset = datetime(2026, 11, 24, tzinfo=UTC)
    assert onset_for("never_early", onset) is None
    assert onset_for("unknown", onset) is None


def test_admitted_regimes_include_windowed_and_unknown() -> None:
    assert {"never_early", "always_latent", "windowed", "unknown"} <= VALID_REGIMES
