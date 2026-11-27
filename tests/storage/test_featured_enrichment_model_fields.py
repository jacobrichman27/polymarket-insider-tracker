"""Touch featured-enrichment model columns so schema fields stay live."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from polymarket_insider_tracker.storage.models import (
    ArchiveWalletModel,
    ProxyFundingModel,
    TradeModel,
)


def test_trade_enrichment_columns_are_readable() -> None:
    trade = TradeModel(
        trade_ts=datetime.now(UTC),
        observation_id="obs",
        observed_at=datetime.now(UTC),
        archive_start_at=datetime.now(UTC),
        source_id="src",
        transaction_hash="0x",
        proxy_wallet="0xabc",
        condition_id="c",
        token_id="t",
        outcome=None,
        outcome_index=None,
        side="BUY",
        price=Decimal("1"),
        size_shares=Decimal("1"),
        notional_usdc=Decimal("1"),
        source="test",
        neg_risk=None,
        outcome_repair_status="not_needed",
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status="not_attempted",
        info_knowability_regime=None,
        knowability_label_source=None,
        raw_row_json=None,
        gamma_enrichment_status="not_attempted",
        funding_lookup_status="not_attempted",
        wallet_hydrate_status="not_attempted",
        fee_usdc=Decimal("0.01"),
        counterparty_wallets=["0xdef"],
        featuring_reason="eligible",
    )
    assert trade.gamma_enrichment_status == "not_attempted"
    assert trade.fee_usdc == Decimal("0.01")
    assert trade.counterparty_wallets == ["0xdef"]
    assert trade.featuring_reason == "eligible"


def test_wallet_and_funding_columns_are_readable() -> None:
    wallet = ArchiveWalletModel(
        proxy_wallet="0xabc",
        known_at=datetime.now(UTC),
        wallet_hydrate_status="ok",
        lifetime_is_first_trade=False,
        event_horizon_at=datetime.now(UTC),
    )
    funding = ProxyFundingModel(
        proxy_wallet="0xabc",
        known_at=datetime.now(UTC),
        funding_lookup_status="ok",
        owner_address="0xowner",
        wallet_type="proxy",
        wallet_created_at=datetime.now(UTC),
    )
    assert wallet.lifetime_is_first_trade is False
    assert wallet.event_horizon_at is not None
    assert funding.owner_address == "0xowner"
    assert funding.wallet_type == "proxy"
    assert funding.wallet_created_at is not None
