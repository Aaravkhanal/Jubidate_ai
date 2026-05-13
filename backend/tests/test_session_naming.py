from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.app.database import Database


class SessionNamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db = Database(self.db_path)
        self.db.init()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_names_are_monotonic_while_any_session_exists(self) -> None:
        sessions = [self.db.create_session(max_sessions=10) for _ in range(10)]

        self.assertEqual(sessions[0]["name"], "Debate Session #1")
        self.assertEqual(sessions[9]["name"], "Debate Session #10")

        deleted = self.db.delete_session(sessions[1]["id"])
        self.assertTrue(deleted)
        self.assertEqual(len(self.db.list_sessions()), 9)

        next_session = self.db.create_session(max_sessions=10)
        self.assertEqual(next_session["name"], "Debate Session #11")
        self.assertEqual(next_session["default_index"], 11)

    def test_counter_resets_after_all_sessions_are_deleted(self) -> None:
        sessions = [self.db.create_session(max_sessions=10) for _ in range(3)]
        for session in sessions:
            self.db.delete_session(session["id"])

        reset_session = self.db.create_session(max_sessions=10)
        self.assertEqual(reset_session["name"], "Debate Session #1")
        self.assertEqual(reset_session["default_index"], 1)

    def test_delete_all_sessions_resets_counter_and_preserves_universal_experience(self) -> None:
        session = self.db.create_session(max_sessions=10)
        self.db.add_agent_experience(
            scope="universal",
            agent_id="judge",
            lesson_type="rubric",
            lesson="Prefer direct winner statements.",
        )
        self.db.add_agent_experience(
            scope="chat",
            session_id=session["id"],
            agent_id="pro_advocate",
            lesson_type="team_note",
            lesson="Protect the main burden.",
        )

        deleted = self.db.delete_all_sessions()

        self.assertEqual(deleted, 1)
        self.assertEqual(self.db.list_sessions(), [])
        universal = self.db.list_agent_experience(agent_id="judge", include_universal=True)
        chat_scoped = self.db.list_agent_experience(
            agent_id="pro_advocate",
            session_id=session["id"],
            include_universal=False,
        )
        self.assertEqual(len(universal), 1)
        self.assertEqual(chat_scoped, [])

        reset_session = self.db.create_session(max_sessions=10)
        self.assertEqual(reset_session["name"], "Debate Session #1")
        self.assertEqual(reset_session["default_index"], 1)

    def test_session_limit_counts_current_sessions_not_historical_numbers(self) -> None:
        sessions = [self.db.create_session(max_sessions=10) for _ in range(10)]
        with self.assertRaisesRegex(ValueError, "SESSION_LIMIT"):
            self.db.create_session(max_sessions=10)

        self.db.delete_session(sessions[0]["id"])
        created = self.db.create_session(max_sessions=10)

        self.assertEqual(created["name"], "Debate Session #11")
        self.assertEqual(len(self.db.list_sessions()), 10)

    def test_rename_and_delete_update_session_records(self) -> None:
        session = self.db.create_session(max_sessions=10)

        renamed = self.db.rename_session(session["id"], "  Better Council Name  ")
        self.assertEqual(renamed["name"], "Better Council Name")
        self.assertEqual(self.db.get_session(session["id"])["name"], "Better Council Name")

        self.assertTrue(self.db.delete_session(session["id"]))
        self.assertIsNone(self.db.get_session(session["id"]))


if __name__ == "__main__":
    unittest.main()
