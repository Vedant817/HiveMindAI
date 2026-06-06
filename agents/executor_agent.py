from __future__ import annotations

from datetime import datetime, timezone

from shared.artifacts import write_task_artifacts
from shared.message_schema import AgentMessage
from shared.llm_client import LLMClient
from shared.config import executor_confidence_cap, executor_confidence_floor


EXECUTOR_PROMPT = """You are the Executor agent in an enterprise swarm.
Given a task JSON, produce the implementation result as JSON:
{
  "output": {
    "summary": "what was completed",
    "details": "specific work performed",
    "artifacts": ["files, ticket ids, urls, or deliverables if any"]
  },
  "confidence": 0.0
}
Return only JSON."""


class ExecutorAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def execute(self, msg: AgentMessage) -> AgentMessage:
        generated = await self.llm.chat_json(EXECUTOR_PROMPT, msg.model_dump_json())
        if isinstance(generated, dict):
            try:
                output = generated.get("output", generated)
                if not isinstance(output, dict):
                    output = {"summary": str(output), "details": str(output)}
                confidence = float(generated.get("confidence", msg.confidence))
                output = self._with_artifacts(msg.payload, output)
                return AgentMessage(
                    type="complete",
                    payload={**msg.payload, "output": output},
                    confidence=max(0.0, min(1.0, confidence)),
                    assigned_to="Executor",
                    status="done",
                    parent_task_id=msg.task_id,
                    jira_ticket_id=msg.jira_ticket_id,
                )
            except (TypeError, ValueError):
                pass

        title = msg.payload.get("title", "Untitled task")
        description = msg.payload.get("description", "")
        output = {
            "title": title,
            "summary": f"Completed task: {title}",
            "details": description,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": msg.payload.get("artifacts", []),
        }
        output = self._with_artifacts(msg.payload, output)
        confidence = min(executor_confidence_cap(), max(executor_confidence_floor(), msg.confidence))
        return AgentMessage(
            type="complete",
            payload={**msg.payload, "output": output},
            confidence=confidence,
            assigned_to="Executor",
            status="done",
            parent_task_id=msg.task_id,
            jira_ticket_id=msg.jira_ticket_id,
        )

    def _with_artifacts(self, task: dict, output: dict) -> dict:
        artifacts = list(output.get("artifacts") or [])
        artifacts.extend(write_task_artifacts(task, output))
        output["artifacts"] = sorted({str(path) for path in artifacts})
        return output
