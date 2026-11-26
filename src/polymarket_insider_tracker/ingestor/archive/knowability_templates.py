"""Knowability template allowlist slot (matching disabled by default).

Lookup order still reserves override → series → template → Decisions. When
``TEMPLATE_MATCHING_ENABLED`` is false the template step is skipped entirely.
Reserved ids are for a future allowlist bump with high-precision rules.
"""

from __future__ import annotations

from dataclasses import dataclass

TEMPLATE_ALLOWLIST_VERSION = "knowability.templates.v1"
TEMPLATE_MATCHING_ENABLED = False

# Reserved for a future allowlist bump — matching currently disabled.
CRYPTO_UP_OR_DOWN_WINDOW = "CRYPTO_UP_OR_DOWN_WINDOW"
SPORTS_MATCHUP_WINNER = "SPORTS_MATCHUP_WINNER"
EARNINGS_BEAT_EPS = "EARNINGS_BEAT_EPS"

ALLOWLIST_REGIMES: dict[str, str] = {
    CRYPTO_UP_OR_DOWN_WINDOW: "no_private_edge",
    SPORTS_MATCHUP_WINNER: "private_edge_possible",
    EARNINGS_BEAT_EPS: "private_edge_possible",
}


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    regime: str


def match_template(
    question: str,
    *,
    category: str | None = None,
) -> TemplateMatch | None:
    """Match question text to an allowlisted template when matching is enabled."""
    if not TEMPLATE_MATCHING_ENABLED:
        return None
    del question, category
    return None
