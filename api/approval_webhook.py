from __future__ import annotations

from hitl.confidence_gate import ConfidenceGate
from orchestrator.swarm_runtime import SwarmRuntime

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - import fallback for environments before install
    APIRouter = None

gate = ConfidenceGate()
runtime = SwarmRuntime(gate=gate)

if APIRouter:
    router = APIRouter()

    @router.post("/approval/{approval_id}/approve")
    async def approve(approval_id: str, token: str | None = None):
        return await runtime.resume_approval(approval_id, approved=True, token=token)

    @router.post("/approval/{approval_id}/reject")
    async def reject(approval_id: str, token: str | None = None):
        return await runtime.resume_approval(approval_id, approved=False, token=token)
else:
    router = None

