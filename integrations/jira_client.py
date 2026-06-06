from __future__ import annotations

import base64
import os
from typing import Any
import uuid

from shared.config import is_real_value, require_or_fallback


class JiraClient:
    def __init__(self) -> None:
        domain = os.getenv("JIRA_DOMAIN", "").strip().rstrip("/")
        self._base = f"https://{domain}/rest/api/3" if domain else ""
        self._email = os.getenv("JIRA_EMAIL")
        self._token = os.getenv("JIRA_API_TOKEN")
        self._project_key = os.getenv("JIRA_PROJECT_KEY")
        self._status_names = {
            "Done": os.getenv("JIRA_DONE_STATUS", "Done"),
            "In Progress": os.getenv("JIRA_IN_PROGRESS_STATUS", "In Progress"),
            "Failed": os.getenv("JIRA_FAILED_STATUS", "Failed"),
        }

    @property
    def configured(self) -> bool:
        return all(is_real_value(value) for value in (self._base, self._email, self._token, self._project_key))

    def _headers(self) -> dict[str, str]:
        raw = f"{self._email}:{self._token}".encode("utf-8")
        token = base64.b64encode(raw).decode("utf-8")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create(self, ticket: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            require_or_fallback(
                "Jira",
                "set JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_PROJECT_KEY",
            )
            key = f"LOCAL-{str(uuid.uuid4())[:8].upper()}"
            return {"id": str(uuid.uuid4()), "key": key, "self": "local-fallback", "fields": ticket}

        import httpx

        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": ticket["title"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": ticket["description"]}],
                        }
                    ],
                },
                "issuetype": {"name": ticket.get("issue_type", "Task")},
                "priority": {"name": ticket.get("priority", "Medium")},
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base}/issue", json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def transition(self, ticket_id: str, status: str) -> dict[str, Any]:
        if not self.configured:
            require_or_fallback(
                "Jira",
                "set JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_PROJECT_KEY",
            )
            return {"ticket_id": ticket_id, "status": status, "local_fallback": True}

        import httpx

        transition_id = await self._transition_id(ticket_id, status)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/issue/{ticket_id}/transitions",
                json={"transition": {"id": transition_id}},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return {"ticket_id": ticket_id, "status": status, "transition_id": transition_id}

    async def _transition_id(self, ticket_id: str, status: str) -> str:
        import httpx

        desired_status = self._status_names.get(status, status).lower()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base}/issue/{ticket_id}/transitions",
                headers=self._headers(),
            )
            resp.raise_for_status()
        transitions = resp.json().get("transitions", [])
        for transition in transitions:
            name = str(transition.get("name", "")).lower()
            target = str(transition.get("to", {}).get("name", "")).lower()
            if desired_status in {name, target}:
                return str(transition["id"])
        available = ", ".join(t.get("name", "") for t in transitions)
        raise RuntimeError(f"No Jira transition from {ticket_id} to {status}. Available: {available}")
