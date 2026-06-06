from __future__ import annotations

import asyncio
import os

from agents.summary_agent import SummaryAgent
from memory.cosmos_client import CosmosClient
from shared.config import is_real_value, require_or_fallback


async def _run() -> dict | None:
    cosmos = CosmosClient()
    tasks = await cosmos.query("Tasks", limit=1000)
    if not tasks:
        return None
    summary_text = await SummaryAgent().generate(tasks)

    conn = os.getenv("AZURE_COMMUNICATION_CONNECTION_STRING")
    sender = os.getenv("SENDER_EMAIL")
    recipient = os.getenv("STAKEHOLDER_EMAIL")
    if not all(is_real_value(value) for value in (conn, sender, recipient)):
        require_or_fallback(
            "Azure Communication Services",
            "set AZURE_COMMUNICATION_CONNECTION_STRING, SENDER_EMAIL, and STAKEHOLDER_EMAIL",
        )
        return {"local_fallback": True, "summary": summary_text}

    from azure.communication.email import EmailClient

    email_client = EmailClient.from_connection_string(conn)
    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": recipient}]},
        "content": {
            "subject": f"Swarm Daily Report - {len(tasks)} tasks processed",
            "plainText": summary_text,
        },
    }
    poller = email_client.begin_send(message)
    poller.result()
    return {"sent": True}


def main(timer=None) -> None:
    asyncio.run(_run())
