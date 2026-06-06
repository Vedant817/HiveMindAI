from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agents.debate_agent import DebateOrchestrator
from agents.meeting_agent import MeetingAgent
from agents.summary_agent import SummaryAgent
from metrics.swarm_metrics import project_health
from orchestrator.swarm_runtime import SwarmRuntime
from shared.config import config_report, demo_defaults


def demo_mode(report: dict) -> str:
    if report.get("app_stack") == "azure" and report.get("production_ready"):
        return "production"
    if report.get("app_stack") == "free" and report.get("free_stack_ready"):
        return "free-cloud"
    return "local-demo"


async def run_pitch_demo(payload: dict | None = None) -> dict:
    payload = payload or {}
    defaults = demo_defaults()
    goal = payload.get("goal") or defaults["goal"]
    transcript = payload.get("transcript") or defaults["transcript"]
    question = payload.get("question") or defaults["question"]

    runtime = SwarmRuntime()
    meeting = MeetingAgent()
    debate = DebateOrchestrator()
    summary = SummaryAgent()

    swarm_result = await runtime.run_goal(goal)
    meeting_result = await meeting.process_transcript(transcript)
    debate_result = await debate.run_debate(question)
    task_rows = swarm_result["dag"]["tasks"]
    executive_summary = await summary.generate(task_rows)
    return {
        "mode": demo_mode(config_report()),
        "config": config_report(),
        "goal": goal,
        "meeting": meeting_result,
        "swarm": swarm_result,
        "debate": debate_result,
        "summary": executive_summary,
        "metrics": {
            **project_health(task_rows),
            "tickets_created": meeting_result["count"],
            "agents_involved": sorted({task["assigned_to"] for task in task_rows}),
            "human_gate_threshold": defaults["human_gate_threshold"],
        },
        "story": defaults["story"],
    }


async def run_pitch_demo_stream(payload: dict | None = None) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def publish(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            payload_data = payload or {}
            defaults = demo_defaults()
            goal = payload_data.get("goal") or defaults["goal"]
            transcript = payload_data.get("transcript") or defaults["transcript"]
            question = payload_data.get("question") or defaults["question"]

            runtime = SwarmRuntime()
            meeting = MeetingAgent()
            debate = DebateOrchestrator()
            summary = SummaryAgent()

            await publish({"type": "stage", "phase": "config", "status": "complete", "message": "Configuration loaded.", "config": config_report()})
            await publish({"type": "stage", "phase": "swarm", "status": "running", "message": "Starting PM, executor, validator, memory, and reflection agents."})
            swarm_result = await runtime.run_goal(goal, progress=lambda event: publish({"type": "swarm", **event}))

            await publish({"type": "stage", "phase": "meeting", "status": "running", "message": "Meeting agent is extracting Jira-ready work items."})
            meeting_result = await meeting.process_transcript(transcript)
            await publish({"type": "stage", "phase": "meeting", "status": "complete", "message": f"Meeting agent created {meeting_result['count']} local or Jira tickets.", "tickets": meeting_result["tickets"]})

            await publish({"type": "stage", "phase": "debate", "status": "running", "message": "Specialist agents are debating the architecture decision."})
            debate_result = await debate.run_debate(question)
            await publish({"type": "stage", "phase": "debate", "status": "complete", "message": f"{debate_result['winner']['winner']} won the debate.", "debate": debate_result})

            await publish({"type": "stage", "phase": "summary", "status": "running", "message": "Summary agent is preparing the manager view."})
            task_rows = swarm_result["dag"]["tasks"]
            executive_summary = await summary.generate(task_rows)
            result = {
                "mode": demo_mode(config_report()),
                "config": config_report(),
                "goal": goal,
                "meeting": meeting_result,
                "swarm": swarm_result,
                "debate": debate_result,
                "summary": executive_summary,
                "metrics": {
                    **project_health(task_rows),
                    "tickets_created": meeting_result["count"],
                    "agents_involved": sorted({task["assigned_to"] for task in task_rows}),
                    "human_gate_threshold": defaults["human_gate_threshold"],
                },
                "story": defaults["story"],
            }
            await publish({"type": "complete", "phase": "summary", "status": "complete", "message": "Demo run complete.", "data": result})
        except Exception as exc:
            await publish({"type": "error", "phase": "error", "status": "failed", "message": str(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        await task
