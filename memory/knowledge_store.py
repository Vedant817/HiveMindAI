from __future__ import annotations

from schemas.knowledge_entry import KnowledgeEntry, KnowledgeRelation
from memory.cosmos_client import CosmosClient
from memory.search_client import SearchClient


class KnowledgeStore:
    def __init__(
        self,
        cosmos: CosmosClient | None = None,
        search: SearchClient | None = None,
    ) -> None:
        self.cosmos = cosmos or CosmosClient()
        self.search = search or SearchClient()

    async def add_entry(self, entry: KnowledgeEntry) -> dict:
        row = entry.to_dict()
        row["id"] = entry.entry_id
        saved = await self.cosmos.upsert("Knowledge", row)
        await self.search.index(saved)
        return saved

    async def add_relation(self, relation: KnowledgeRelation) -> dict:
        row = relation.to_dict()
        row["id"] = f"{relation.source_id}:{relation.relation}:{relation.target_id}"
        return await self.cosmos.upsert("KnowledgeRelations", row)

    async def search_entries(self, query: str, limit: int = 5) -> list[dict]:
        matches = await self.search.search(query, limit=limit)
        if matches:
            return matches

        # Local fallback search indexes documents from the durable store so memory survives restarts.
        stored = await self.cosmos.query("Knowledge", limit=1000)
        for row in stored:
            await self.search.index(row)
        return await self.search.search(query, limit=limit)

