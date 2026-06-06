from __future__ import annotations

from pathlib import Path
import tempfile

from agents.meeting_agent import MeetingAgent
from api.security import require_api_key
from orchestrator.swarm_runtime import SwarmRuntime
from shared.validation import PayloadValidationError, bounded_text

try:
    from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
except Exception:  # pragma: no cover
    APIRouter = File = UploadFile = None

meeting_agent = MeetingAgent()
runtime = SwarmRuntime()

if APIRouter:
    router = APIRouter()

    @router.post("/ingest/meeting", dependencies=[Depends(require_api_key)])
    async def ingest_meeting(file: UploadFile = File(...), execute: bool = False):
        suffix = Path(file.filename or "meeting.txt").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            result = await meeting_agent.process_file(tmp_path)
            if execute:
                result["executions"] = await runtime.process_queued_tickets(max_messages=result["count"])
            return result
        finally:
            tmp_path.unlink(missing_ok=True)

    @router.post("/ingest/transcript", dependencies=[Depends(require_api_key)])
    async def ingest_transcript(payload: dict):
        try:
            transcript = bounded_text(payload, "transcript", required=False, max_length=24000)
        except PayloadValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await meeting_agent.process_transcript(transcript)
        if bool(payload.get("execute")):
            result["executions"] = await runtime.process_queued_tickets(max_messages=result["count"])
        return result
else:
    router = None

