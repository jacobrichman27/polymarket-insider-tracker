"""Signed-flow disagreement classification."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.signed_flow_kpi import (
    DisagreementClass,
    classify_disagreement,
)


def test_agree_and_unavailable() -> None:
    assert (
        classify_disagreement(api_side="BUY", onchain_direction="BUY", receipt_status="ok")
        == DisagreementClass.AGREE
    )
    assert (
        classify_disagreement(api_side="BUY", onchain_direction=None, receipt_status="ok")
        == DisagreementClass.UNAVAILABLE
    )


def test_complement_and_mismatch() -> None:
    assert (
        classify_disagreement(api_side="BUY", onchain_direction="SELL", receipt_status="ok")
        == DisagreementClass.COMPLEMENT
    )
