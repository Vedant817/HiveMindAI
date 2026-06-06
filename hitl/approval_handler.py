from __future__ import annotations

from hitl.confidence_gate import ConfidenceGate


class ApprovalHandler:
    def __init__(self, gate: ConfidenceGate | None = None) -> None:
        self.gate = gate or ConfidenceGate()

    async def approve(self, approval_id: str) -> dict:
        return await self.gate.resolve(approval_id, approved=True)

    async def reject(self, approval_id: str) -> dict:
        return await self.gate.resolve(approval_id, approved=False)

