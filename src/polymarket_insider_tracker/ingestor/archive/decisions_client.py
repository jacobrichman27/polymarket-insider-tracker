"""OpenAI Decisions API adapter for knowability model-on-miss.

Request/response shape follows the Decisions create contract:
``POST /v1/decisions`` with ``input`` evidence + ``questions``; response
``answers[]`` where a choice question yields ``{type: "choice", choice: ...}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx

from polymarket_insider_tracker.archive_defaults import (
    DEFAULT_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY,
)

DECISIONS_URL = "https://api.openai.com/v1/decisions"
DECISIONS_MODEL = "gpt-6-luna"
REGIME_CHOICES = ("no_private_edge", "private_edge_possible", "unknown")
REGIME_QUESTION_NAME = "knowability_regime"

_REGIME_CHOICE_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "value": "no_private_edge",
        "description": (
            "No meaningful non-public informational edge exists: anyone who "
            "could know the settlement fact early has only the same public "
            "signals as everyone else (no privileged channel)."
        ),
    },
    {
        "value": "private_edge_possible",
        "description": (
            "Some party can hold privileged, non-public knowledge of the "
            "eventual settlement fact before that fact is public."
        ),
    },
    {
        "value": "unknown",
        "description": (
            "The listing does not clearly establish whether a privileged "
            "non-public edge exists."
        ),
    },
)

_REGIME_INSTRUCTIONS = (
    "Classify information-knowability for this prediction-market listing: "
    "could someone with a privileged, non-public channel know the eventual "
    "settlement fact before that fact is public? Answer yes "
    "(private_edge_possible) or no (no_private_edge). Judge the structure of "
    "the question, not resemblance to familiar categories. Ignore ordinary "
    "forecast skill, public data, or widely available models—those are not "
    "insider edges. Timing of when privileged knowledge might appear does not "
    "create a third category. Pick exactly one regime from the supplied choices."
)


@dataclass(frozen=True)
class DecisionsRegimeResult:
    regime: str
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
    consecutive_errors: int = 0
    circuit_open: bool = False
    error_threshold: int = 5

    def allow(self, day_key: str) -> bool:
        if day_key != self.day_key:
            self.day_key = day_key
            self.calls_today = 0
            self.consecutive_errors = 0
            self.circuit_open = False
        if self.circuit_open:
            return False
        return self.calls_today < self.max_calls_per_day

    def record_success(self) -> None:
        self.calls_today += 1
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
        del market_json
        payload = choice_payload(question, series_slug)
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
        self.budget.record_success()
        return DecisionsRegimeResult(regime=extract_regime(body), raw=body)


def _evidence_input(question: str, series_slug: str | None) -> str:
    q = question.strip() or "(missing)"
    series = (series_slug or "").strip() or "(none)"
    return f"Market question: {q}\nSeries slug: {series}"


def choice_payload(question: str, series_slug: str | None) -> dict[str, Any]:
    """Documented Decisions create body: shared ``input`` + ``questions``."""
    return {
        "model": DECISIONS_MODEL,
        "input": _evidence_input(question, series_slug),
        "questions": [
            {
                "type": "choice",
                "name": REGIME_QUESTION_NAME,
                "instructions": _REGIME_INSTRUCTIONS,
                "choices": [dict(option) for option in _REGIME_CHOICE_OPTIONS],
            }
        ],
    }


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
