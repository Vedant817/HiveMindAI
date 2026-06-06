from __future__ import annotations

from pathlib import Path
import tempfile

from agents.meeting_agent import MeetingAgent

try:
    from fastapi import APIRouter, File, UploadFile
except Exception:  # pragma: no cover
    APIRouter = File = UploadFile = None

meeting_agent = MeetingAgent()

if APIRouter:
    router = APIRouter()

    @router.post("/ingest/meeting")
    async def ingest_meeting(file: UploadFile = File(...)):
        suffix = Path(file.filename or "meeting.txt").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            return await meeting_agent.process_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    @router.post("/ingest/transcript")
    async def ingest_transcript(payload: dict):
        return await meeting_agent.process_transcript(payload.get("transcript", ""))
else:
    router = None

