from __future__ import annotations

from memory.knowledge_store import KnowledgeStore
from schemas.knowledge_entry import KnowledgeEntry, KnowledgeRelation


class KnowledgeAgent:
    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or KnowledgeStore()

    async def remember(
        self,
        title: str,
        content: str,
        kind: str = "decision",
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> dict:
        entry = KnowledgeEntry(
            title=title,
            content=content,
            kind=kind,  # type: ignore[arg-type]
            tags=tags or [],
            source=source,
        )
        return await self.store.add_entry(entry)

    async def connect(self, source_id: str, target_id: str, relation: str) -> dict:
        return await self.store.add_relation(KnowledgeRelation(source_id, target_id, relation))

    async def related(self, entry_id: str, depth: int = 1) -> dict:
        return await self.store.related_entries(entry_id, depth=depth)

    async def answer(self, question: str) -> dict:
        graph = await self.store.graph_context(question)
        matches = graph["matches"]
        if not matches:
            return {"answer": "No matching organizational memory found.", "sources": [], "graph": graph}
        top = matches[0]
        return {
            "answer": top.get("content", ""),
            "sources": [{"id": row.get("id"), "title": row.get("title")} for row in matches],
            "graph": graph,
        }

