import os
import tempfile
import unittest

from agents.planner_agent import PlannerAgent
from memory.cosmos_client import CosmosClient
from memory.knowledge_store import KnowledgeStore
from schemas.knowledge_entry import KnowledgeEntry


class StorageAndResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_env = {
            name: os.environ.get(name)
            for name in (
                "LOCAL_STATE_DIR",
                "LLM_PROVIDER",
                "SWARM_ENABLE_LOCAL_FALLBACKS",
                "SWARM_STRICT_INTEGRATIONS",
                "MONGODB_URI",
                "COSMOS_ENDPOINT",
                "COSMOS_KEY",
                "SEARCH_ENDPOINT",
                "SEARCH_KEY",
                "REDIS_URL",
            )
        }
        os.environ["LOCAL_STATE_DIR"] = self.tmp.name
        os.environ["LLM_PROVIDER"] = "none"
        os.environ["SWARM_ENABLE_LOCAL_FALLBACKS"] = "true"
        os.environ["SWARM_STRICT_INTEGRATIONS"] = "false"
        for name in ("MONGODB_URI", "COSMOS_ENDPOINT", "COSMOS_KEY", "SEARCH_ENDPOINT", "SEARCH_KEY", "REDIS_URL"):
            os.environ.pop(name, None)

    async def asyncTearDown(self):
        for name, value in self.saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.tmp.cleanup()

    async def test_dag_upsert_uses_stable_dag_id(self):
        store = CosmosClient()
        await store.upsert("TaskDAGs", {"dag_id": "dag-1", "goal": "first", "tasks": []})
        await store.upsert("TaskDAGs", {"dag_id": "dag-1", "goal": "updated", "tasks": []})

        rows = await store.query("TaskDAGs")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "dag-1")
        self.assertEqual(rows[0]["goal"], "updated")

    async def test_local_knowledge_search_survives_new_store_instance(self):
        first_store = KnowledgeStore()
        await first_store.add_entry(
            KnowledgeEntry(
                title="Redis status updates",
                content="Use Redis pub/sub for short-lived cross-agent status fan-out.",
                kind="decision",
                tags=["redis", "status"],
            )
        )

        second_store = KnowledgeStore()
        matches = await second_store.search_entries("redis status")

        self.assertTrue(matches)
        self.assertEqual(matches[0]["title"], "Redis status updates")

    async def test_malformed_llm_plan_falls_back_to_local_dag(self):
        class BadLLM:
            async def chat_json(self, *_args, **_kwargs):
                return [{"title": "Build", "description": "Missing dependency", "depends_on": ["Unknown"]}]

        dag = await PlannerAgent(llm=BadLLM()).plan_async("Build dashboard")

        self.assertEqual(len(dag.tasks), 3)
        self.assertEqual(dag.tasks[0].assigned_to, "Planner")


if __name__ == "__main__":
    unittest.main()
