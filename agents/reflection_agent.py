from __future__ import annotations

from datetime import datetime, timezone

from memory.cosmos_client import CosmosClient
from shared.redis_client import RedisClient
from shared.llm_client import LLMClient
from shared.config import confidence_threshold, require_or_fallback


class ReflectionAgent:
    def __init__(
        self,
        cosmos: CosmosClient | None = None,
        redis: RedisClient | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.cosmos = cosmos or CosmosClient()
        self.redis = redis or RedisClient()
        self.llm = llm or LLMClient()

    async def reflect(self, task_history: list[dict], dag_id: str) -> dict:
        if self.llm.configured:
            row = await self.llm.chat_json(
                """Analyse this completed task run and return JSON:
{"duration_ok":true,"confidence_accurate":true,"best_agent":"agent","failure_reason":null,"bottleneck":null,"improvement":"one actionable PM improvement"}""",
                str(task_history),
            )
            if row is not None:
                row["dag_id"] = dag_id
                row["timestamp"] = datetime.now(timezone.utc).isoformat()
                await self.cosmos.upsert("Reflections", row)
                await self._update_pm_context(row["improvement"])
                return row
        require_or_fallback("LLM provider", "set OpenRouter or Azure OpenAI variables for AI reflection")

        failed = [row for row in task_history if row.get("status") == "failed"]
        confidences = [float(row.get("confidence", 1.0)) for row in task_history]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
        insights = {
            "duration_ok": True,
            "confidence_accurate": avg_confidence >= 0.8 and not failed,
            "best_agent": self._best_agent(task_history),
            "failure_reason": failed[0].get("payload", {}).get("validation", {}).get("issues") if failed else None,
            "bottleneck": None,
            "improvement": self._improvement(failed, avg_confidence),
            "dag_id": dag_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.cosmos.upsert("Reflections", insights)
        await self._update_pm_context(insights["improvement"])
        return insights

    def _best_agent(self, task_history: list[dict]) -> str:
        done = [row for row in task_history if row.get("status") == "done" and row.get("assigned_to")]
        return done[-1]["assigned_to"] if done else "unknown"

    def _improvement(self, failed: list[dict], avg_confidence: float) -> str:
        if failed:
            return "Route low-confidence or failed validation tasks to human approval earlier."
        if avg_confidence < confidence_threshold():
            return "Add clearer acceptance criteria during planning to raise execution confidence."
        return "Current workflow is healthy; preserve the planner-executor-validator sequence."

    async def _update_pm_context(self, improvement: str) -> None:
        recent = await self.cosmos.query("Reflections", where="ORDER BY c.timestamp DESC", limit=5)
        insights_text = "\n".join(f"- {row['improvement']}" for row in recent if "improvement" in row)
        if not insights_text:
            insights_text = f"- {improvement}"
        await self.redis.set("pm_dynamic_context", {"text": insights_text}, ttl=604800)
