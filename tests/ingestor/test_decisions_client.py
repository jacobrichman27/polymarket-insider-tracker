"""Decisions API request/response shape (documented contract)."""

from __future__ import annotations

import json

import httpx
import pytest

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    REGIME_CHOICES,
    REGIME_QUESTION_NAME,
    HttpxDecisionsClient,
    choice_payload,
    extract_regime,
)


def test_choice_payload_matches_decisions_create_contract() -> None:
    payload = choice_payload("Will BTC be up or down on 2026-11-24?", "btc-updown")
    assert payload["model"] == "gpt-6-luna"
    assert "Market question:" in payload["input"]
    assert "btc-updown" in payload["input"]
    questions = payload["questions"]
    assert len(questions) == 1
    q0 = questions[0]
    assert q0["type"] == "choice"
    assert q0["name"] == REGIME_QUESTION_NAME
    assert [c["value"] for c in q0["choices"]] == list(REGIME_CHOICES)
    assert all("description" in c for c in q0["choices"])
    assert "regime" in q0["instructions"].lower() or "insider" in q0["instructions"].lower()


def test_extract_regime_from_documented_choice_answer() -> None:
    body = {
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": REGIME_QUESTION_NAME,
                "choice": "never_early",
                "confidence": 0.9,
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
    }
    assert extract_regime(body) == "never_early"


def test_extract_regime_refusal_is_unknown() -> None:
    body = {
        "answers": [{"type": "refusal", "name": REGIME_QUESTION_NAME}],
    }
    assert extract_regime(body) == "unknown"


@pytest.mark.asyncio
async def test_client_posts_and_parses_choice_answer() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "answers": [
                    {
                        "type": "choice",
                        "name": REGIME_QUESTION_NAME,
                        "choice": "always_latent",
                    }
                ],
            },
        )

    client = HttpxDecisionsClient(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await client.classify_regime(
        question="Lakers vs Celtics — who will win?",
        series_slug="nba",
        market_json=None,
    )
    assert result.regime == "always_latent"
    assert seen["path"] == "/v1/decisions"
    body = seen["body"]
    assert isinstance(body, dict)
    assert "questions" in body
