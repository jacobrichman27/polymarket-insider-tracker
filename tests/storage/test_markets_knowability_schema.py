"""Schema tests for markets / knowability / repair cutover."""

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
    KnowabilityOverrideModel,
    KnowabilitySeriesCacheModel,
    KnowabilityTemplateCacheModel,
    MarketVersionModel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ENV = "DATABASE_URL"
MARKETS_KNOWABILITY_TABLES = (
    "markets",
    "knowability_series_cache",
    "knowability_template_cache",
    "knowability_overrides",
)


def test_markets_knowability_models_expose_required_columns() -> None:
    market_cols = {col.name for col in MarketVersionModel.__table__.columns}
    assert {"condition_id", "known_at", "token_outcomes", "knowable_from"} <= market_cols
    state_cols = {col.name for col in ArchiveCollectorStateModel.__table__.columns}
    assert "repair_enabled_at" in state_cols
    series_cols = {col.name for col in KnowabilitySeriesCacheModel.__table__.columns}
    assert {"series_slug", "policy_version", "regime"} <= series_cols
    template_cols = {col.name for col in KnowabilityTemplateCacheModel.__table__.columns}
    assert {"template_id", "allowlist_version", "regime"} <= template_cols
    override_cols = {col.name for col in KnowabilityOverrideModel.__table__.columns}
    assert {"key_type", "key_id", "regime", "policy_version"} <= override_cols


def test_sqlite_create_all_builds_markets_knowability_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert set(MARKETS_KNOWABILITY_TABLES) <= names


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
def test_markets_knowability_migration_upgrade_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = _skip_without_services()
    admin_url = make_url(base_url).set(database="postgres")
    name = f"pit_archive_mk_{uuid.uuid4().hex}"
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
                        "WHERE schemaname = 'public' AND tablename = ANY(:names)"
                    ),
                    {"names": list(MARKETS_KNOWABILITY_TABLES)},
                )
            }
            assert set(MARKETS_KNOWABILITY_TABLES) <= tables
            cols = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'archive_collector_state'"
                    )
                )
            }
            assert "repair_enabled_at" in cols
        _run_alembic(temporary_url, "downgrade", "005_research_trade_archive_a0", monkeypatch)
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename = ANY(:names)"
                    ),
                    {"names": list(MARKETS_KNOWABILITY_TABLES)},
                )
            }
            assert tables == set()
            cols = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'archive_collector_state'"
                    )
                )
            }
            assert "repair_enabled_at" not in cols
    finally:
        _drop_database(admin_url, name)
