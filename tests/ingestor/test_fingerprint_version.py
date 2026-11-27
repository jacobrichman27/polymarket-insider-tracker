"""Strong vs weak fingerprint versioning and weak canonicalization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from polymarket_insider_tracker.ingestor.archive.fingerprint import (
    assess_weak_collision,
    compute_fill_fingerprint,
)


def test_strong_fingerprint_uses_log_index() -> None:
    strong = compute_fill_fingerprint(
        transaction_hash="0xTx",
        token_id="tok",
        fingerprint_version="b.v2",
        log_index=3,
    )
    weak = compute_fill_fingerprint(
        transaction_hash="0xtx",
        token_id="tok",
        fingerprint_version="b.v2",
        price="0.5",
        size_shares="10",
    )
    assert strong.strength == "strong"
    assert weak.strength == "weak"
    assert strong.fill_fingerprint != weak.fill_fingerprint
    assert strong.fingerprint_version == "b.v2"
    assert strong.material == "0xtx|tok|3"


def test_weak_price_size_canonicalization_collapses_aliases() -> None:
    a = compute_fill_fingerprint(
        transaction_hash="0xABC",
        token_id=" tok ",
        fingerprint_version="b.v2",
        price="0.5",
        size_shares="10",
    )
    b = compute_fill_fingerprint(
        transaction_hash="0xabc",
        token_id="tok",
        fingerprint_version="b.v2",
        price=Decimal("0.50000000"),
        size_shares=10.0,
    )
    c = compute_fill_fingerprint(
        transaction_hash="0xabc",
        token_id="tok",
        fingerprint_version="b.v2",
        price="0.500",
        size_shares="10.000",
    )
    assert a.fill_fingerprint == b.fill_fingerprint == c.fill_fingerprint
    assert a.material == "0xabc|tok|0.50000000|10.00000000"


def test_weak_requires_price_and_size() -> None:
    with pytest.raises(ValueError, match="price and size_shares"):
        compute_fill_fingerprint(
            transaction_hash="0xtx",
            token_id="tok",
            fingerprint_version="b.v2",
            price="0.5",
        )


def test_weak_collision_suspect_rules() -> None:
    assert assess_weak_collision(observation_count=2, same_side_max=1) is False
    assert assess_weak_collision(observation_count=3, same_side_max=1) is True
    assert assess_weak_collision(observation_count=2, same_side_max=2) is True
