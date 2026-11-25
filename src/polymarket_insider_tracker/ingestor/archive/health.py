"""Trade-archive readiness signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from polymarket_insider_tracker.ingestor.health import ComponentStatus

DEGRADED_OWED_SECONDS = 30.0
DEGRADED_FAILURE_WINDOW_SECONDS = 60.0
DOWN_OWED_SECONDS = 300.0
DOWN_FAILURE_WINDOW_SECONDS = 300.0


class TapeLevel(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class ArchiveHealthSignals:
    """Mutable in-process signals feeding the ``trade_archive`` checker."""

    recent_failure_at: float | None = None
    last_attempt_at: float | None = None
    attempts_in_window: int = 0
    failures_in_window: int = 0
    _owed: dict[str, float] = field(default_factory=dict[str, float])
    _failure_times: list[float] = field(default_factory=list[float])
    _attempt_times: list[float] = field(default_factory=list[float])

    def mark_owed(self, identity: str, now: float) -> None:
        if identity not in self._owed:
            self._owed[identity] = now

    def clear_owed(self, identity: str) -> None:
        self._owed.pop(identity, None)

    def owed_count(self) -> int:
        return len(self._owed)

    def oldest_owed_age(self, now: float) -> float:
        age = self._owed_age(now)
        return 0.0 if age is None else age

    def mark_attempt(self, now: float, *, failed: bool) -> None:
        self.last_attempt_at = now
        self._attempt_times.append(now)
        if failed:
            self.recent_failure_at = now
            self._failure_times.append(now)
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - DOWN_FAILURE_WINDOW_SECONDS
        self._attempt_times = [stamp for stamp in self._attempt_times if stamp >= cutoff]
        self._failure_times = [stamp for stamp in self._failure_times if stamp >= cutoff]
        self.attempts_in_window = len(self._attempt_times)
        self.failures_in_window = len(self._failure_times)

    def evaluate(self, now: float) -> ComponentStatus:
        level = self._level(now)
        owed = self._owed_age(now)
        if level is TapeLevel.UP:
            return ComponentStatus(status=level.value)
        reason = f"owed_age={owed}; failures={self.failures_in_window}/{self.attempts_in_window}"
        return ComponentStatus(status=level.value, last_error=reason)

    def _owed_age(self, now: float) -> float | None:
        if not self._owed:
            return None
        return max(0.0, now - min(self._owed.values()))

    def _recent_failure(self, now: float) -> bool:
        if self.recent_failure_at is None:
            return False
        return (now - self.recent_failure_at) <= DEGRADED_FAILURE_WINDOW_SECONDS

    def _level(self, now: float) -> TapeLevel:
        if self._is_down(now):
            return TapeLevel.DOWN
        if self._is_degraded(now):
            return TapeLevel.DEGRADED
        return TapeLevel.UP

    def _is_down(self, now: float) -> bool:
        owed = self._owed_age(now)
        if owed is not None and owed > DOWN_OWED_SECONDS:
            return True
        return self._all_attempts_failed(now)

    def _is_degraded(self, now: float) -> bool:
        owed = self._owed_age(now)
        if owed is not None and owed > DEGRADED_OWED_SECONDS:
            return True
        return self._recent_failure(now)

    def _all_attempts_failed(self, now: float) -> bool:
        self._prune(now)
        if self.attempts_in_window < 1:
            return False
        window_start = now - DOWN_FAILURE_WINDOW_SECONDS
        if self.last_attempt_at is None or self.last_attempt_at < window_start:
            return False
        return self.failures_in_window >= self.attempts_in_window
