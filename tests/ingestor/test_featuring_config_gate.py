"""Featuring workers stay off unless archive and featuring are both on."""

from __future__ import annotations

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import should_run_featuring_workers


def test_featuring_workers_off_when_archive_off() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=False, ARCHIVE_FEATURING_ENABLED=True)
    assert should_run_featuring_workers(archive) is False


def test_featuring_workers_off_when_featuring_flag_off() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=False)
    assert should_run_featuring_workers(archive) is False


def test_featuring_workers_on_when_both_enabled() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    assert should_run_featuring_workers(archive) is True
