from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
import uuid

from memory.cosmos_client import CosmosClient
from shared.config import config_report
from shared.llm_client import LLMClient
from shared.redis_client import RedisClient


async def verify_config(live: bool = False) -> dict[str, Any]:
    """Verify configured dependencies without side effects unless live=True."""
    report = config_report()
    checks: dict[str, dict[str, Any]] = {}

    if report["llm_configured"]:
        checks["llm"] = await _check_llm(live=live)
    elif report["llm_provider"] == "none" and report["local_fallbacks_enabled"]:
        checks["llm"] = {"ok": True, "reason": "Using deterministic local fallback instead of a model provider."}
    else:
        checks["llm"] = {"ok": False, "reason": "No LLM provider is configured"}

    redis_configured = any(
        report["integrations"].get(name, {}).get("configured") for name in ("Upstash Redis", "Redis")
    )
    if redis_configured:
        checks["redis"] = await _check_redis(live=live)

    store_configured = any(
        report["integrations"].get(name, {}).get("configured") for name in ("MongoDB Atlas", "Cosmos DB")
    )
    if store_configured:
        checks["document_store"] = await _check_document_store(live=live)

    side_effect_integrations = [
        name
        for name in ("Jira", "Slack", "Teams", "Azure Communication Services", "Azure Service Bus")
        if name in report["integrations"]
    ]
    for name in side_effect_integrations:
        configured = report["integrations"][name]["configured"]
        checks[name] = {
            "ok": configured,
            "reason": "Configured; live verification is skipped to avoid creating tickets/messages."
            if configured
            else "Missing required configuration.",
        }

    verified_ready = all(check.get("ok") for check in checks.values()) if checks else False
    return {"configured": report, "live": live, "verified_ready": verified_ready, "checks": checks}


async def _check_llm(live: bool) -> dict[str, Any]:
    if not live:
        return {"ok": True, "reason": "Provider is configured; set live=true to perform a model call."}
    text = await asyncio.wait_for(LLMClient().chat_text("Reply with OK.", "OK", temperature=0), timeout=30)
    return {"ok": bool(text and text.strip()), "reason": "Model call completed" if text else "Model returned no text"}


async def _check_redis(live: bool) -> dict[str, Any]:
    if not live:
        return {"ok": True, "reason": "Redis URL is configured; set live=true to ping via set/get."}
    client = RedisClient()
    key = f"config-check:{uuid.uuid4()}"
    value = {"timestamp": datetime.now(timezone.utc).isoformat()}
    await asyncio.wait_for(client.set(key, value, ttl=60), timeout=15)
    restored = await asyncio.wait_for(client.get(key), timeout=15)
    await client.delete(key)
    return {"ok": restored == value, "reason": "Redis set/get completed"}


async def _check_document_store(live: bool) -> dict[str, Any]:
    if not live:
        return {"ok": True, "reason": "Document store is configured; set live=true to upsert/read a check record."}
    store = CosmosClient()
    item = {"id": f"config-check:{uuid.uuid4()}", "timestamp": datetime.now(timezone.utc).isoformat()}
    await asyncio.wait_for(store.upsert("ConfigChecks", item), timeout=20)
    restored = await asyncio.wait_for(store.get("ConfigChecks", item["id"]), timeout=20)
    return {"ok": bool(restored and restored.get("id") == item["id"]), "reason": "Document store upsert/read completed"}
