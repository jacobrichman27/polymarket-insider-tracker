"""OpenAI Decisions API adapter for knowability model-on-miss.

Request/response shape follows the Decisions create contract:
``POST /v1/decisions`` with ``input`` evidence + ``questions``; response
``answers[]`` where a choice question yields ``{type: "choice", choice: ...}``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import httpx

from polymarket_insider_tracker.archive_defaults import (
    DEFAULT_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY,
)

DECISIONS_URL = "https://api.openai.com/v1/decisions"
DECISIONS_MODEL = "gpt-6-luna"
KNOWABILITY_PROMPT_VERSION = "knowability.prompt.v8"
KNOWABILITY_MODEL_VERSION = f"{DECISIONS_MODEL}/{KNOWABILITY_PROMPT_VERSION}"
REGIME_CHOICES = (
    "no_private_edge",
    "private_edge_possible",
    "unknown",
)
REGIME_QUESTION_NAME = "knowability_regime"
TITLE_RULE_LABEL_SOURCE = "title_rule"
_EVIDENCE_TEXT_CAP = 500
_USAGE_LOG_PATH = "/tmp/knowability_decisions_usage.jsonl"

_REGIME_CHOICE_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "value": "no_private_edge",
        "description": (
            "There is no meaningful privileged, non-public informational "
            "advantage about how this market will settle before that "
            "settlement becomes public."
        ),
    },
    {
        "value": "private_edge_possible",
        "description": (
            "Some party can hold a privileged, non-public informational "
            "advantage about how this market will settle before that "
            "settlement becomes public. That may be the finished settlement "
            "result itself, or non-public intermediate information that can "
            "materially change settlement odds."
        ),
    },
    {
        "value": "unknown",
        "description": (
            "The listing does not make clear whether a privileged, "
            "non-public informational advantage exists."
        ),
    },
)

_REGIME_INSTRUCTIONS_CORE = (
    "Classify the information-knowability of this prediction-market listing. "
    "Base the classification only on how the market settles. Do not classify "
    "from topic resemblance, category habit, or ordinary forecasting skill. "
    "Apply this settlement test. "
    "If the public learns the result only by watching a public process finish "
    "(a public price path, scoreboard aggregation, a season of public contests, "
    "public post or search counts, or other continuously public observables), "
    "choose no_private_edge. "
    "If some party can hold the finished settlement result itself, or a "
    "decisive contest edge, before that public process completes (held "
    "decisions, votes, awards, ballots, official announcements, compiled "
    "measured releases, or a single contest moneyline/spread/handicap), "
    "choose private_edge_possible. "
    "If the listing does not make the settlement structure clear, choose "
    "unknown. "
    "Do not choose private_edge_possible over no_private_edge merely because "
    "the structure is ambiguous; if it is unclear, choose unknown. "
    "Your confidence score must be the probability that the chosen regime "
    "is correct. Use high confidence only when the settlement mechanism "
    "clearly maps to one regime. If you are torn between regimes, keep "
    "confidence low. "
    "The timing of when privileged knowledge might appear does not create "
    "another regime. "
    "Pick exactly one choice."
)

_NOTE_OU = (
    "The market title uses over/under point-total wording. Treat settlement "
    "as an aggregate scoring total that becomes known as the public "
    "scoreboard unfolds. Choose no_private_edge."
)
_NOTE_HANDICAP = (
    "The market title appears to use spread or handicap wording, or a signed "
    "handicap line. If that is the case, treat this as a market that evaluates whether "
    "a side covers a final margin, and choose private_edge_possible. Otherwise, choose no_private_edge."
)
_NOTE_EXACT_SCORE = (
    "The market title uses exact-scoreline wording. An exact finished "
    "scoreline is usually not knowable through privileged intermediate "
    "information. Choose no_private_edge."
)
_NOTE_IN_EVENT = (
    "The market title refers to an in-progress or partial state. If the "
    "settlement can be known only as public play unfolds in real time, "
    "choose no_private_edge."
)
_NOTE_UP_OR_DOWN = (
    "The market title uses up-or-down path wording. If settlement comes "
    "from a short public price path, choose no_private_edge."
)
_NOTE_DOLLAR = (
    "The market title includes a dollar-denominated level. If settlement is "
    "tied to public quoted prices or other publicly observable monetary "
    "levels, choose no_private_edge, unless some party can hold the finished "
    "measured value before public release."
)
_NOTE_TEMPERATURE = (
    "The market title refers to temperature. Treat settlement as a "
    "continuously public weather observable. Choose no_private_edge."
)
_NOTE_TWEETS = (
    "The market title refers to tweets, Truth Social posts, or similar "
    "public posts. If settlement depends on a count that only becomes known "
    "as public posts accumulate in real time, choose no_private_edge."
)

_OU = re.compile(r"\bo\s*/\s*u\b|\bover\s*/\s*under\b", re.IGNORECASE)
# "Spread: ...", "Map/Game Handicap: ...", or a signed line like "(-2.5)" / "(+1.5)".
_HANDICAP = re.compile(
    r"\bspread\b|\bhandicap\b|\([+-]\d+(?:\.\d+)?\)",
    re.IGNORECASE,
)
_EXACT_SCORE = re.compile(r"\bexact\s+score\b", re.IGNORECASE)
_IN_EVENT = re.compile(
    r"\bhalftime\b|\banytime\b|\bleading at\b|\bin progress\b",
    re.IGNORECASE,
)
_UP_OR_DOWN = re.compile(r"\bup\s+or\s+down\b", re.IGNORECASE)
_TEMPERATURE = re.compile(r"\btemperature\b", re.IGNORECASE)
_TWEETS = re.compile(r"\btweets?\b|\btruth\s+social\b", re.IGNORECASE)

# High-precision title short-circuits: skip Decisions entirely.
_NO_EDGE_TITLE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_TEMPERATURE, "temperature"),
    (_UP_OR_DOWN, "up_or_down"),
    (_TWEETS, "public_posts"),
    (_OU, "point_total_ou"),
    (_EXACT_SCORE, "exact_score"),
    (_IN_EVENT, "in_event"),
)


@dataclass(frozen=True)
class DecisionsRegimeResult:
    regime: str
    confidence: float | None = None
    raw: object | None = None


class DecisionsClient(Protocol):
    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult: ...


@dataclass
class BudgetGate:
    """UTC-day call budget + simple consecutive-error circuit."""

    max_calls_per_day: int
    day_key: str = ""
    calls_today: int = 0
    input_tokens_today: int = 0
    output_tokens_today: int = 0
    consecutive_errors: int = 0
    circuit_open: bool = False
    error_threshold: int = 5

    def allow(self, day_key: str) -> bool:
        if day_key != self.day_key:
            self.day_key = day_key
            self.calls_today = 0
            self.input_tokens_today = 0
            self.output_tokens_today = 0
            self.consecutive_errors = 0
            self.circuit_open = False
        if self.circuit_open:
            return False
        return self.calls_today < self.max_calls_per_day

    def record_success(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.calls_today += 1
        self.input_tokens_today += max(0, input_tokens)
        self.output_tokens_today += max(0, output_tokens)
        self.consecutive_errors = 0

    def record_error(self) -> None:
        self.calls_today += 1
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.error_threshold:
            self.circuit_open = True


class HttpxDecisionsClient:
    """POST /v1/decisions with a single named choice question."""

    def __init__(
        self,
        *,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        budget: BudgetGate | None = None,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self.budget = budget or BudgetGate(
            max_calls_per_day=DEFAULT_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY
        )

    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult:
        payload = choice_payload(question, series_slug, market_json=market_json)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as client:
                response = await client.post(DECISIONS_URL, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            self.budget.record_error()
            return DecisionsRegimeResult(regime="unknown")
        in_tok, out_tok = extract_usage_tokens(body)
        self.budget.record_success(input_tokens=in_tok, output_tokens=out_tok)
        _append_usage_log(input_tokens=in_tok, output_tokens=out_tok)
        return DecisionsRegimeResult(
            regime=extract_regime(body),
            confidence=extract_confidence(body),
            raw=body,
        )


def no_edge_title_rule(question: str) -> str | None:
    """Return a no-edge title-rule id when the title is an easy public shape."""
    for pattern, rule_id in _NO_EDGE_TITLE_RULES:
        if pattern.search(question):
            return rule_id
    return None


def _clip_evidence(value: str) -> str:
    text = " ".join(value.split())
    if len(text) <= _EVIDENCE_TEXT_CAP:
        return text
    return f"{text[: _EVIDENCE_TEXT_CAP - 3]}..."


def _market_json_fields(market_json: object | None) -> tuple[str, str]:
    if not isinstance(market_json, dict):
        return "(none)", "(none)"
    raw_source = market_json.get("resolutionSource")
    if raw_source is None:
        raw_source = market_json.get("resolution_source")
    raw_desc = market_json.get("description")
    source = _clip_evidence(str(raw_source)) if raw_source else "(none)"
    desc = _clip_evidence(str(raw_desc)) if raw_desc else "(none)"
    return source, desc


def _evidence_input(
    question: str,
    series_slug: str | None,
    *,
    market_json: object | None = None,
) -> str:
    q = question.strip() or "(missing)"
    series = (series_slug or "").strip() or "(none)"
    source, desc = _market_json_fields(market_json)
    return (
        f"Market question: {q}\n"
        f"Series slug: {series}\n"
        f"Resolution source: {source}\n"
        f"Description: {desc}"
    )


def _append_usage_log(*, input_tokens: int, output_tokens: int) -> None:
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "prompt_version": KNOWABILITY_PROMPT_VERSION,
        "model": DECISIONS_MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    with open(_USAGE_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def title_cue_notes(question: str) -> tuple[str, ...]:
    """Conditional instruction notes from title cues (no topic examples)."""
    notes: list[str] = []
    if _OU.search(question):
        notes.append(_NOTE_OU)
    elif _HANDICAP.search(question):
        # O/U titles can also contain parentheses; prefer the total cue.
        notes.append(_NOTE_HANDICAP)
    if _EXACT_SCORE.search(question):
        notes.append(_NOTE_EXACT_SCORE)
    if _IN_EVENT.search(question):
        notes.append(_NOTE_IN_EVENT)
    if _UP_OR_DOWN.search(question):
        notes.append(_NOTE_UP_OR_DOWN)
    if "$" in question:
        notes.append(_NOTE_DOLLAR)
    if _TEMPERATURE.search(question):
        notes.append(_NOTE_TEMPERATURE)
    if _TWEETS.search(question):
        notes.append(_NOTE_TWEETS)
    return tuple(notes)


def regime_instructions(question: str) -> str:
    """Core knowability instructions plus any title-cue notes."""
    notes = title_cue_notes(question)
    if not notes:
        return _REGIME_INSTRUCTIONS_CORE
    joined = " ".join(notes)
    return f"{_REGIME_INSTRUCTIONS_CORE} " f"Additional notes based on the market title: {joined}"


def choice_payload(
    question: str,
    series_slug: str | None,
    *,
    market_json: object | None = None,
) -> dict[str, Any]:
    """Documented Decisions create body: shared ``input`` + ``questions``."""
    return {
        "model": DECISIONS_MODEL,
        "input": _evidence_input(question, series_slug, market_json=market_json),
        "questions": [
            {
                "type": "choice",
                "name": REGIME_QUESTION_NAME,
                "instructions": regime_instructions(question),
                "choices": [dict(option) for option in _REGIME_CHOICE_OPTIONS],
            }
        ],
    }


def extract_usage_tokens(body: object) -> tuple[int, int]:
    """Parse Decisions ``usage`` token counts when present."""
    if not isinstance(body, dict):
        return 0, 0
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    raw_in = usage.get("input_tokens", 0)
    raw_out = usage.get("output_tokens", 0)
    in_tok = int(raw_in) if isinstance(raw_in, int) and not isinstance(raw_in, bool) else 0
    out_tok = int(raw_out) if isinstance(raw_out, int) and not isinstance(raw_out, bool) else 0
    return max(0, in_tok), max(0, out_tok)


def _first_choice_answer(body: object) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    answers = cast(dict[str, Any], body).get("answers")
    if not isinstance(answers, list) or not answers:
        return None
    first_obj = cast(object, answers[0])
    if not isinstance(first_obj, dict):
        return None
    return cast(dict[str, Any], first_obj)


def extract_regime(body: object) -> str:
    """Parse documented ``answers[0].choice`` (or refusal → unknown)."""
    entry = _first_choice_answer(body)
    if entry is None or entry.get("type") == "refusal":
        return "unknown"
    choice = entry.get("choice")
    if isinstance(choice, str) and choice in REGIME_CHOICES:
        return choice
    return "unknown"


def extract_confidence(body: object) -> float | None:
    """Parse documented ``answers[0].confidence`` when present and finite."""
    entry = _first_choice_answer(body)
    if entry is None or entry.get("type") == "refusal":
        return None
    value = entry.get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if score < 0.0 or score > 1.0:
        return None
    return score


class NullDecisionsClient:
    """No-op client when model is forced off or credentials absent."""

    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult:
        del question, series_slug, market_json
        return DecisionsRegimeResult(regime="unknown")
