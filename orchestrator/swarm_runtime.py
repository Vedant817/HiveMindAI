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
        for task in dag.tasks:
            task.metadata.setdefault("dag_id", dag.dag_id)
        await self.store.upsert("TaskDAGs", dag.to_dict())
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
        await self._execute_dag(dag, history, progress)

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

    async def process_queued_tickets(
        self,
        queue: str | None = None,
        max_messages: int = 10,
        progress: ProgressCallback | None = None,
    ) -> dict:
        messages = await self.pm.bus.receive(queue=queue, max_messages=max_messages)
        executions = []
        for msg in messages:
            await _publish(
                progress,
                {
                    "phase": "ticket-execution",
                    "status": "running",
                    "message": f"Executing queued ticket: {msg.payload.get('title', msg.task_id)}",
                },
            )
            executions.append(await self.process_message(msg))
        return {"count": len(executions), "executions": executions}

    async def resume_approval(
        self,
        approval_id: str,
        approved: bool,
        token: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict:
        resolution = await self.gate.resolve(approval_id, approved=approved, token=token)
        if "error" in resolution:
            return resolution

        context = resolution.get("context", {})
        task_payload = resolution.get("task", {})
        dag_id = context.get("dag_id") or task_payload.get("metadata", {}).get("dag_id") or task_payload.get("dag_id")
        task_id = context.get("task_id") or task_payload.get("task_id")
        if not dag_id or not task_id:
            return {**resolution, "resumed": False, "reason": "approval was not tied to a persisted DAG task"}

        dag_data = await self.store.get("TaskDAGs", dag_id)
        if not dag_data:
            return {**resolution, "resumed": False, "reason": f"DAG {dag_id} was not found"}

        dag = TaskDAG.from_dict(dag_data)
        target = next((task for task in dag.tasks if task.task_id == task_id), None)
        if target is None:
            return {**resolution, "resumed": False, "reason": f"Task {task_id} was not found"}

        target.metadata.update({"approval_id": approval_id, "approved_by_human": approved})
        if not approved:
            target.status = "blocked"
            target.metadata["blocked_reason"] = "Human rejected the approval request."
            await self._block_pending_tasks(dag, progress)
            await self.store.upsert("TaskDAGs", dag.to_dict())
            await self._persist_tasks(dag)
            return {**resolution, "resumed": True, "dag": dag.to_dict(), "complete": False}

        target.status = "done"
        target.metadata.pop("gate", None)
        target.metadata.pop("blocked_reason", None)
        await self.store.upsert("TaskDAGs", dag.to_dict())
        await self._persist_task(dag.dag_id, target)
        history = [resolution.get("message", {})]
        await self._execute_dag(dag, history, progress)
        await self.store.upsert("TaskDAGs", dag.to_dict())
        await self._persist_tasks(dag)
        return {
            **resolution,
            "resumed": True,
            "dag": dag.to_dict(),
            "history": history,
            "complete": all(task.status == "done" for task in dag.tasks),
        }

    async def _execute_dag(self, dag: TaskDAG, history: list[dict], progress: ProgressCallback | None = None) -> None:
        while True:
            ready = dag.ready_tasks()
            if not ready:
                if not self._has_pending_approval(dag):
                    await self._block_pending_tasks(dag, progress)
                break
            for task in ready:
                result = await self._run_task(dag, task, progress)
                if result["gate"] == "auto_execute" and result["validated"].status == "done":
                    task.status = "done"
                    task.metadata.pop("gate", None)
                    task.metadata.pop("blocked_reason", None)
                else:
                    task.status = "blocked"
                    task.metadata["gate"] = result["gate"]
                    task.metadata["blocked_reason"] = (
                        "Waiting for human approval."
                        if result["gate"] == "awaiting_human"
                        else "Validation did not produce an auto-executable result."
                    )
                await self.store.upsert("TaskDAGs", dag.to_dict())
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

    def _has_pending_approval(self, dag: TaskDAG) -> bool:
        return any(task.status == "blocked" and task.metadata.get("gate") == "awaiting_human" for task in dag.tasks)

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

    async def _run_task(self, dag: TaskDAG, task: TaskNode, progress: ProgressCallback | None = None) -> dict:
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
            task_id=task.task_id,
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
        gate_result = await self.gate.evaluate(validated, context={"dag_id": dag.dag_id, "task_id": task.task_id})
        if gate_result == "auto_execute":
            await self.comms.on_task_complete(validated)
        return {"input": msg, "executed": executed, "validated": validated, "gate": gate_result}


async def _publish(progress: ProgressCallback | None, event: dict[str, Any]) -> None:
    if progress is not None:
        await progress(event)
