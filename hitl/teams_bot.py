from __future__ import annotations

import os
import uuid

from shared.message_schema import AgentMessage
from shared.config import is_real_value, require_or_fallback
from shared.security import sign_token


class TeamsBot:
    def __init__(self) -> None:
        self._webhook = os.getenv("TEAMS_WEBHOOK_URL")
        self._base_url = os.getenv("APP_BASE_URL")

    async def send_approval_card(self, msg: AgentMessage) -> str:
        approval_id = str(uuid.uuid4())
        token = sign_token(approval_id)
        token_query = f"?token={token}" if token else ""
        if not is_real_value(self._webhook) or not is_real_value(self._base_url):
            require_or_fallback("Microsoft Teams", "set TEAMS_WEBHOOK_URL and APP_BASE_URL")
            return approval_id
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "FF8C00",
            "summary": "Agent approval required",
            "sections": [
                {
                    "activityTitle": "Agent needs your approval",
                    "activitySubtitle": f"Confidence: {msg.confidence:.0%}",
                    "facts": [
                        {"name": "Task", "value": msg.payload.get("title", "Unknown")},
                        {"name": "Agent", "value": msg.assigned_to or "Unknown"},
                        {"name": "Type", "value": msg.type},
                        {"name": "Confidence", "value": f"{msg.confidence:.0%}"},
                    ],
                }
            ],
            "potentialAction": [
                {
                    "@type": "HttpPOST",
                    "name": "Approve",
                    "target": f"{self._base_url}/approval/{approval_id}/approve{token_query}",
                },
                {
                    "@type": "HttpPOST",
                    "name": "Reject",
                    "target": f"{self._base_url}/approval/{approval_id}/reject{token_query}",
                },
            ],
        }
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self._webhook, json=card)
            resp.raise_for_status()
        return approval_id
