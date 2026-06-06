from __future__ import annotations

from hitl.teams_bot import TeamsBot
from shared.message_schema import AgentMessage
from shared.redis_client import RedisClient
from shared.config import confidence_threshold


class ConfidenceGate:
    def __init__(
        self,
        teams: TeamsBot | None = None,
        redis: RedisClient | None = None,
        threshold: float | None = None,
    ) -> None:
        self.teams = teams or TeamsBot()
        self.redis = redis or RedisClient()
        self.threshold = confidence_threshold() if threshold is None else threshold

    async def evaluate(self, msg: AgentMessage) -> str:
        if msg.confidence >= self.threshold:
            await self._log_auto_execute(msg)
            return "auto_execute"
        approval_id = await self.teams.send_approval_card(msg)
        await self.redis.set(f"pending:{approval_id}", msg.model_dump(), ttl=86400)
        return "awaiting_human"

    async def resolve(self, approval_id: str, approved: bool) -> dict:
        data = await self.redis.get(f"pending:{approval_id}")
        if not data:
            return {"error": "Approval request expired or not found"}
        msg = AgentMessage.model_validate(data)
        await self.redis.delete(f"pending:{approval_id}")
        if approved:
            return {"action": "execute", "task": msg.payload}
        return {"action": "cancelled", "task": msg.payload}

    async def _log_auto_execute(self, msg: AgentMessage) -> None:
        await self.redis.set(
            f"auto:{msg.task_id}",
            {
                "task_id": msg.task_id,
                "confidence": msg.confidence,
                "auto_executed": True,
            },
        )
