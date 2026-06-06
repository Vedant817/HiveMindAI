from __future__ import annotations

from agents.debate_agent import DebateOrchestrator
from agents.knowledge_agent import KnowledgeAgent
from agents.summary_agent import SummaryAgent
from api import approval_webhook, ingest
from api.demo import run_pitch_demo, run_pitch_demo_stream
from memory.cosmos_client import CosmosClient
from orchestrator.swarm_runtime import SwarmRuntime
from shared.config import config_report, demo_defaults

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import StreamingResponse
except Exception:  # pragma: no cover
    APIRouter = None

if APIRouter:
    router = APIRouter()
    runtime = SwarmRuntime()
    knowledge = KnowledgeAgent()
    debate = DebateOrchestrator()
    summary = SummaryAgent()
    store = CosmosClient()

    if ingest.router:
        router.include_router(ingest.router)
    if approval_webhook.router:
        router.include_router(approval_webhook.router)

    @router.get("/health")
    async def health():
        return {"status": "ok", "service": "HiveMindAI"}

    @router.get("/config/check")
    async def check_config():
        return config_report()

    @router.get("/demo/defaults")
    async def get_demo_defaults():
        return demo_defaults()

    @router.post("/swarm/run")
    async def run_goal(payload: dict):
        goal = str(payload.get("goal", "")).strip()
        if not goal:
            raise HTTPException(status_code=400, detail="goal is required")
        return await runtime.run_goal(goal)

    @router.post("/demo/run")
    async def run_demo(payload: dict):
        return await run_pitch_demo(payload)

    @router.post("/demo/run/stream")
    async def run_demo_stream(payload: dict):
        return StreamingResponse(run_pitch_demo_stream(payload), media_type="text/event-stream")

    @router.post("/knowledge")
    async def remember(payload: dict):
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not title or not content:
            raise HTTPException(status_code=400, detail="title and content are required")
        return await knowledge.remember(
            title=title,
            content=content,
            kind=payload.get("kind", "decision"),
            tags=payload.get("tags", []),
            source=payload.get("source"),
        )

    @router.get("/knowledge/search")
    async def search_knowledge(q: str):
        return await knowledge.answer(q)

    @router.post("/debate")
    async def run_debate(payload: dict):
        question = str(payload.get("question", "")).strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        return await debate.run_debate(question)

    @router.get("/summary")
    async def project_summary():
        tasks = await store.query("Tasks", limit=100)
        if not tasks:
            dags = await store.query("TaskDAGs", limit=20)
            tasks = [task for dag in dags for task in dag.get("tasks", [])]
        return {"summary": await summary.generate(tasks)}
else:
    router = None
