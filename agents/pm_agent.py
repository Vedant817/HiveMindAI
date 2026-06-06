from __future__ import annotations

from agents.planner_agent import PlannerAgent
from memory.cosmos_client import CosmosClient
from schemas.task_dag import TaskDAG
from shared.message_schema import AgentMessage
from shared.service_bus import ServiceBusClient


class PMAgent:
    def __init__(
        self,
        planner: PlannerAgent | None = None,
        bus: ServiceBusClient | None = None,
        store: CosmosClient | None = None,
    ) -> None:
        self.planner = planner or PlannerAgent()
        self.bus = bus or ServiceBusClient()
        self.store = store or CosmosClient()

    async def create_plan(self, goal: str) -> TaskDAG:
        dag = await self.planner.plan_async(goal)
        await self.store.upsert("TaskDAGs", dag.to_dict())
        return dag

    async def dispatch_ready(self, dag: TaskDAG) -> list[AgentMessage]:
        dispatched: list[AgentMessage] = []
        for task in dag.ready_tasks():
            msg = AgentMessage(
                type="execute",
                payload=task.to_dict(),
                assigned_to=task.assigned_to,
                confidence=task.confidence,
            )
            await self.bus.send(msg)
            dispatched.append(msg)
            task.status = "running"
        await self.store.upsert("TaskDAGs", dag.to_dict())
        return dispatched

    async def run_goal(self, goal: str) -> dict:
        dag = await self.create_plan(goal)
        dispatched = await self.dispatch_ready(dag)
        return {"dag": dag.to_dict(), "dispatched": [msg.model_dump() for msg in dispatched]}
