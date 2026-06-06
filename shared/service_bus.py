from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import os

from shared.message_schema import AgentMessage
from shared.config import is_real_value, require_or_fallback


class ServiceBusClient:
    """Azure Service Bus wrapper with a process-local queue fallback."""

    _queues: dict[str, deque[AgentMessage]] = defaultdict(deque)

    def __init__(self, connection_string: str | None = None) -> None:
        self._conn = connection_string if connection_string is not None else os.getenv(
            "AZURE_SERVICE_BUS_CONNECTION_STRING"
        )
        self._redis_url = os.getenv("REDIS_URL")
        self._redis_client = None

    @property
    def default_task_queue(self) -> str:
        return os.getenv("TASK_QUEUE_NAME", "task-queue")

    async def send(self, msg: AgentMessage, queue: str | None = None) -> None:
        queue = queue or self.default_task_queue
        redis_client = await self._redis()
        if redis_client is not None:
            await redis_client.rpush(queue, msg.model_dump_json())
            return
        if not is_real_value(self._conn):
            require_or_fallback("Azure Service Bus", "set AZURE_SERVICE_BUS_CONNECTION_STRING")
            self._queues[queue].append(msg)
            return
        try:
            from azure.servicebus import ServiceBusMessage
            from azure.servicebus.aio import ServiceBusClient as AzureServiceBusClient

            async with AzureServiceBusClient.from_connection_string(self._conn) as client:
                async with client.get_queue_sender(queue) as sender:
                    await sender.send_messages(ServiceBusMessage(msg.model_dump_json()))
        except Exception:
            require_or_fallback("Azure Service Bus", "connection failed")
            self._queues[queue].append(msg)

    async def receive(self, queue: str | None = None, max_messages: int = 10) -> list[AgentMessage]:
        queue = queue or self.default_task_queue
        redis_client = await self._redis()
        if redis_client is not None:
            result: list[AgentMessage] = []
            for _ in range(max_messages):
                raw = await redis_client.lpop(queue)
                if raw is None:
                    break
                result.append(AgentMessage.model_validate_json(raw))
            return result
        if not is_real_value(self._conn):
            require_or_fallback("Azure Service Bus", "set AZURE_SERVICE_BUS_CONNECTION_STRING")
            return self._receive_local(queue, max_messages)
        try:
            from azure.servicebus.aio import ServiceBusClient as AzureServiceBusClient

            async with AzureServiceBusClient.from_connection_string(self._conn) as client:
                async with client.get_queue_receiver(queue) as receiver:
                    messages = await receiver.receive_messages(
                        max_message_count=max_messages,
                        max_wait_time=5,
                    )
                    result: list[AgentMessage] = []
                    for message in messages:
                        result.append(AgentMessage.model_validate_json(str(message)))
                        await receiver.complete_message(message)
                    return result
        except Exception:
            require_or_fallback("Azure Service Bus", "connection failed")
            return self._receive_local(queue, max_messages)

    def _receive_local(self, queue: str, max_messages: int) -> list[AgentMessage]:
        result: list[AgentMessage] = []
        for _ in range(max_messages):
            if not self._queues[queue]:
                break
            result.append(self._queues[queue].popleft())
        return result

    async def drain(self, queue: str | None = None) -> list[AgentMessage]:
        await asyncio.sleep(0)
        queue = queue or self.default_task_queue
        redis_client = await self._redis()
        if redis_client is not None:
            rows: list[AgentMessage] = []
            while True:
                raw = await redis_client.lpop(queue)
                if raw is None:
                    break
                rows.append(AgentMessage.model_validate_json(raw))
            return rows
        return self._receive_local(queue, 10000)

    async def _redis(self):
        if not is_real_value(self._redis_url):
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis.asyncio as redis

            self._redis_client = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis_client.ping()
            return self._redis_client
        except Exception:
            require_or_fallback("Upstash Redis", "connection failed")
            self._redis_client = None
            return None
