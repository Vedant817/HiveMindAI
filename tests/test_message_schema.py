import unittest

from shared.message_schema import AgentMessage


class AgentMessageTests(unittest.TestCase):
    def test_json_round_trip(self):
        msg = AgentMessage(
            type="execute",
            payload={"title": "Build dashboard"},
            confidence=0.91,
            assigned_to="Executor",
        )

        restored = AgentMessage.model_validate_json(msg.model_dump_json())

        self.assertEqual(restored.task_id, msg.task_id)
        self.assertEqual(restored.payload["title"], "Build dashboard")
        self.assertEqual(restored.confidence, 0.91)

    def test_rejects_invalid_confidence(self):
        with self.assertRaises(ValueError):
            AgentMessage(type="execute", payload={}, confidence=1.2)


if __name__ == "__main__":
    unittest.main()

