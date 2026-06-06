from __future__ import annotations

from hitl.confidence_gate import ConfidenceGate

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - import fallback for environments before install
    APIRouter = None

gate = ConfidenceGate()

if APIRouter:
    router = APIRouter()

    @router.post("/approval/{approval_id}/approve")
    async def approve(approval_id: str):
        return await gate.resolve(approval_id, approved=True)

    @router.post("/approval/{approval_id}/reject")
    async def reject(approval_id: str):
        return await gate.resolve(approval_id, approved=False)
else:
    router = None

