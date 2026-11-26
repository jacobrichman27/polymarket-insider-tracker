"""Binary regimes remain admitted; windowed/onset removed under knowability.v3."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.knowability import VALID_REGIMES


def test_admitted_regimes_are_binary_plus_unknown() -> None:
    assert VALID_REGIMES == frozenset(
        {"no_private_edge", "private_edge_possible", "unknown"}
    )


def test_legacy_windowed_name_is_not_valid() -> None:
    assert "windowed" not in VALID_REGIMES
    assert "never_early" not in VALID_REGIMES
    assert "always_latent" not in VALID_REGIMES
