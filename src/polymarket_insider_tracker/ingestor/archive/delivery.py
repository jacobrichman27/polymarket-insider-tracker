"""Archive-enabled delivery helpers (policy a + bounded retry)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation

ArchiveWriteFn = Callable[[TradeObservation], Awaitable[bool]]
Sleeper = Callable[[float], Awaitable[None]]

INITIAL_BACKOFF_SECONDS = 0.25
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 5.0


class FutureConsumer(Protocol):
    """Reserved decision/execution bus slot; ships a no-op only."""

    async def consume(self, observation: TradeObservation) -> None: ...


class NoOpFutureConsumer:
    """Placeholder third fan-out consumer (no trading / order placement)."""

    async def consume(self, observation: TradeObservation) -> None:
        del observation
        return None


@dataclass
class RetryState:
    delay: float = INITIAL_BACKOFF_SECONDS

    def next_delay(self) -> float:
        current = self.delay
        self.delay = min(self.delay * BACKOFF_FACTOR, MAX_BACKOFF_SECONDS)
        return current


async def write_with_backoff(
    write: ArchiveWriteFn,
    observation: TradeObservation,
    *,
    sleeper: Sleeper,
    should_stop: Callable[[], bool],
) -> bool:
    """Retry archive writes until success, stop, or caller abandons the cycle."""
    state = RetryState()
    while True:
        if await write(observation):
            return True
        if should_stop():
            return False
        await sleeper(state.next_delay())
