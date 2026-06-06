from __future__ import annotations

import asyncio
from pathlib import Path
import json
import os
from typing import Any
import uuid
from shared.config import is_real_value, require_or_fallback


class CosmosClient:
    """Container-oriented document store with MongoDB, Cosmos DB, or local JSON fallback."""

    def __init__(self) -> None:
        self._endpoint = os.getenv("COSMOS_ENDPOINT")
        self._key = os.getenv("COSMOS_KEY")
        self._database_name = os.getenv("COSMOS_DATABASE", "swarm")
        self._mongo_uri = os.getenv("MONGODB_URI")
        self._mongo_database_name = os.getenv("MONGODB_DATABASE", "hivemindai")
        self._local_dir = Path(os.getenv("LOCAL_STATE_DIR", "local_state"))
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._database = None
        self._mongo_database = None

    def _container_path(self, container: str) -> Path:
        return self._local_dir / f"{container}.json"

    async def upsert(self, container: str, item: dict[str, Any]) -> dict[str, Any]:
        item = dict(item)
        if not item.get("id"):
            item["id"] = item.get("entry_id") or item.get("task_id") or item.get("dag_id") or str(uuid.uuid4())
        mongo = self._mongo_collection(container)
        if mongo is not None:
            await asyncio.to_thread(mongo.replace_one, {"id": item["id"]}, item, upsert=True)
            return item
        cosmos = self._cosmos_container(container)
        if cosmos is not None:
            return await asyncio.to_thread(cosmos.upsert_item, item)
        items = await self._read_all(container)
        items = [row for row in items if row.get("id") != item["id"]]
        items.append(item)
        path = self._container_path(container)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        temp_path.replace(path)
        return item

    async def get(self, container: str, item_id: str) -> dict[str, Any] | None:
        mongo = self._mongo_collection(container)
        if mongo is not None:
            row = await asyncio.to_thread(mongo.find_one, {"id": item_id}, {"_id": False})
            return dict(row) if row else None
        cosmos = self._cosmos_container(container)
        if cosmos is not None:
            try:
                return await asyncio.to_thread(cosmos.read_item, item=item_id, partition_key=item_id)
            except Exception:
                return None
        for item in await self._read_all(container):
            if item.get("id") == item_id:
                return item
        return None

    async def query(
        self,
        container: str,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        mongo = self._mongo_collection(container)
        if mongo is not None:
            def _mongo_query() -> list[dict[str, Any]]:
                cursor = mongo.find({}, {"_id": False})
                if where and "ORDER BY" in where.upper() and "TIMESTAMP" in where.upper():
                    cursor = cursor.sort("timestamp", -1)
                if limit:
                    cursor = cursor.limit(limit)
                return [dict(row) for row in cursor]

            return await asyncio.to_thread(_mongo_query)
        cosmos = self._cosmos_container(container)
        if cosmos is not None:
            query = "SELECT * FROM c"
            if where:
                query = f"{query} {where}"
            rows = await asyncio.to_thread(lambda: list(cosmos.query_items(query=query, enable_cross_partition_query=True)))
            return rows[:limit] if limit else rows
        rows = await self._read_all(container)
        if where and "ORDER BY" in where.upper() and "TIMESTAMP" in where.upper():
            rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
        return rows[:limit] if limit else rows

    async def _read_all(self, container: str) -> list[dict[str, Any]]:
        path = self._container_path(container)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            require_or_fallback("Local document store", f"{path} contains invalid JSON")
            return []
        return data if isinstance(data, list) else []

    def _mongo_collection(self, container: str):
        if not is_real_value(self._mongo_uri):
            return None
        try:
            from pymongo import MongoClient

            if self._mongo_database is None:
                client = MongoClient(self._mongo_uri, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")
                self._mongo_database = client[self._mongo_database_name]
            return self._mongo_database[container]
        except Exception:
            require_or_fallback("MongoDB Atlas", "connection failed")
            return None

    def _cosmos_container(self, container: str):
        if not is_real_value(self._endpoint) or not is_real_value(self._key):
            require_or_fallback("Cosmos DB", "set COSMOS_ENDPOINT and COSMOS_KEY")
            return None
        try:
            from azure.cosmos import CosmosClient as AzureCosmosClient
            from azure.cosmos import PartitionKey

            if self._database is None:
                client = AzureCosmosClient(self._endpoint, credential=self._key)
                self._database = client.create_database_if_not_exists(self._database_name)
            return self._database.create_container_if_not_exists(
                id=container,
                partition_key=PartitionKey(path="/id"),
            )
        except Exception:
            require_or_fallback("Cosmos DB", "connection failed")
            return None
