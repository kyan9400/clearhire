"""The job queue's Redis connection (set REDIS_TEST_URL to run against a real Redis)."""

from __future__ import annotations

import asyncio
import os

import pytest

from clearhire import tasks
from clearhire.config import get_settings


def test_the_queue_connection_has_no_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLEARHIRE_REDIS_URL", "redis://redis.invalid:6379/0")
    get_settings.cache_clear()
    try:
        broker = tasks._broker()
        kwargs = broker.connection_pool.connection_kwargs  # type: ignore[attr-defined]
        assert kwargs["socket_timeout"] is None and kwargs["health_check_interval"] == 30
    finally:
        get_settings.cache_clear()


@pytest.mark.skipif(not os.environ.get("REDIS_TEST_URL"), reason="set REDIS_TEST_URL")
async def test_an_idle_worker_keeps_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """redis-py's default 5 s timeout used to end an idle wait with an error that killed the worker."""
    monkeypatch.setenv("CLEARHIRE_REDIS_URL", os.environ["REDIS_TEST_URL"])
    get_settings.cache_clear()
    broker = tasks._broker()
    await broker.startup()
    try:
        with pytest.raises(asyncio.TimeoutError):  # still waiting for a job, not failed
            await asyncio.wait_for(broker.listen().__anext__(), 7)
    finally:
        await broker.shutdown()
        get_settings.cache_clear()
