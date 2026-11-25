"""Schema tests for research trade archive tables."""

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
    ArchiveCollectorStateModel,
    Base,
    IngestGapEventModel,
    TradeModel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENV = "DATABASE_URL"
OMITTED_TRADE_COLUMNS = (
    "fill_fingerprint",
    "fingerprint_version",
    "data_complete",
    "block_number",
    "log_index",
    "onchain_direction",
    "fee_usdc",
)


def test_trade_model_has_a0_columns_without_phase_b_fields() -> None:
    columns = {col.name for col in TradeModel.__table__.columns}
    assert "observation_id" in columns
    assert "trade_ts" in columns
    assert "raw_row_json" in columns
    assert "archive_start_at" in columns
    for name in OMITTED_TRADE_COLUMNS:
        assert name not in columns


def test_gap_and_collector_models_expose_required_columns() -> None:
    gap_columns = {col.name for col in IngestGapEventModel.__table__.columns}
    state_columns = {col.name for col in ArchiveCollectorStateModel.__table__.columns}
    assert {"class", "reason", "status", "observation_id"} <= gap_columns
    assert {"source_id", "archive_start_at", "raw_retention"} <= state_columns


def test_sqlite_create_all_builds_a0_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert {"trades", "ingest_gap_events", "archive_collector_state"} <= names


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
def test_a0_migration_upgrade_and_downgrade_on_disposable_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = _skip_without_services()
    admin_url = make_url(base_url).set(database="postgres")
    name = f"pit_archive_a0_{uuid.uuid4().hex}"
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
                        "('trades', 'ingest_gap_events', 'archive_collector_state')"
                    )
                )
            }
            partitions = connection.execute(
                text("SELECT COUNT(*) FROM pg_inherits WHERE inhparent = 'trades'::regclass")
            ).scalar_one()
            trade_cols = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'trades'"
                    )
                )
            }
        _run_alembic(temporary_url, "downgrade", "004_terminal_errors", monkeypatch)
        engine_after = create_engine(temporary_url)
        with engine_after.connect() as connection:
            remaining = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename IN "
                        "('trades', 'ingest_gap_events', 'archive_collector_state')"
                    )
                )
            }
    finally:
        _drop_database(admin_url, name)

    assert tables == {"trades", "ingest_gap_events", "archive_collector_state"}
    assert partitions >= 15
    assert "raw_row_json" in trade_cols
    assert "fill_fingerprint" not in trade_cols
    assert remaining == set()
