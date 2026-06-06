from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agents.comms_agent import CommsAgent
from agents.executor_agent import ExecutorAgent
from agents.pm_agent import PMAgent
from agents.reflection_agent import ReflectionAgent
from agents.validator_agent import ValidatorAgent
from hitl.confidence_gate import ConfidenceGate
from memory.cosmos_client import CosmosClient
from schemas.task_dag import TaskDAG, TaskNode
from shared.message_schema import AgentMessage

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


class SwarmRuntime:
    def __init__(
        self,
        pm: PMAgent | None = None,
        executor: ExecutorAgent | None = None,
        validator: ValidatorAgent | None = None,
        gate: ConfidenceGate | None = None,
        comms: CommsAgent | None = None,
        reflection: ReflectionAgent | None = None,
        store: CosmosClient | None = None,
    ) -> None:
        self.pm = pm or PMAgent()
        self.executor = executor or ExecutorAgent()
        self.validator = validator or ValidatorAgent()
        self.gate = gate or ConfidenceGate()
        self.comms = comms or CommsAgent()
        self.reflection = reflection or ReflectionAgent()
        self.store = store or CosmosClient()

    async def run_goal(self, goal: str, progress: ProgressCallback | None = None) -> dict:
        await _publish(progress, {"phase": "planning", "status": "running", "message": "PM agent is creating the task DAG."})
        dag = await self.pm.create_plan(goal)
        await _publish(
            progress,
            {
                "phase": "planning",
                "status": "complete",
                "message": f"PM agent created {len(dag.tasks)} dependent tasks.",
                "tasks": [task.to_dict() for task in dag.tasks],
            },
        )
        history: list[dict] = []
        await self._persist_tasks(dag)

        while True:
            ready = dag.ready_tasks()
            if not ready:
                await self._block_pending_tasks(dag, progress)
                break
            for task in ready:
                result = await self._run_task(task, progress)
                task.status = "done" if result["gate"] == "auto_execute" and result["validated"].status == "done" else "blocked"
                await self._persist_task(dag.dag_id, task)
                await _publish(
                    progress,
                    {
                        "phase": "gate",
                        "status": task.status,
                        "message": f"{task.assigned_to} task {task.status}: {task.title}",
                        "task": task.to_dict(),
                        "gate": result["gate"],
                    },
                )
                history.extend(
                    [
                        result["input"].model_dump(),
                        result["executed"].model_dump(),
                        result["validated"].model_dump(),
                    ]
                )

        await _publish(progress, {"phase": "memory", "status": "running", "message": "Persisting DAG and execution history."})
        await self.store.upsert("TaskDAGs", dag.to_dict())
        await self._persist_tasks(dag)
        await _publish(progress, {"phase": "reflection", "status": "running", "message": "Reflection agent is reviewing the run."})
        reflection = await self.reflection.reflect(history, dag.dag_id)
        await _publish(progress, {"phase": "reflection", "status": "complete", "message": "Reflection agent produced improvement notes."})
        return {
            "dag": dag.to_dict(),
            "history": history,
            "reflection": reflection,
            "complete": all(task.status == "done" for task in dag.tasks),
        }

    async def process_message(self, msg: AgentMessage) -> dict:
        if msg.type == "ticket":
            goal = f"{msg.payload.get('title')}: {msg.payload.get('description', '')}"
            return await self.run_goal(goal)
        result = await self.executor.execute(msg)
        validated = await self.validator.validate(result)
        gate_result = await self.gate.evaluate(validated)
        if gate_result == "auto_execute":
            await self.comms.on_task_complete(validated)
        return {
            "input": msg.model_dump(),
            "executed": result.model_dump(),
            "validated": validated.model_dump(),
            "gate": gate_result,
        }

    async def _persist_task(self, dag_id: str, task: TaskNode) -> None:
        await self.store.upsert("Tasks", {"dag_id": dag_id, **task.to_dict()})

    async def _persist_tasks(self, dag: TaskDAG) -> None:
        for task in dag.tasks:
            await self._persist_task(dag.dag_id, task)

    async def _block_pending_tasks(self, dag: TaskDAG, progress: ProgressCallback | None = None) -> None:
        done = {task.task_id for task in dag.tasks if task.status == "done"}
        terminal = {task.task_id: task.status for task in dag.tasks if task.status in {"blocked", "failed"}}
        for task in dag.tasks:
            if task.status != "pending":
                continue
            unsatisfied = [dependency for dependency in task.depends_on if dependency not in done]
            if not unsatisfied and dag.ready_tasks():
                continue
            task.status = "blocked"
            task.metadata["blocked_reason"] = (
                "Waiting on blocked dependencies: " + ", ".join(dep for dep in unsatisfied if dep in terminal)
                if any(dep in terminal for dep in unsatisfied)
                else "No executable dependency path remains."
            )
            await self._persist_task(dag.dag_id, task)
            await _publish(
                progress,
                {
                    "phase": "gate",
                    "status": "blocked",
                    "message": f"Blocked downstream task: {task.title}",
                    "task": task.to_dict(),
                },
            )

    async def _run_task(self, task: TaskNode, progress: ProgressCallback | None = None) -> dict:
        task.status = "running"
        await _publish(
            progress,
            {
                "phase": "execution",
                "status": "running",
                "message": f"{task.assigned_to} started: {task.title}",
                "task": task.to_dict(),
            },
        )
        msg = AgentMessage(
            type="execute",
            payload=task.to_dict(),
            assigned_to=task.assigned_to,
            confidence=task.confidence,
            jira_ticket_id=task.jira_ticket_id,
        )
        executed = await self.executor.execute(msg)
        await _publish(
            progress,
            {
                "phase": "execution",
                "status": "complete",
                "message": f"Executor completed: {task.title}",
                "task": task.to_dict(),
                "confidence": executed.confidence,
            },
        )
        validated = await self.validator.validate(executed)
        await _publish(
            progress,
            {
                "phase": "validation",
                "status": validated.status,
                "message": f"Validator returned {validated.payload.get('validation', {}).get('verdict', 'review')}: {task.title}",
                "task": task.to_dict(),
                "confidence": validated.confidence,
            },
        )
        gate_result = await self.gate.evaluate(validated)
        if gate_result == "auto_execute":
            await self.comms.on_task_complete(validated)
        return {"input": msg, "executed": executed, "validated": validated, "gate": gate_result}


async def _publish(progress: ProgressCallback | None, event: dict[str, Any]) -> None:
    if progress is not None:
        await progress(event)
