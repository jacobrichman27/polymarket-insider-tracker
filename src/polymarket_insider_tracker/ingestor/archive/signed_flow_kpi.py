"""Signed-flow / aggressor disagreement KPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "DEFAULT_PUBLISH_MIN_SAMPLE",
    "DisagreementClass",
    "SignedFlowKpi",
    "classify_disagreement",
    "convention_signed_side",
    "lambda_core_allowed",
]

# Provisional cohort floor aligned with deferred audit A-006 (~1k receipts).
DEFAULT_PUBLISH_MIN_SAMPLE = 1000


class DisagreementClass(StrEnum):
    AGREE = "agree"
    COMPLEMENT = "complement"
    MINT_MERGE = "mint_merge"
    TRUE_MISMATCH = "true_mismatch"
    UNAVAILABLE = "unavailable"


_CLASSIFIABLE = frozenset(
    {
        DisagreementClass.AGREE.value,
        DisagreementClass.COMPLEMENT.value,
        DisagreementClass.MINT_MERGE.value,
        DisagreementClass.TRUE_MISMATCH.value,
    }
)


@dataclass
class SignedFlowKpi:
    """Cohort counters for receipt vs API side disagreement."""

    counts: dict[str, int] = field(default_factory=dict[str, int])
    published: bool = False
    publish_min_sample: int = DEFAULT_PUBLISH_MIN_SAMPLE

    def observe(self, klass: DisagreementClass) -> None:
        self.counts[klass.value] = self.counts.get(klass.value, 0) + 1
        from polymarket_insider_tracker.ingestor.archive.enrichment_health import (
            record_disagreement,
        )

        record_disagreement(klass.value)

    def classifiable_count(self) -> int:
        return sum(self.counts.get(name, 0) for name in _CLASSIFIABLE)

    def can_publish(self) -> bool:
        return self.classifiable_count() >= self.publish_min_sample

    def publish(self) -> bool:
        """Publish only after a classifiable receipt cohort meets the sample floor."""
        if not self.can_publish():
            return False
        self.published = True
        from polymarket_insider_tracker.ingestor.archive.enrichment_health import (
            set_signed_flow_published,
        )

        set_signed_flow_published(True)
        return True


def _mismatched_class(api: str, onchain: str) -> DisagreementClass:
    if {api, onchain} == {"buy", "sell"}:
        return DisagreementClass.COMPLEMENT
    if "mint" in onchain or "merge" in onchain:
        return DisagreementClass.MINT_MERGE
    return DisagreementClass.TRUE_MISMATCH


def classify_disagreement(
    *,
    api_side: str | None,
    onchain_direction: str | None,
    receipt_status: str | None,
) -> DisagreementClass:
    if receipt_status not in {"ok", "partial"}:
        return DisagreementClass.UNAVAILABLE
    if onchain_direction is None or api_side is None:
        return DisagreementClass.UNAVAILABLE
    api = api_side.lower()
    onchain = onchain_direction.lower()
    if api == onchain:
        return DisagreementClass.AGREE
    return _mismatched_class(api, onchain)


def convention_signed_side(*, api_side: str, canonical_leg: bool) -> str | None:
    """Market-tape signed aggregates use API side on the convention canonical leg."""
    if not canonical_leg:
        return None
    return api_side


def lambda_core_allowed(*, kpi_published: bool) -> bool:
    return kpi_published
