import os
import tempfile
import unittest

from agents.executor_agent import ExecutorAgent
from agents.meeting_agent import MeetingAgent
from hitl.confidence_gate import ConfidenceGate
from orchestrator.swarm_runtime import SwarmRuntime
from shared.artifacts import artifact_exists
from shared.message_schema import AgentMessage
from shared.redis_client import RedisClient
from shared.security import sign_token, verify_token


class EndToEndFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = tempfile.TemporaryDirectory()
        self.saved_env = {
            name: os.environ.get(name)
            for name in (
                "LOCAL_STATE_DIR",
                "WORKSPACE_DIR",
                "LLM_PROVIDER",
                "SWARM_ENABLE_LOCAL_FALLBACKS",
                "SWARM_STRICT_INTEGRATIONS",
                "REDIS_URL",
                "APP_SECRET",
                "HIVEMIND_API_KEY",
            )
        }
        os.environ["LOCAL_STATE_DIR"] = self.tmp.name
        os.environ["WORKSPACE_DIR"] = self.workspace.name
        os.environ["LLM_PROVIDER"] = "none"
        os.environ["SWARM_ENABLE_LOCAL_FALLBACKS"] = "true"
        os.environ["SWARM_STRICT_INTEGRATIONS"] = "false"
        os.environ.pop("REDIS_URL", None)
        os.environ.pop("APP_SECRET", None)
        os.environ.pop("HIVEMIND_API_KEY", None)
        RedisClient._memory.clear()
        RedisClient._channels.clear()

    async def asyncTearDown(self):
        for name, value in self.saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        RedisClient._memory.clear()
        RedisClient._channels.clear()
        self.workspace.cleanup()
        self.tmp.cleanup()

    async def test_executor_produces_verifiable_artifacts(self):
        msg = AgentMessage(
            type="execute",
            payload={
                "title": "Build dashboard",
                "description": "Create a project health dashboard artifact.",
                "task_id": "task-1",
                "metadata": {"dag_id": "dag-1"},
            },
        )

        result = await ExecutorAgent().execute(msg)
        artifacts = result.payload["output"]["artifacts"]

        self.assertGreaterEqual(len(artifacts), 2)
        self.assertTrue(all(artifact_exists(path) for path in artifacts))

    async def test_meeting_tickets_are_drained_and_executed(self):
        meeting = MeetingAgent()
        result = await meeting.process_transcript("Action: build a dashboard before Friday")

        executions = await SwarmRuntime().process_queued_tickets(max_messages=result["count"])

        self.assertEqual(result["count"], 1)
        self.assertEqual(executions["count"], 1)
        self.assertTrue(executions["executions"][0]["complete"])

    async def test_human_approval_resume_continues_the_dag(self):
        runtime = SwarmRuntime(gate=ConfidenceGate(threshold=0.99))
        result = await runtime.run_goal("Build a dashboard before Friday")
        pending_keys = [key for key in RedisClient._memory if key.startswith("pending:")]

        self.assertFalse(result["complete"])
        self.assertEqual(len(pending_keys), 1)

        approval_id = pending_keys[0].split(":", 1)[1]
        runtime.gate.threshold = 0.90
        resumed = await runtime.resume_approval(approval_id, approved=True)

        self.assertTrue(resumed["resumed"])
        self.assertTrue(resumed["complete"])

    async def test_signed_approval_tokens_are_verified(self):
        os.environ["APP_SECRET"] = "test-secret"
        token = sign_token("approval-1")

        self.assertTrue(verify_token("approval-1", token))
        self.assertFalse(verify_token("approval-2", token))


if __name__ == "__main__":
    unittest.main()
