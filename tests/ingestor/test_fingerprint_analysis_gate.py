"""Primary-analysis readiness for fingerprints."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.fingerprint import fingerprint_analysis_ready


def test_weak_not_core_until_sensitivity_labeled() -> None:
    assert (
        fingerprint_analysis_ready(
            fingerprint_version="b.v1",
            locked_version="b.v1",
            strength="weak",
            sensitivity_only=False,
        )
        is False
    )
    assert (
        fingerprint_analysis_ready(
            fingerprint_version="b.v1",
            locked_version="b.v1",
            strength="weak",
            sensitivity_only=True,
        )
        is True
    )


def test_strong_ready_when_version_matches() -> None:
    assert (
        fingerprint_analysis_ready(
            fingerprint_version="b.v1",
            locked_version="b.v1",
            strength="strong",
        )
        is True
    )
