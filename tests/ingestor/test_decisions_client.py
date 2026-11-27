"""Decisions API request/response shape (documented contract)."""

from __future__ import annotations

import json

import httpx
import pytest

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    KNOWABILITY_MODEL_VERSION,
    REGIME_CHOICES,
    REGIME_QUESTION_NAME,
    HttpxDecisionsClient,
    choice_payload,
    extract_confidence,
    extract_regime,
    no_edge_title_rule,
    title_cue_notes,
)


def test_choice_payload_matches_decisions_create_contract() -> None:
    payload = choice_payload("Will the match end in a draw?", "series-a")
    assert payload["model"] == "gpt-6-luna"
    assert "Market question:" in payload["input"]
    assert "series-a" in payload["input"]
    assert "Resolution source:" in payload["input"]
    assert "Description:" in payload["input"]
    questions = payload["questions"]
    assert len(questions) == 1
    q0 = questions[0]
    assert q0["type"] == "choice"
    assert q0["name"] == REGIME_QUESTION_NAME
    assert [c["value"] for c in q0["choices"]] == list(REGIME_CHOICES)
    assert all("description" in c for c in q0["choices"])
    instructions = q0["instructions"].lower()
    assert "watching a public process finish" in instructions
    assert "topic resemblance" in instructions
    assert "season of public contests" in instructions
    assert "single contest moneyline/spread/handicap" in instructions
    assert "held decisions, votes, awards, ballots" in instructions
    assert "probability that the chosen regime is correct" in instructions
    assert "do not choose private_edge_possible over no_private_edge" in instructions
    assert "if it is unclear, choose unknown" in instructions
    assert "private_settlement_possible" not in instructions
    assert "private_factor_possible" not in instructions
    assert set(REGIME_CHOICES) == {
        "no_private_edge",
        "private_edge_possible",
        "unknown",
    }
    private = next(c for c in q0["choices"] if c["value"] == "private_edge_possible")
    assert "privileged, non-public informational" in private["description"].lower()
    assert "intermediate information" in private["description"].lower()
    no_edge = next(c for c in q0["choices"] if c["value"] == "no_private_edge")
    assert "windowed" not in q0["instructions"].lower()
    assert "e.g." not in no_edge["description"].lower()
    assert "crypto" not in no_edge["description"].lower()
    assert "knowability.prompt.v8" in KNOWABILITY_MODEL_VERSION


def test_choice_payload_includes_clipped_market_json_evidence() -> None:
    payload = choice_payload(
        "Will the committee approve the nominee?",
        None,
        market_json={
            "resolutionSource": "https://example.com/source",
            "description": "Official ballot result is published after the vote.",
        },
    )
    assert "https://example.com/source" in payload["input"]
    assert "Official ballot result is published after the vote." in payload["input"]


def test_no_edge_title_rule_covers_easy_public_shapes() -> None:
    assert no_edge_title_rule("Will the highest temperature in Paris be 2°C?") == "temperature"
    assert no_edge_title_rule("Bitcoin Up or Down - November 27") == "up_or_down"
    assert no_edge_title_rule("Will Elon post 40 tweets?") == "public_posts"
    assert no_edge_title_rule("Team A vs Team B: O/U 45.5") == "point_total_ou"
    assert no_edge_title_rule("Exact Score: A 1 - 0 B?") == "exact_score"
    assert no_edge_title_rule("Spread: Team A (-3.5)") is None
    assert no_edge_title_rule("Will the committee approve the nominee?") is None


def test_title_cue_notes_for_scoring_path_and_in_event() -> None:
    ou = title_cue_notes("Team A vs Team B: O/U 2.5")
    assert any("over/under point-total" in note.lower() for note in ou)
    assert any("no_private_edge" in note for note in ou)
    assert not any("private_edge_possible" in note for note in ou)
    spread = title_cue_notes("Spread: Team A (-1.5)")
    assert any("spread or handicap" in note.lower() for note in spread)
    assert any("private_edge_possible" in note for note in spread)
    map_handicap = title_cue_notes("Map Handicap: 100T (-1.5) vs M80 (+1.5)")
    assert any("private_edge_possible" in note for note in map_handicap)
    signed_line = title_cue_notes("Broncos (-2.5)")
    assert any("private_edge_possible" in note for note in signed_line)
    moneyline = title_cue_notes("Nets vs. Raptors")
    assert moneyline == ()
    exact = title_cue_notes("Exact Score: Team A 1 - 0 Team B?")
    assert any("exact-scoreline" in note.lower() for note in exact)
    assert any("no_private_edge" in note for note in exact)
    in_event = title_cue_notes("Team A leading at halftime?")
    assert any("in-progress or partial state" in note.lower() for note in in_event)
    path = title_cue_notes("Asset Up or Down - November 26, 12:00PM-1:00PM ET")
    assert any("up-or-down path" in note.lower() for note in path)
    dollar = title_cue_notes("Will the price be above $64,000 on December 1?")
    assert any("dollar-denominated level" in note.lower() for note in dollar)
    temperature = title_cue_notes("Will the highest temperature in Paris be -2°C on November 28?")
    assert any("temperature" in note.lower() for note in temperature)
    assert any("no_private_edge" in note for note in temperature)
    tweets = title_cue_notes("Will someone post 100-120 tweets this week?")
    assert any(
        "tweets, truth social posts, or similar public posts" in note.lower() for note in tweets
    )
    assert any("no_private_edge" in note for note in tweets)
    truth = title_cue_notes(
        "Will Donald Trump post 80-99 Truth Social posts from November 20 to November 27?"
    )
    assert any("truth social" in note.lower() for note in truth)
    assert any("no_private_edge" in note for note in truth)
    plain = title_cue_notes("Will the committee approve the nominee?")
    assert plain == ()


def test_choice_payload_appends_title_cue_notes() -> None:
    payload = choice_payload("Side A vs Side B: O/U 223.5", None)
    instructions = payload["questions"][0]["instructions"]
    assert "Additional notes based on the market title:" in instructions
    title_notes = instructions.split("Additional notes based on the market title:", 1)[1]
    assert "no_private_edge" in title_notes
    assert "private_edge_possible" not in title_notes
    spread_payload = choice_payload("Spread: Side A (-3.5)", None)
    spread_notes = spread_payload["questions"][0]["instructions"].split(
        "Additional notes based on the market title:", 1
    )[1]
    assert "private_edge_possible" in spread_notes
    dollar_payload = choice_payload("Will the price be above $1,800 on December 2?", None)
    dollar_instructions = dollar_payload["questions"][0]["instructions"]
    assert "dollar-denominated level" in dollar_instructions.lower()
    assert "no_private_edge" in dollar_instructions


def test_extract_regime_from_documented_choice_answer() -> None:
    body = {
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": REGIME_QUESTION_NAME,
                "choice": "no_private_edge",
                "confidence": 0.9,
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
    }
    assert extract_regime(body) == "no_private_edge"
    assert extract_confidence(body) == 0.9


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
                        "choice": "private_edge_possible",
                        "confidence": 0.81,
                    }
                ],
            },
        )

    client = HttpxDecisionsClient(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await client.classify_regime(
        question="Side A vs Side B — who will win?",
        series_slug="series-a",
        market_json=None,
    )
    assert result.regime == "private_edge_possible"
    assert result.confidence == 0.81
    assert seen["path"] == "/v1/decisions"
    body = seen["body"]
    assert isinstance(body, dict)
    assert "questions" in body
