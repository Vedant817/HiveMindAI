from __future__ import annotations

from shared.message_schema import AgentMessage
from shared.llm_client import LLMClient
from shared.config import confidence_threshold


VALIDATOR_PROMPT = """You are the Validator agent in an enterprise swarm.
Review the executor output for correctness, security, and completeness.
Return only JSON:
{"verdict": "PASS|FAIL", "issues": ["issue list"], "confidence": 0.0}"""


class ValidatorAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def validate(self, msg: AgentMessage) -> AgentMessage:
        verdict = await self.llm.chat_json(VALIDATOR_PROMPT, msg.model_dump_json())
        if isinstance(verdict, dict):
            try:
                raw_issues = verdict.get("issues", [])
                if isinstance(raw_issues, str):
                    issues = [raw_issues]
                else:
                    issues = [str(issue) for issue in raw_issues]
                passed = str(verdict.get("verdict", "")).upper() == "PASS"
                confidence = float(verdict.get("confidence", msg.confidence))
                return AgentMessage(
                    type="validate" if passed else "escalate",
                    payload={**msg.payload, "validation": {"verdict": "PASS" if passed else "FAIL", "issues": issues}},
                    confidence=max(0.0, min(1.0, confidence)),
                    assigned_to="Validator",
                    status="done" if passed else "failed",
                    parent_task_id=msg.task_id,
                    jira_ticket_id=msg.jira_ticket_id,
                )
            except (TypeError, ValueError):
                pass

        issues: list[str] = []
        output = msg.payload.get("output")
        if not output:
            issues.append("Executor did not provide an output payload.")
        if not msg.payload.get("title"):
            issues.append("Task title is missing.")
        if "security" in str(msg.payload).lower() and msg.confidence < confidence_threshold():
            issues.append("Security-sensitive task needs human review.")

        passed = not issues
        return AgentMessage(
            type="validate" if passed else "escalate",
            payload={
                **msg.payload,
                "validation": {
                    "verdict": "PASS" if passed else "FAIL",
                    "issues": issues,
                },
            },
            confidence=msg.confidence if passed else min(msg.confidence, 0.75),
            assigned_to="Validator",
            status="done" if passed else "failed",
            parent_task_id=msg.task_id,
            jira_ticket_id=msg.jira_ticket_id,
        )
