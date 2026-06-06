from __future__ import annotations

import base64
import os
from typing import Any

from shared.config import is_real_value, require_or_fallback


class AzureDevOpsClient:
    """Azure DevOps work item client."""

    def __init__(self) -> None:
        self._org_url = os.getenv("AZURE_DEVOPS_ORG_URL", "").rstrip("/")
        self._project = os.getenv("AZURE_DEVOPS_PROJECT")
        self._pat = os.getenv("AZURE_DEVOPS_PAT")

    @property
    def configured(self) -> bool:
        return all(is_real_value(value) for value in (self._org_url, self._project, self._pat))

    async def update_work_item(self, work_item_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            require_or_fallback(
                "Azure DevOps",
                "set AZURE_DEVOPS_ORG_URL, AZURE_DEVOPS_PROJECT, and AZURE_DEVOPS_PAT",
            )
            return {"work_item_id": work_item_id, "fields": fields, "local_fallback": True}

        import httpx

        token = base64.b64encode(f":{self._pat}".encode("utf-8")).decode("utf-8")
        patch = [{"op": "add", "path": f"/fields/{key}", "value": value} for key, value in fields.items()]
        url = (
            f"{self._org_url}/{self._project}/_apis/wit/workitems/{work_item_id}"
            "?api-version=7.1"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                url,
                json=patch,
                headers={
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/json-patch+json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()
