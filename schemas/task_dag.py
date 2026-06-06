from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import uuid

TaskNodeStatus = Literal["pending", "running", "done", "failed", "blocked"]


@dataclass(slots=True)
class TaskNode:
    title: str
    description: str
    assigned_to: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    depends_on: list[str] = field(default_factory=list)
    status: TaskNodeStatus = "pending"
    confidence: float = 1.0
    jira_ticket_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskDAG:
    goal: str
    tasks: list[TaskNode]
    dag_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def validate(self) -> None:
        ids = {task.task_id for task in self.tasks}
        if len(ids) != len(self.tasks):
            raise ValueError("task DAG contains duplicate task ids")
        for task in self.tasks:
            missing = [dep for dep in task.depends_on if dep not in ids]
            if missing:
                raise ValueError(f"task {task.task_id} has unknown dependencies: {missing}")
        self._assert_acyclic()

    def ready_tasks(self) -> list[TaskNode]:
        done = {task.task_id for task in self.tasks if task.status == "done"}
        return [
            task
            for task in self.tasks
            if task.status == "pending" and all(dep in done for dep in task.depends_on)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dag_id": self.dag_id,
            "goal": self.goal,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskDAG":
        tasks = [TaskNode(**task) for task in data.get("tasks", [])]
        return cls(goal=data["goal"], tasks=tasks, dag_id=data.get("dag_id") or str(uuid.uuid4()))

    def _assert_acyclic(self) -> None:
        graph = {task.task_id: task.depends_on for task in self.tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise ValueError("task DAG contains a cycle")
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)

