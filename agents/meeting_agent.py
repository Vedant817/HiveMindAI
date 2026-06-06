from __future__ import annotations

from pathlib import Path
import re

from integrations.jira_client import JiraClient
from shared.message_schema import AgentMessage
from shared.service_bus import ServiceBusClient
from shared.llm_client import LLMClient
from shared.config import meeting_confidence, require_or_fallback


class MeetingAgent:
    def __init__(
        self,
        jira: JiraClient | None = None,
        bus: ServiceBusClient | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.jira = jira or JiraClient()
        self.bus = bus or ServiceBusClient()
        self.llm = llm or LLMClient()

    async def process_transcript(self, transcript: str) -> dict:
        tickets = await self.extract_tickets_async(transcript)
        created: list[dict] = []
        for ticket in tickets:
            jira_ticket = await self.jira.create(ticket)
            ticket["jira_ticket_id"] = jira_ticket.get("key") or jira_ticket.get("id")
            msg = AgentMessage(
                type="ticket",
                payload=ticket,
                assigned_to="PM",
                confidence=meeting_confidence(bool(ticket.get("needs_review"))),
                jira_ticket_id=ticket["jira_ticket_id"],
            )
            await self.bus.send(msg)
            created.append({"ticket": ticket, "jira": jira_ticket, "message": msg.model_dump()})
        return {"tickets": created, "count": len(created)}

    async def process_file(self, path: str | Path) -> dict:
        transcript = await self.transcribe(path)
        return await self.process_transcript(transcript)

    async def transcribe(self, path: str | Path) -> str:
        file_path = Path(path)
        if file_path.suffix.lower() in {".txt", ".md", ".vtt", ".srt"}:
            return file_path.read_text(encoding="utf-8")
        transcript = await self.llm.transcribe_audio(str(file_path))
        if transcript is not None:
            return transcript
        require_or_fallback("Azure OpenAI Whisper", "audio uploads require AZURE_OPENAI_WHISPER_DEPLOYMENT")
        return f"Review uploaded recording {file_path.name} and extract follow-up tasks."

    async def extract_tickets_async(self, transcript: str) -> list[dict]:
        rows = await self.llm.chat_json(
            """Extract actionable Jira tickets from a meeting transcript.
Return only JSON:
[{"title":"short summary","description":"full action item context","priority":"Highest|High|Medium|Low","issue_type":"Task","needs_review":false}]""",
            transcript,
        )
        tickets = self._normalize_tickets(rows)
        return tickets or self.extract_tickets(transcript)

    def extract_tickets(self, transcript: str) -> list[dict]:
        candidates: list[str] = []
        for line in transcript.splitlines():
            stripped = line.strip(" -\t")
            if not stripped:
                continue
            if re.search(r"\b(todo|action|need|needs|build|fix|create|implement|review)\b", stripped, re.I):
                candidates.append(stripped)
        if not candidates:
            candidates = [transcript.strip()[:180] or "Review meeting follow-up"]

        tickets = []
        for index, candidate in enumerate(candidates[:10], start=1):
            title = re.sub(r"^(todo|action item|action):\s*", "", candidate, flags=re.I)
            tickets.append(
                {
                    "title": title[:120],
                    "description": candidate,
                    "priority": "High" if re.search(r"\b(urgent|blocker|friday)\b", candidate, re.I) else "Medium",
                    "source": "meeting",
                    "sequence": index,
                    "needs_review": len(candidate) < 20,
                }
            )
        return tickets

    def _normalize_tickets(self, rows: object) -> list[dict]:
        if not isinstance(rows, list):
            return []
        tickets: list[dict] = []
        for index, row in enumerate(rows[:10], start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "")).strip()
            description = str(row.get("description", title)).strip()
            if not title or not description:
                continue
            priority = str(row.get("priority", "Medium")).strip() or "Medium"
            issue_type = str(row.get("issue_type", "Task")).strip() or "Task"
            try:
                sequence = int(row.get("sequence", index) or index)
            except (TypeError, ValueError):
                sequence = index
            tickets.append(
                {
                    "title": title[:120],
                    "description": description,
                    "priority": priority,
                    "issue_type": issue_type,
                    "source": str(row.get("source", "meeting") or "meeting"),
                    "sequence": sequence,
                    "needs_review": bool(row.get("needs_review", False)),
                }
            )
        return tickets
