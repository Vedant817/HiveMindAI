from __future__ import annotations

import asyncio
import math
import os
import re
from typing import Any
from shared.config import is_real_value, require_or_fallback


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class SearchClient:
    """Vector-search facade with deterministic keyword scoring fallback."""

    def __init__(self) -> None:
        self._endpoint = os.getenv("SEARCH_ENDPOINT")
        self._key = os.getenv("SEARCH_KEY")
        self._index = os.getenv("SEARCH_INDEX", "knowledge")
        self._documents: list[dict[str, Any]] = []

    async def index(self, document: dict[str, Any]) -> None:
        azure_client = self._azure_client()
        if azure_client is not None:
            try:
                await asyncio.to_thread(azure_client.merge_or_upload_documents, [document])
                return
            except Exception as exc:
                require_or_fallback("Azure AI Search", f"indexing failed: {exc}")
        self._documents = [row for row in self._documents if row.get("id") != document.get("id")]
        self._documents.append(dict(document))

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        azure_client = self._azure_client()
        if azure_client is not None:
            try:
                return await asyncio.to_thread(lambda: [dict(row) for row in azure_client.search(query, top=limit)])
            except Exception as exc:
                require_or_fallback("Azure AI Search", f"search failed: {exc}")
        return self._keyword_search(self._documents, query, limit)

    def _keyword_search(self, documents: list[dict[str, Any]], query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for document in documents:
            text = " ".join(str(document.get(key, "")) for key in ("title", "content", "tags"))
            doc_tokens = _tokens(text)
            if not doc_tokens:
                continue
            overlap = len(query_tokens & doc_tokens)
            score = overlap / math.sqrt(len(doc_tokens))
            if score > 0:
                row = dict(document)
                row["@search.score"] = score
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:limit]]

    def _azure_client(self):
        if not is_real_value(self._endpoint) or not is_real_value(self._key):
            require_or_fallback("Azure AI Search", "set SEARCH_ENDPOINT and SEARCH_KEY")
            return None
        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents import SearchClient as AzureSearchClient

            return AzureSearchClient(
                endpoint=self._endpoint,
                index_name=self._index,
                credential=AzureKeyCredential(self._key),
            )
        except Exception:
            require_or_fallback("Azure AI Search", "client initialization failed")
            return None
