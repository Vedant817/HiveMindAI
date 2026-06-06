from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any

from shared.config import is_real_value, require_or_fallback


class RedisClient:
    """Redis wrapper with an in-memory fallback for local demos and tests."""

    _memory: dict[str, tuple[str, datetime | None]] = {}
    _channels: dict[str, list[str]] = defaultdict(list)

    def __init__(self, url: str | None = None) -> None:
        self._url = url if url is not None else os.getenv("REDIS_URL")
        self._client = None

    async def _redis(self):
        if not is_real_value(self._url):
            require_or_fallback("Redis", "set REDIS_URL")
            return None
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as redis

            self._client = redis.from_url(self._url, decode_responses=True)
            await self._client.ping()
            return self._client
        except Exception:
            require_or_fallback("Redis", "connection failed")
            self._client = None
            return None

    async def set(self, key: str, value: dict[str, Any], ttl: int = 3600) -> None:
        raw = json.dumps(value, default=str)
        client = await self._redis()
        if client:
            await client.setex(key, ttl, raw)
            return
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl) if ttl else None
        self._memory[key] = (raw, expires)

    async def get(self, key: str) -> dict[str, Any] | None:
        client = await self._redis()
        if client:
            raw = await client.get(key)
            return json.loads(raw) if raw else None
        raw, expires = self._memory.get(key, (None, None))
        if raw is None:
            return None
        if expires and expires < datetime.now(timezone.utc):
            self._memory.pop(key, None)
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        client = await self._redis()
        if client:
            await client.delete(key)
            return
        self._memory.pop(key, None)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        raw = json.dumps(message, default=str)
        client = await self._redis()
        if client:
            await client.publish(channel, raw)
            return
        self._channels[channel].append(raw)

    async def drain_channel(self, channel: str) -> list[dict[str, Any]]:
        await asyncio.sleep(0)
        rows = self._channels.pop(channel, [])
        return [json.loads(row) for row in rows]
