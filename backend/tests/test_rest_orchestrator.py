import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Set test database path and mock setting before importing any app modules
temp_dir = TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(temp_dir.name) / "test.db")
os.environ["MOCK_LLM_RESPONSES"] = "true"

from fastapi.testclient import TestClient
from app.main import app, db
from app.model_registry import MODEL_MAP


class RESTOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.main import settings
        settings.mock_llm = True
        cls.client = TestClient(app)

    def setUp(self) -> None:
        # Re-initialize the test database schema before each test
        db.init()

    def tearDown(self) -> None:
        # Clean up database file to start fresh in subsequent tests
        db_path = Path(temp_dir.name) / "test.db"
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass

    def test_models_and_modes_endpoints(self) -> None:
        # Test GET /debate/models
        response = self.client.get("/debate/models")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("models", data)
        self.assertIn("nemotron-70b", data["models"])
        self.assertIn("mistral-nemotron", data["models"])

        # Test GET /debate/modes
        response = self.client.get("/debate/modes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("modes", data)
        modes = {m["key"]: m["label"] for m in data["modes"]}
        self.assertEqual(modes.get("ai_vs_human"), "Human vs AI")
        self.assertEqual(modes.get("ai_vs_ai"), "AI vs AI")

    def test_create_session_validation_errors(self) -> None:
        # 1. Invalid debate mode
        payload = {
            "mode": "invalid_mode",
            "ai_a_model": "llama-3.1-8b",
            "judge_model": "mixtral-8x7b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid debate mode selected", response.json()["detail"])

        # 2. Human vs AI: Duplicate Opponent and Judge
        payload = {
            "mode": "ai_vs_human",
            "ai_a_model": "llama-3.1-8b",
            "judge_model": "llama-3.1-8b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Judge AI must not be the same model as the Opponent AI", response.json()["detail"])

        # 3. AI vs AI: Missing AI B model
        payload = {
            "mode": "ai_vs_ai",
            "ai_a_model": "llama-3.1-8b",
            "ai_b_model": "",
            "judge_model": "mixtral-8x7b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("AI B model is required for AI vs AI mode", response.json()["detail"])

        # 4. AI vs AI: Duplicate Judge and AI A
        payload = {
            "mode": "ai_vs_ai",
            "ai_a_model": "llama-3.1-8b",
            "ai_b_model": "mixtral-8x7b",
            "judge_model": "llama-3.1-8b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Judge model must always be different from both AI A and AI B", response.json()["detail"])

        # 5. AI vs AI: Duplicate Judge and AI B
        payload = {
            "mode": "ai_vs_ai",
            "ai_a_model": "llama-3.1-8b",
            "ai_b_model": "mixtral-8x7b",
            "judge_model": "mixtral-8x7b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Judge model must always be different from both AI A and AI B", response.json()["detail"])

        # 6. AI vs AI: Duplicate AI A and AI B
        payload = {
            "mode": "ai_vs_ai",
            "ai_a_model": "llama-3.1-8b",
            "ai_b_model": "llama-3.1-8b",
            "judge_model": "mixtral-8x7b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("AI A and AI B must be different debater models", response.json()["detail"])

        # 7. Valid Human vs AI creation
        payload = {
            "mode": "ai_vs_human",
            "ai_a_model": "llama-3.1-8b",
            "judge_model": "mixtral-8x7b",
            "rounds": 3
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "ai_vs_human")
        self.assertEqual(data["ai_a_model"], "llama-3.1-8b")
        self.assertEqual(data["judge_model"], "mixtral-8x7b")
        self.assertEqual(data["rounds"], 3)

    def test_ai_vs_human_turn_based_flow(self) -> None:
        # Create session
        payload = {
            "mode": "ai_vs_human",
            "ai_a_model": "llama-3.1-8b",
            "judge_model": "mixtral-8x7b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 200)
        session_id = response.json()["id"]

        # Start debate
        start_payload = {
            "session_id": session_id,
            "topic": "Should schools use AI tutors?"
        }
        response = self.client.post("/debate/start", json=start_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("session", data)
        self.assertIn("debate", data)
        self.assertIn("messages", data)

        debate_id = data["debate"]["id"]
        messages = data["messages"]
        # Expected messages:
        # 1. User/Topic message ("Should schools use AI tutors?")
        # 2. Con - llama-3.1-8b opening argument
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["speaker"], "You")
        self.assertEqual(messages[0]["content"], "Should schools use AI tutors?")
        
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["speaker"], "Con - llama-3.1-8b")
        self.assertIn("Mock Response", messages[1]["content"])
        self.assertEqual(messages[1]["phase_key"], "con_constructive_1")

        # Next turn (Human Rebuttal / Turn 2)
        next_payload = {
            "session_id": session_id,
            "debate_id": debate_id,
            "content": "AI tutors provide customized pace but lack social empathy."
        }
        response = self.client.post("/debate/next-turn", json=next_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        messages = data["messages"]
        # Expected messages:
        # 1. User/Topic
        # 2. Con - llama-3.1-8b opening argument
        # 3. You - Rebuttal 2 ("AI tutors provide...")
        # 4. Con - llama-3.1-8b Rebuttal 2
        # Since rounds = 2, this was the last round!
        # Thus, it should also trigger:
        # 5. Judge verdict
        self.assertEqual(len(messages), 5)
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["speaker"], "You")
        self.assertEqual(messages[2]["content"], "AI tutors provide customized pace but lack social empathy.")
        self.assertEqual(messages[2]["phase_key"], "pro_rebuttal_2")

        self.assertEqual(messages[3]["role"], "assistant")
        self.assertEqual(messages[3]["speaker"], "Con - llama-3.1-8b")
        self.assertEqual(messages[3]["phase_key"], "con_rebuttal_2")

        self.assertEqual(messages[4]["role"], "judge")
        self.assertEqual(messages[4]["speaker"], "Judge")
        self.assertEqual(messages[4]["model"], "mixtral-8x7b")

        # Verify debate status is completed
        self.assertEqual(data["debate"]["status"], "completed")
        self.assertIsNotNone(data["debate"]["judge_summary"])

    def test_ai_vs_ai_turn_based_flow(self) -> None:
        # Create AI vs AI session
        payload = {
            "mode": "ai_vs_ai",
            "ai_a_model": "llama-3.1-8b",
            "ai_b_model": "mixtral-8x7b",
            "judge_model": "nemotron-70b",
            "rounds": 2
        }
        response = self.client.post("/debate/create", json=payload)
        self.assertEqual(response.status_code, 200)
        session_id = response.json()["id"]

        # Start debate
        start_payload = {
            "session_id": session_id,
            "topic": "Should space exploration be fully privatized?"
        }
        response = self.client.post("/debate/start", json=start_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        debate_id = data["debate"]["id"]
        messages = data["messages"]
        # Expected:
        # 1. Topic (System message)
        # 2. Pro - llama-3.1-8b opening argument
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["speaker"], "System")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["speaker"], "Pro - llama-3.1-8b")
        self.assertEqual(messages[1]["phase_key"], "pro_constructive_1")

        # Next turn (triggers AI B opening constructive argument)
        next_payload = {
            "session_id": session_id,
            "debate_id": debate_id
        }
        response = self.client.post("/debate/next-turn", json=next_payload)
        self.assertEqual(response.status_code, 200)
        messages = response.json()["messages"]
        # Expected:
        # 1. Topic
        # 2. Pro opening (llama-3.1-8b)
        # 3. Con opening (mixtral-8x7b)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[2]["speaker"], "Con - mixtral-8x7b")
        self.assertEqual(messages[2]["phase_key"], "con_rebuttal_1")

        # Next turn (triggers AI A round 2 rebuttal)
        response = self.client.post("/debate/next-turn", json=next_payload)
        self.assertEqual(response.status_code, 200)
        messages = response.json()["messages"]
        # Expected:
        # 1. Topic
        # 2. Pro opening
        # 3. Con opening
        # 4. Pro rebuttal 2 (llama-3.1-8b)
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[3]["speaker"], "Pro - llama-3.1-8b")
        self.assertEqual(messages[3]["phase_key"], "pro_rebuttal_2")

        # Next turn (triggers AI B round 2 rebuttal & Judge Adjudication since rounds = 2)
        response = self.client.post("/debate/next-turn", json=next_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        messages = data["messages"]
        # Expected:
        # 1. Topic
        # 2. Pro opening
        # 3. Con opening
        # 4. Pro rebuttal 2
        # 5. Con rebuttal 2
        # 6. Judge Adjudication (nemotron-70b)
        self.assertEqual(len(messages), 6)
        self.assertEqual(messages[4]["speaker"], "Con - mixtral-8x7b")
        self.assertEqual(messages[4]["phase_key"], "con_rebuttal_2")

        self.assertEqual(messages[5]["role"], "judge")
        self.assertEqual(messages[5]["speaker"], "Judge")
        self.assertEqual(messages[5]["model"], "nemotron-70b")

        # Verify completed status
        self.assertEqual(data["debate"]["status"], "completed")
        self.assertIsNotNone(data["debate"]["judge_summary"])


if __name__ == "__main__":
    unittest.main()
