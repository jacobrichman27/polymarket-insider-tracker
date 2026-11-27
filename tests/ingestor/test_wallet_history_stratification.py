"""Reject silent lifetime↔archive hybrids without hydrate status."""

from __future__ import annotations

import pytest

from polymarket_insider_tracker.ingestor.archive.wallet_hydrate import require_hydrate_status


def test_require_hydrate_status_rejects_missing() -> None:
    with pytest.raises(ValueError, match="wallet_hydrate_status"):
        require_hydrate_status(None)
    assert require_hydrate_status("ok") == "ok"
