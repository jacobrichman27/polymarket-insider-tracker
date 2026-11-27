"""Strong vs weak fill fingerprint versioning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

__all__ = [
    "FingerprintResult",
    "WEAK_PRICE_PLACES",
    "WEAK_SIZE_PLACES",
    "assess_weak_collision",
    "compute_fill_fingerprint",
    "fingerprint_analysis_ready",
]

# Fixed-scale weak material — do not change without bumping ARCHIVE_FINGERPRINT_VERSION.
WEAK_PRICE_PLACES = 8
WEAK_SIZE_PLACES = 8


@dataclass(frozen=True)
class FingerprintResult:
    fill_fingerprint: str
    fingerprint_version: str
    strength: str
    material: str


def _canon_decimal(value: Decimal | float | str, *, places: int) -> str:
    try:
        quantized = Decimal(str(value)).quantize(Decimal(10) ** -places)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("fingerprint decimal is not finite") from exc
    return format(quantized, f".{places}f")


def _weak_material(
    transaction_hash: str,
    token_id: str,
    price: Decimal | float | str | None,
    size_shares: Decimal | float | str | None,
) -> str:
    if price is None or size_shares is None:
        raise ValueError("weak fingerprint requires price and size_shares")
    price_key = _canon_decimal(price, places=WEAK_PRICE_PLACES)
    size_key = _canon_decimal(size_shares, places=WEAK_SIZE_PLACES)
    return f"{transaction_hash}|{token_id}|{price_key}|{size_key}"


def compute_fill_fingerprint(
    *,
    transaction_hash: str,
    token_id: str,
    fingerprint_version: str,
    log_index: int | None = None,
    price: Decimal | float | str | None = None,
    size_shares: Decimal | float | str | None = None,
) -> FingerprintResult:
    """Match grain: strong with log_index; weak with canonical price/size.

    Never includes side or proxy_wallet — opposite legs of one slice must collide.
    """
    tx = transaction_hash.lower()
    token = token_id.strip()
    if log_index is not None:
        material = f"{tx}|{token}|{log_index}"
        strength = "strong"
    else:
        material = _weak_material(tx, token, price, size_shares)
        strength = "weak"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return FingerprintResult(
        fill_fingerprint=digest,
        fingerprint_version=fingerprint_version,
        strength=strength,
        material=material,
    )


def assess_weak_collision(*, observation_count: int, same_side_max: int) -> bool:
    """True when a weak key looks over-merged (not a clean opposite-leg pair).

    A healthy pair is two observations with opposite sides (same_side_max == 1).
    More than two rows, or two+ rows on one side, is a collision suspect.
    """
    if observation_count > 2:
        return True
    return same_side_max > 1


def fingerprint_analysis_ready(
    *,
    fingerprint_version: str | None,
    locked_version: str,
    strength: str | None,
    sensitivity_only: bool = False,
) -> bool:
    if fingerprint_version != locked_version:
        return False
    if strength == "strong":
        return True
    return sensitivity_only and strength == "weak"
