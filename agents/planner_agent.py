from __future__ import annotations

import re

from schemas.task_dag import TaskDAG, TaskNode
from shared.config import planner_default_confidence, require_or_fallback
from shared.llm_client import LLMClient


PLANNER_PROMPT = """Break the user's goal into an execution DAG for an enterprise agent swarm.
Return only JSON with this shape:
[
  {
    "title": "short task title",
    "description": "clear acceptance criteria and work details",
    "assigned_to": "Planner|Executor|Validator|SecurityAgent|KnowledgeAgent|MeetingAgent|CommsAgent",
    "depends_on": ["title of dependency task"],
    "confidence": 0.0
  }
]
Include dependencies by exact title. Do not include markdown fences."""


class PlannerAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def plan_async(self, goal: str) -> TaskDAG:
        normalized = goal.strip()
        if not normalized:
            raise ValueError("goal is required")
        rows = await self.llm.chat_json(PLANNER_PROMPT, normalized)
        if rows is None:
            return self.plan(normalized)
        try:
            return self._dag_from_rows(normalized, rows)
        except (KeyError, TypeError, ValueError) as exc:
            require_or_fallback("Planner LLM", f"invalid task DAG JSON: {exc}")
            return self.plan(normalized)

    def plan(self, goal: str) -> TaskDAG:
        """Build a local execution DAG from a high-level goal."""
        normalized = goal.strip()
        if not normalized:
            raise ValueError("goal is required")

        themes = self._extract_themes(normalized)
        goal_lower = normalized.lower()
        tasks: list[TaskNode] = []

        research = TaskNode(
            title=f"Clarify requirements for {themes['object']}",
            description=f"Identify acceptance criteria, constraints, and risks for: {normalized}",
            assigned_to="Planner",
        )
        tasks.append(research)
        implementation_dependencies = [research.task_id]
        implementation_nodes: list[TaskNode] = []

        if any(word in goal_lower for word in ("meeting", "transcript", "jira", "ticket")):
            implementation_nodes.append(
                TaskNode(
                    title=f"Extract execution tickets for {themes['object']}",
                    description="Convert the source discussion into prioritized, Jira-ready work items with owners and acceptance criteria.",
                    assigned_to="MeetingAgent",
                    depends_on=implementation_dependencies.copy(),
                )
            )

        if any(word in goal_lower for word in ("api", "endpoint", "webhook", "service")):
            implementation_nodes.append(
                TaskNode(
                    title=f"Implement API contract for {themes['object']}",
                    description="Produce endpoint behavior, request/response contract, integration notes, and operational checks.",
                    assigned_to="Executor",
                    depends_on=implementation_dependencies.copy(),
                )
            )

        if any(word in goal_lower for word in ("dashboard", "report", "summary", "manager")):
            implementation_nodes.append(
                TaskNode(
                    title=f"Implement dashboard and reporting view for {themes['object']}",
                    description="Create a usable project health view with task status, tickets, confidence, risks, and manager summary.",
                    assigned_to="Executor",
                    depends_on=implementation_dependencies.copy(),
                )
            )

        if any(word in goal_lower for word in ("approval", "human", "risk", "security", "risky")):
            implementation_nodes.append(
                TaskNode(
                    title=f"Configure approval and risk controls for {themes['object']}",
                    description="Define confidence thresholds, approval payloads, audit trail, and safe rejection behavior.",
                    assigned_to="SecurityAgent",
                    depends_on=implementation_dependencies.copy(),
                    confidence=0.88,
                )
            )

        if any(word in goal_lower for word in ("memory", "knowledge", "decision", "context")):
            implementation_nodes.append(
                TaskNode(
                    title=f"Update organizational memory for {themes['object']}",
                    description="Store decisions, relations, reusable context, and lookup tags for future swarm runs.",
                    assigned_to="KnowledgeAgent",
                    depends_on=implementation_dependencies.copy(),
                )
            )

        if not implementation_nodes:
            implementation_nodes.append(
                TaskNode(
                    title=f"Implement {themes['object']}",
                    description=f"Produce the working deliverable for: {normalized}",
                    assigned_to="Executor",
                    depends_on=implementation_dependencies.copy(),
                )
            )

        tasks.extend(implementation_nodes)
        validation_dependencies = [node.task_id for node in implementation_nodes]

        if any(word in goal_lower for word in ("friday", "today", "tomorrow", "deadline", "sprint")):
            rollout = TaskNode(
                title=f"Prepare delivery status for {themes['object']}",
                description="Summarize delivery readiness, risks, ETA, and stakeholder communications for the deadline.",
                assigned_to="CommsAgent",
                depends_on=validation_dependencies.copy(),
            )
            tasks.append(rollout)
            validation_dependencies = [rollout.task_id]

        validation = TaskNode(
            title=f"Validate {themes['object']}",
            description="Check completeness, correctness, security, generated artifacts, and operational readiness.",
            assigned_to="Validator",
            depends_on=validation_dependencies,
        )
        tasks.append(validation)
        dag = TaskDAG(goal=normalized, tasks=tasks)
        dag.validate()
        return dag

    def _extract_themes(self, goal: str) -> dict[str, str]:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", goal)
        meaningful = [w for w in words if len(w) > 3]
        obj = " ".join(meaningful[:5]) if meaningful else "requested work"
        return {"object": obj}

    def _dag_from_rows(self, goal: str, rows: list[dict]) -> TaskDAG:
        if not isinstance(rows, list) or not rows:
            raise ValueError("planner response must be a non-empty list")

        nodes: list[TaskNode] = []
        title_to_id: dict[str, str] = {}
        pending_dependencies: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("each task must be an object")
            title = str(row.get("title", "")).strip()
            description = str(row.get("description", "")).strip()
            if not title or not description:
                raise ValueError("each task requires title and description")
            if title in title_to_id:
                raise ValueError(f"duplicate task title: {title}")
            node = TaskNode(
                title=title,
                description=description,
                assigned_to=str(row.get("assigned_to") or "Executor"),
                confidence=max(0.0, min(1.0, float(row.get("confidence", planner_default_confidence())))),
            )
            nodes.append(node)
            title_to_id[node.title] = node.task_id
            pending_dependencies[node.task_id] = [str(dep).strip() for dep in row.get("depends_on", []) if str(dep).strip()]

        for node in nodes:
            unknown = [dep_title for dep_title in pending_dependencies[node.task_id] if dep_title not in title_to_id]
            if unknown:
                raise ValueError(f"task {node.title} references unknown dependencies: {unknown}")
            node.depends_on = [title_to_id[dep_title] for dep_title in pending_dependencies[node.task_id]]
        dag = TaskDAG(goal=goal, tasks=nodes)
        dag.validate()
        return dag
