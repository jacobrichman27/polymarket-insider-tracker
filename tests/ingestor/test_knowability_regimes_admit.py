"""Binary private-edge regimes remain admitted; windowed/onset removed under knowability.v5."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.knowability import VALID_REGIMES


def test_admitted_regimes_are_binary_plus_unknown() -> None:
    assert (
        frozenset(
            {
                "no_private_edge",
                "private_edge_possible",
                "unknown",
            }
        )
        == VALID_REGIMES
    )


def test_legacy_windowed_and_split_names_are_not_valid() -> None:
    assert "windowed" not in VALID_REGIMES
    assert "never_early" not in VALID_REGIMES
    assert "always_latent" not in VALID_REGIMES
    assert "private_settlement_possible" not in VALID_REGIMES
    assert "private_factor_possible" not in VALID_REGIMES
