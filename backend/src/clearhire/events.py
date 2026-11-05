"""Events for other services (the Telegram bot), published to a Redis stream; dropped without Redis."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)
STREAM = "clearhire:events"


class Events:
    def __init__(self, redis_url: str | None) -> None:
        self._redis = None
        if redis_url:
            import redis.asyncio as redis

            self._redis = redis.from_url(redis_url)

    async def publish(self, kind: str, **payload: Any) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.xadd(
                STREAM, {"kind": kind, "data": json.dumps(payload, default=str)}, maxlen=10_000
            )
        except Exception:  # an event bus outage must not fail the request that caused the event
            log.exception("could not publish %s", kind)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
