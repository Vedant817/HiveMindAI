import os
import tempfile
import unittest

from orchestrator.swarm_runtime import SwarmRuntime


class SwarmRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_state_dir = os.environ.get("LOCAL_STATE_DIR")
        self.old_llm_provider = os.environ.get("LLM_PROVIDER")
        self.old_fallbacks = os.environ.get("SWARM_ENABLE_LOCAL_FALLBACKS")
        os.environ["LOCAL_STATE_DIR"] = self.tmp.name
        os.environ["LLM_PROVIDER"] = "none"
        os.environ["SWARM_ENABLE_LOCAL_FALLBACKS"] = "true"

    async def asyncTearDown(self):
        if self.old_state_dir is None:
            os.environ.pop("LOCAL_STATE_DIR", None)
        else:
            os.environ["LOCAL_STATE_DIR"] = self.old_state_dir
        if self.old_llm_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = self.old_llm_provider
        if self.old_fallbacks is None:
            os.environ.pop("SWARM_ENABLE_LOCAL_FALLBACKS", None)
        else:
            os.environ["SWARM_ENABLE_LOCAL_FALLBACKS"] = self.old_fallbacks
        self.tmp.cleanup()

    async def test_run_goal_completes_local_swarm(self):
        result = await SwarmRuntime().run_goal("Build a dashboard before Friday")

        self.assertTrue(result["complete"])
        self.assertGreaterEqual(len(result["dag"]["tasks"]), 3)
        self.assertIn("improvement", result["reflection"])


if __name__ == "__main__":
    unittest.main()
