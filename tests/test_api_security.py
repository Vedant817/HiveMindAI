import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from main import create_app


class ApiSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_env = {name: os.environ.get(name) for name in ("HIVEMIND_API_KEY", "LOCAL_STATE_DIR", "LLM_PROVIDER")}
        os.environ["HIVEMIND_API_KEY"] = "test-api-key"
        os.environ["LOCAL_STATE_DIR"] = self.tmp.name
        os.environ["LLM_PROVIDER"] = "none"
        self.client = TestClient(create_app())

    def tearDown(self):
        for name, value in self.saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.tmp.cleanup()

    def test_mutating_routes_require_api_key_when_configured(self):
        denied = self.client.post("/swarm/run", json={"goal": "Build dashboard"})
        allowed = self.client.post(
            "/swarm/run",
            json={"goal": "Build dashboard"},
            headers={"X-Hivemind-Api-Key": "test-api-key"},
        )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()["complete"])


if __name__ == "__main__":
    unittest.main()
