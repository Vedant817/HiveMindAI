import unittest
from unittest.mock import patch

from orchestrator.group_chat import _autogen_model_config
from shared.config import active_llm_provider, config_report, is_real_value, llm_configured


class ConfigTests(unittest.TestCase):
    def test_openrouter_provider_is_selected_when_configured(self):
        env = {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "qwen/qwen3-coder:free",
            "SWARM_ENABLE_LOCAL_FALLBACKS": "true",
        }

        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(active_llm_provider(), "openrouter")
            self.assertTrue(llm_configured())
            self.assertTrue(config_report()["free_model_ready"])

    def test_provider_none_is_not_llm_configured(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "none"}, clear=True):
            self.assertEqual(active_llm_provider(), "none")
            self.assertFalse(llm_configured())

    def test_placeholder_values_are_not_treated_as_configured(self):
        self.assertFalse(is_real_value("https://your-resource.openai.azure.com/"))
        self.assertFalse(is_real_value("your_openrouter_key"))
        self.assertTrue(is_real_value("test-key"))

    def test_autogen_openrouter_config_is_not_azure_hardcoded(self):
        env = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "openrouter/free",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        }

        with patch.dict("os.environ", env, clear=True):
            config = _autogen_model_config("openrouter")
            self.assertEqual(config["model"], "openrouter/free")
            self.assertEqual(config["api_key"], "test-key")
            self.assertEqual(config["base_url"], "https://openrouter.ai/api/v1")
            self.assertNotIn("api_type", config)

    def test_free_stack_reports_free_services_only(self):
        env = {
            "APP_STACK": "free",
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "qwen/qwen3-coder:free",
            "MONGODB_URI": "mongodb+srv://user:pass@cluster.mongodb.net",
            "REDIS_URL": "rediss://default:token@example.upstash.io:6379",
        }

        with patch.dict("os.environ", env, clear=True):
            report = config_report()
            self.assertEqual(report["app_stack"], "free")
            self.assertTrue(report["free_stack_ready"])
            self.assertIn("MongoDB Atlas", report["integrations"])
            self.assertIn("Upstash Redis", report["integrations"])
            self.assertNotIn("Azure Service Bus", report["integrations"])
            self.assertNotIn("Cosmos DB", report["integrations"])

    def test_azure_stack_keeps_azure_readiness(self):
        with patch.dict("os.environ", {"APP_STACK": "azure", "LLM_PROVIDER": "azure"}, clear=True):
            report = config_report()
            self.assertEqual(report["app_stack"], "azure")
            self.assertIn("Azure Service Bus", report["integrations"])
            self.assertIn("Cosmos DB", report["integrations"])
            self.assertNotIn("MongoDB Atlas", report["integrations"])


if __name__ == "__main__":
    unittest.main()
