"""Gamma ``GET /markets`` documented response shapes (live-probed 2026-11-24)."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.markets import parse_token_outcomes
from polymarket_insider_tracker.ingestor.archive.workers import first_market

# Redacted fixture matching live Gamma list/condition_ids response fields.
_GAMMA_MARKET_V1 = {
    "id": "703257",
    "version": "v1",
    "conditionId": "0x747dc809fb79e1b05be09c42d6179459a58de2ef3e40f02484a4e1260f741f75",
    "question": "Will the US confirm that aliens exist before 2027?",
    "outcomes": '["Yes", "No"]',
    "clobTokenIds": '["111", "222"]',
    "positionIds": None,
}


def test_first_market_takes_array_envelope() -> None:
    market = first_market([_GAMMA_MARKET_V1])
    assert market is not None
    assert market["conditionId"] == _GAMMA_MARKET_V1["conditionId"]


def test_first_market_rejects_object_wrappers() -> None:
    assert first_market({"data": [_GAMMA_MARKET_V1]}) is None
    assert first_market({"markets": [_GAMMA_MARKET_V1]}) is None
    assert first_market(_GAMMA_MARKET_V1) is None
    assert first_market([]) is None
    assert first_market(None) is None


def test_parse_token_outcomes_from_json_encoded_clob_ids() -> None:
    mapped = parse_token_outcomes(_GAMMA_MARKET_V1)
    assert mapped == {
        "111": {"outcome": "Yes", "outcome_index": 0},
        "222": {"outcome": "No", "outcome_index": 1},
    }


def test_parse_token_outcomes_uses_position_ids_when_clob_null() -> None:
    raw = {
        "version": "v2",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": None,
        "positionIds": ["p0", "p1"],
    }
    mapped = parse_token_outcomes(raw)
    assert mapped == {
        "p0": {"outcome": "Yes", "outcome_index": 0},
        "p1": {"outcome": "No", "outcome_index": 1},
    }


def test_parse_token_outcomes_ignores_speculative_tokens_objects() -> None:
    raw = {
        "tokens": [
            {"token_id": "t0", "outcome": "Up", "outcome_index": 0},
        ],
        "outcomes": '["Up", "Down"]',
    }
    assert parse_token_outcomes(raw) == {}


def test_parse_token_outcomes_requires_json_encoded_outcomes() -> None:
    # Live Gamma encodes outcomes as a JSON string, not a native list.
    raw = {
        "outcomes": ["Yes", "No"],
        "clobTokenIds": '["111", "222"]',
    }
    assert parse_token_outcomes(raw) == {}
