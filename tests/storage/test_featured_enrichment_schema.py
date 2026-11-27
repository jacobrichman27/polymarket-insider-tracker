"""Schema tests for featured enrichment archive tables."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from polymarket_insider_tracker.storage.models import (
    ArchiveWalletModel,
    Base,
    EnrichmentWorkItemModel,
    ProxyFundingModel,
    TradeFeaturesModel,
    TradeModel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENV = "DATABASE_URL"
FEATURED_ENRICHMENT_TABLES = (
    "enrichment_work_items",
    "trade_features",
    "wallets",
    "proxy_funding",
)
FEATURED_ENRICHMENT_TRADE_COLUMNS = (
    "gamma_enrichment_status",
    "funding_lookup_status",
    "wallet_hydrate_status",
    "fill_fingerprint",
    "fingerprint_version",
    "block_number",
    "log_index",
)


def test_featured_enrichment_trade_columns_present() -> None:
    trade_cols = {col.name for col in TradeModel.__table__.columns}
    assert set(FEATURED_ENRICHMENT_TRADE_COLUMNS) <= trade_cols


def test_featured_enrichment_side_table_columns_present() -> None:
    work_cols = {col.name for col in EnrichmentWorkItemModel.__table__.columns}
    feature_cols = {col.name for col in TradeFeaturesModel.__table__.columns}
    wallet_cols = {col.name for col in ArchiveWalletModel.__table__.columns}
    funding_cols = {col.name for col in ProxyFundingModel.__table__.columns}
    assert {"work_id", "trigger", "status", "enrichment_budget_version"} <= work_cols
    assert {"order_as_of_contract", "feature_version", "payload"} <= feature_cols
    assert {"proxy_wallet", "wallet_hydrate_status", "known_at"} <= wallet_cols
    assert {"proxy_wallet", "funding_lookup_status", "known_at"} <= funding_cols


def test_sqlite_create_all_builds_featured_enrichment_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert set(FEATURED_ENRICHMENT_TABLES) <= names


def _skip_without_services() -> str:
    if os.environ.get("RUN_SERVICE_TESTS") != "1":
        pytest.skip("set RUN_SERVICE_TESTS=1 with the documented local services")
    value = os.environ.get(DATABASE_ENV)
    if not value:
        pytest.skip(f"{DATABASE_ENV} is required for migration cycle")
    return value


def _create_database(admin_url: URL, name: str) -> None:
    import psycopg
    from psycopg import sql

    dsn = admin_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _drop_database(admin_url: URL, name: str) -> None:
    import psycopg
    from psycopg import sql

    dsn = admin_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def _run_alembic(
    database_url: str, direction: str, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AlembicConfig(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
    monkeypatch.setenv(DATABASE_ENV, database_url)
    if direction == "upgrade":
        command.upgrade(config, target)
        return
    command.downgrade(config, target)


@pytest.mark.integration
def test_featured_enrichment_migration_upgrade_and_downgrade_on_disposable_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = _skip_without_services()
    admin_url = make_url(base_url).set(database="postgres")
    name = f"pit_featured_enrichment_{uuid.uuid4().hex}"
    temporary_url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    _create_database(admin_url, name)
    try:
        _run_alembic(temporary_url, "upgrade", "head", monkeypatch)
        engine = create_engine(temporary_url)
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename IN "
                        "('enrichment_work_items', 'trade_features', 'wallets', 'proxy_funding')"
                    )
                )
            }
            trade_cols = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'trades'"
                    )
                )
            }
        _run_alembic(temporary_url, "downgrade", "007_knowability_question_cache", monkeypatch)
        engine_after = create_engine(temporary_url)
        with engine_after.connect() as connection:
            remaining = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename IN "
                        "('enrichment_work_items', 'trade_features', 'wallets', 'proxy_funding')"
                    )
                )
            }
            trade_cols_after = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'trades'"
                    )
                )
            }
    finally:
        _drop_database(admin_url, name)

    assert set(FEATURED_ENRICHMENT_TABLES) <= tables
    for name in FEATURED_ENRICHMENT_TRADE_COLUMNS:
        assert name in trade_cols
    assert remaining == set()
    assert "fill_fingerprint" not in trade_cols_after
