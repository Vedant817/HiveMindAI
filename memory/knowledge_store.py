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

    async def related_entries(self, entry_id: str, depth: int = 1) -> dict:
        depth = max(1, min(depth, 3))
        entries = {row.get("id"): row for row in await self.cosmos.query("Knowledge", limit=1000) if row.get("id")}
        relations = await self.cosmos.query("KnowledgeRelations", limit=2000)
        frontier = {entry_id}
        visited = {entry_id}
        selected_relations: list[dict] = []
        for _ in range(depth):
            next_frontier: set[str] = set()
            for relation in relations:
                source = relation.get("source_id")
                target = relation.get("target_id")
                if source in frontier or target in frontier:
                    selected_relations.append(relation)
                    for node_id in (source, target):
                        if node_id and node_id not in visited:
                            visited.add(node_id)
                            next_frontier.add(node_id)
            frontier = next_frontier
            if not frontier:
                break
        return {
            "root": entries.get(entry_id),
            "nodes": [entries[node_id] for node_id in visited if node_id in entries],
            "relations": selected_relations,
        }

    async def graph_context(self, query: str, limit: int = 5) -> dict:
        matches = await self.search_entries(query, limit=limit)
        related = [await self.related_entries(str(match.get("id")), depth=1) for match in matches if match.get("id")]
        return {"matches": matches, "related": related}

    async def search_entries(self, query: str, limit: int = 5) -> list[dict]:
        matches = await self.search.search(query, limit=limit)
        if matches:
            return matches

        # Local fallback search indexes documents from the durable store so memory survives restarts.
        stored = await self.cosmos.query("Knowledge", limit=1000)
        for row in stored:
            await self.search.index(row)
        return await self.search.search(query, limit=limit)

