from __future__ import annotations

from shared.llm_client import LLMClient
from shared.config import require_or_fallback


SUMMARY_PROMPT = """Generate a concise executive project summary from task JSON.
Include project health, completed count, blockers, risks, and ETA.
Do not invent facts not present in the task data."""


class SummaryAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def generate(self, tasks: list[dict]) -> str:
        if self.llm.configured:
            text = await self.llm.chat_text(SUMMARY_PROMPT, str(tasks), temperature=0.2)
            if text is not None:
                return text
        require_or_fallback("LLM provider", "set OpenRouter or Azure OpenAI variables for AI-generated summaries")

        total = len(tasks)
        done = sum(1 for task in tasks if task.get("status") == "done")
        failed = [task for task in tasks if task.get("status") == "failed"]
        running = [task for task in tasks if task.get("status") == "running"]
        health = round((done / total * 100) if total else 0)

        blockers = "\n".join(f"- {self._title(task)}" for task in failed) or "None"
        risks = "\n".join(f"- {self._title(task)}" for task in running) or "None"
        eta = "on track for current sprint end" if health > 75 else "at risk - review blockers"

        return (
            f"Project Health: {health}%\n\n"
            f"Completed today: {done}/{total} tasks\n\n"
            f"Blockers:\n{blockers}\n\n"
            f"Risks:\n{risks}\n\n"
            f"Estimated ETA: Based on current velocity, {eta}"
        )

    def _title(self, task: dict) -> str:
        payload = task.get("payload") or {}
        return payload.get("title") or task.get("title") or task.get("task_id") or "Untitled task"
