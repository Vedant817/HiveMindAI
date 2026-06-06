from __future__ import annotations

import os

from shared.config import is_real_value, require_or_fallback


class SlackClient:
    def __init__(self) -> None:
        self._webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.sent_messages: list[str] = []

    async def post(self, text: str) -> dict:
        self.sent_messages.append(text)
        if not is_real_value(self._webhook):
            require_or_fallback("Slack", "set SLACK_WEBHOOK_URL")
            return {"local_fallback": True, "text": text}

        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self._webhook, json={"text": text})
            resp.raise_for_status()
        return {"sent": True}
