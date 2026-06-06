from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Literal
import uuid

MessageType = Literal[
    "plan",
    "execute",
    "validate",
    "complete",
    "escalate",
    "ticket",
    "debate",
    "reflect",
]
MessageStatus = Literal["pending", "running", "done", "failed", "cancelled"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AgentMessage:
    type: MessageType
    payload: dict[str, Any]
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    confidence: float = 1.0
    assigned_to: str | None = None
    status: MessageStatus = "pending"
    parent_task_id: str | None = None
    jira_ticket_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.confidence = float(self.confidence)
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        if self.metadata is None:
            self.metadata = {}

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), separators=(",", ":"))

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "AgentMessage":
        values = dict(data)
        created_at = values.get("created_at")
        if isinstance(created_at, str):
            values["created_at"] = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return cls(**values)

    @classmethod
    def model_validate_json(cls, raw: str | bytes) -> "AgentMessage":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.model_validate(json.loads(raw))


def message_from_task(
    task: dict[str, Any],
    message_type: MessageType = "execute",
    status: MessageStatus = "pending",
) -> AgentMessage:
    return AgentMessage(
        type=message_type,
        payload=task,
        assigned_to=task.get("assigned_to"),
        status=status,
        parent_task_id=task.get("parent_task_id"),
        jira_ticket_id=task.get("jira_ticket_id"),
        metadata={k: v for k, v in task.items() if k.startswith("_")},
    )

