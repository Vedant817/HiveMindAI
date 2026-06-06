from __future__ import annotations

import asyncio
import os

from integrations.jira_client import JiraClient
from integrations.slack_client import SlackClient
from shared.message_schema import AgentMessage
from shared.config import is_real_value, require_or_fallback, strict_integrations


class CommsAgent:
    def __init__(
        self,
        jira: JiraClient | None = None,
        slack: SlackClient | None = None,
    ) -> None:
        self.jira = jira or JiraClient()
        self.slack = slack or SlackClient()
        self._teams_webhook = os.getenv("TEAMS_WEBHOOK_URL")

    async def on_task_complete(self, msg: AgentMessage) -> dict:
        results = await asyncio.gather(
            self.post_slack(msg),
            self.post_teams(msg),
            self.update_jira(msg),
            return_exceptions=not strict_integrations(),
        )
        return {"results": [str(result) if isinstance(result, Exception) else result for result in results]}

    async def post_slack(self, msg: AgentMessage) -> dict:
        text = (
            f"[{msg.status.upper()}] {msg.payload.get('title', 'Task')}\n"
            f"Agent: {msg.assigned_to or 'unknown'} | Confidence: {msg.confidence:.0%}"
        )
        return await self.slack.post(text)

    async def post_teams(self, msg: AgentMessage) -> dict:
        card = {
            "@type": "MessageCard",
            "themeColor": "00B050" if msg.status == "done" else "FF0000",
            "summary": f"Task {msg.status}",
            "sections": [
                {
                    "activityTitle": msg.payload.get("title", "Task completed"),
                    "facts": [
                        {"name": "Status", "value": msg.status},
                        {"name": "Agent", "value": msg.assigned_to or ""},
                        {"name": "Confidence", "value": f"{msg.confidence:.0%}"},
                    ],
                }
            ],
        }
        if not is_real_value(self._teams_webhook):
            require_or_fallback("Microsoft Teams", "set TEAMS_WEBHOOK_URL")
            return {"local_fallback": True, "card": card}

        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self._teams_webhook, json=card)
            resp.raise_for_status()
        return {"sent": True}

    async def update_jira(self, msg: AgentMessage) -> dict:
        if not msg.jira_ticket_id:
            return {"skipped": "no_jira_ticket_id"}
        transition = "Done" if msg.status == "done" else "Failed"
        return await self.jira.transition(msg.jira_ticket_id, transition)
