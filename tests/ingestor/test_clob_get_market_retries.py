"""get_market respects max_retries override for hot-path miss fetches."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

import polymarket_insider_tracker.ingestor.clob_client as clob_module
from polymarket_insider_tracker.ingestor.clob_client import ClobClient, RetryError
from tests.fakes import FakeBaseClobClient


@pytest.fixture
def fake_base_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBaseClobClient]:
    fake = FakeBaseClobClient()

    def build(_host: str) -> FakeBaseClobClient:
        return fake

    monkeypatch.setattr(clob_module, "BaseClobClient", build)
    yield fake


@pytest.fixture
def no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def test_get_market_max_retries_zero_is_single_attempt(
    fake_base_client: FakeBaseClobClient, no_backoff_sleep: None
) -> None:
    _ = no_backoff_sleep
    calls = {"n": 0}
    original = fake_base_client.get_market

    def counting(condition_id: str) -> object:
        calls["n"] += 1
        return original(condition_id)

    fake_base_client.get_market = counting  # type: ignore[method-assign]
    fake_base_client.market_error = RuntimeError("gone")
    client = ClobClient()
    with pytest.raises(RetryError):
        client.get_market("0xabc", max_retries=0)
    assert calls["n"] == 1
