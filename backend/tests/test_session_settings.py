from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app.database import Database


class SessionSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        self.db.init()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_settings_are_unique_per_chat(self) -> None:
        first = self.db.create_session(max_sessions=10)
        second = self.db.create_session(max_sessions=10)

        updated = self.db.update_session_settings(
            first["id"],
            {
                "overall_model": "gpt-4o",
                "temperature": 0.1,
                "debate_rounds": 6,
                "show_timestamps": True,
            },
        )
        other = self.db.get_session_settings(second["id"])

        self.assertEqual(updated["overall_model"], "gpt-4o")
        self.assertEqual(updated["debaters_per_team"], 2)
        self.assertEqual(updated["discussion_messages_per_team"], 3)
        self.assertTrue(updated["judge_assistant_enabled"])
        self.assertIn("council_assistant", updated["agent_settings"])
        self.assertIn("lead_advocate", updated["agent_settings"])
        self.assertEqual(updated["temperature"], 0.1)
        self.assertEqual(updated["debate_rounds"], 6)
        self.assertTrue(updated["show_timestamps"])
        self.assertEqual(other["overall_model"], "")
        self.assertNotEqual(other["temperature"], 0.1)
        self.assertFalse(other["show_timestamps"])

    def test_settings_are_clamped_to_safe_ranges(self) -> None:
        session = self.db.create_session(max_sessions=10)

        updated = self.db.update_session_settings(
            session["id"],
            {
                "temperature": 3,
                "max_tokens": 9999,
                "debate_rounds": 99,
                "context_window": -1,
                "debaters_per_team": 99,
                "discussion_messages_per_team": 99,
                "agent_settings": {
                    "council_assistant": {"always_on": True},
                    "lead_advocate": {
                        "temperature": -1,
                        "max_tokens": 9999,
                        "response_length": "Huge",
                    }
                },
            },
        )

        self.assertEqual(updated["temperature"], 1.0)
        self.assertEqual(updated["max_tokens"], 2000)
        self.assertEqual(updated["debate_rounds"], 6)
        self.assertEqual(updated["context_window"], 0)
        self.assertEqual(updated["debaters_per_team"], 4)
        self.assertEqual(updated["discussion_messages_per_team"], 4)
        self.assertTrue(updated["agent_settings"]["council_assistant"]["always_on"])
        self.assertEqual(updated["agent_settings"]["lead_advocate"]["temperature"], 0.0)
        self.assertEqual(updated["agent_settings"]["lead_advocate"]["max_tokens"], 2000)
        self.assertEqual(updated["agent_settings"]["lead_advocate"]["response_length"], "Normal")

    def test_legacy_role_models_are_normalized_to_v2_agent_keys(self) -> None:
        session = self.db.create_session(max_sessions=10)

        updated = self.db.update_session_settings(
            session["id"],
            {
                "role_models": {
                    "critic": "gpt-4o",
                    "researcher": "claude-sonnet-4-6",
                    "judge": "gpt-4o-mini",
                }
            },
        )

        self.assertNotIn("critic", updated["role_models"])
        self.assertEqual(updated["role_models"]["rebuttal_critic"], "gpt-4o")
        self.assertEqual(updated["role_models"]["evidence_researcher"], "claude-sonnet-4-6")
        self.assertEqual(updated["agent_settings"]["rebuttal_critic"]["model"], "gpt-4o")
        self.assertEqual(updated["agent_settings"]["evidence_researcher"]["model"], "claude-sonnet-4-6")
        self.assertEqual(updated["agent_settings"]["judge"]["model"], "gpt-4o-mini")

    def test_cost_display_settings_are_saved_per_chat(self) -> None:
        first = self.db.create_session(max_sessions=10)
        second = self.db.create_session(max_sessions=10)

        updated = self.db.update_session_settings(
            first["id"],
            {
                "show_money_cost": False,
                "cost_currency": "CNY",
                "show_model_costs": True,
                "show_every_message_cost_in_debate": True,
            },
        )
        other = self.db.get_session_settings(second["id"])

        self.assertFalse(updated["show_money_cost"])
        self.assertEqual(updated["cost_currency"], "CNY")
        self.assertTrue(updated["show_model_costs"])
        self.assertTrue(updated["show_every_message_cost_in_debate"])
        self.assertTrue(other["show_money_cost"])
        self.assertEqual(other["cost_currency"], "USD")
        self.assertFalse(other["show_model_costs"])
        self.assertFalse(other["show_every_message_cost_in_debate"])

    def test_message_cost_summary_round_trips(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Cost test", mode="chat")
        summary = {"currency": "USD", "total": 0.001, "models": []}

        saved = self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="assistant",
            speaker="Council Assistant",
            model="gpt-4o-mini",
            content="Done.",
            cost_summary=summary,
            debate_cost_summary={"currency": "USD", "total": 0.01, "models": []},
        )
        listed = self.db.list_messages(session["id"])

        self.assertEqual(saved["cost_summary"], summary)
        self.assertEqual(saved["debate_cost_summary"]["total"], 0.01)
        self.assertEqual(listed[0]["cost_summary"], summary)
        self.assertEqual(listed[0]["debate_cost_summary"]["total"], 0.01)

    def test_existing_settings_table_is_migrated_for_overall_model(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                default_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE session_settings (
                session_id TEXT PRIMARY KEY,
                role_models TEXT NOT NULL,
                temperature REAL NOT NULL,
                max_tokens INTEGER NOT NULL,
                debate_tone TEXT NOT NULL,
                language TEXT NOT NULL,
                response_length TEXT NOT NULL,
                auto_scroll INTEGER NOT NULL,
                show_timestamps INTEGER NOT NULL,
                show_token_count INTEGER NOT NULL,
                context_window INTEGER NOT NULL,
                debate_rounds INTEGER NOT NULL,
                researcher_web_search INTEGER NOT NULL,
                fact_check_mode INTEGER NOT NULL,
                export_format TEXT NOT NULL,
                auto_save_interval INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.close()

        migrated = Database(legacy_path)
        migrated.init()
        session = migrated.create_session(max_sessions=10)
        settings = migrated.get_session_settings(session["id"])

        self.assertEqual(settings["overall_model"], "")
        self.assertEqual(settings["debaters_per_team"], 2)
        self.assertEqual(settings["discussion_messages_per_team"], 3)
        self.assertTrue(settings["judge_assistant_enabled"])
        self.assertFalse(settings["show_every_message_cost_in_debate"])
        self.assertIn("council_assistant", settings["agent_settings"])
        self.assertIn("judge", settings["agent_settings"])

    def test_migration_repairs_judge_only_debates_marked_as_chat(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Legacy judge-only debate")
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="judge",
            speaker="Judge",
            model="mock-model",
            content="WINNER: Pro",
        )
        with self.db.session(immediate=True) as connection:
            connection.execute("UPDATE debates SET mode = 'chat' WHERE id = ?", (debate["id"],))

        migrated = Database(self.db.path)
        migrated.init()
        repaired = migrated.list_debates(session["id"])

        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired[0]["id"], debate["id"])
        self.assertEqual(repaired[0]["mode"], "debate")

    def test_global_experience_list_includes_chat_and_universal_records(self) -> None:
        session = self.db.create_session(max_sessions=10)
        self.db.add_agent_experience(
            scope="universal",
            agent_id="pro_lead_advocate",
            lesson_type="debate_activity",
            lesson="Universal lesson",
        )
        self.db.add_agent_experience(
            scope="chat",
            session_id=session["id"],
            agent_id="con_lead_advocate",
            lesson_type="debate_activity",
            lesson="Chat lesson",
        )

        rows = self.db.list_global_agent_experience(limit=10)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["scope"] for row in rows}, {"universal", "chat"})

    def test_recent_global_debates_can_filter_to_practice(self) -> None:
        session = self.db.create_session(max_sessions=10)
        council_debate = self.db.create_debate(session["id"], "AI vs AI topic", mode="debate")
        practice_debate = self.db.create_debate(session["id"], "Practice topic", mode="practice")

        rows = self.db.list_recent_debates_global(modes=("practice",), limit=10)

        self.assertEqual([row["id"] for row in rows], [practice_debate["id"]])
        self.assertNotIn(council_debate["id"], [row["id"] for row in rows])

    def test_clear_history_hides_visible_messages_but_keeps_memory(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Should AI debates be saved?")
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="user",
            speaker="You",
            model="user",
            content="Please debate this.",
        )
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="assistant",
            speaker="Council Assistant",
            model="mock",
            content="Saved memory.",
        )

        self.assertTrue(self.db.clear_visible_history(session["id"]))

        self.assertEqual(self.db.list_messages(session["id"]), [])
        self.assertEqual(self.db.list_debates(session["id"]), [])
        self.assertEqual(len(self.db.list_messages(session["id"], include_hidden=True)), 2)
        self.assertEqual(len(self.db.list_debates(session["id"], include_hidden=True)), 1)

    def test_clear_memory_removes_visible_history_and_memory(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "Should AI debates be saved?")
        self.db.add_message(
            session_id=session["id"],
            debate_id=debate["id"],
            role="user",
            speaker="You",
            model="user",
            content="Please debate this.",
        )

        self.assertTrue(self.db.clear_memory(session["id"]))

        self.assertEqual(self.db.list_messages(session["id"], include_hidden=True), [])
        self.assertEqual(self.db.list_debates(session["id"], include_hidden=True), [])

    def test_debate_names_increment_and_chat_records_are_not_listed_as_debates(self) -> None:
        session = self.db.create_session(max_sessions=10)
        first = self.db.create_debate(session["id"], "First debate")
        chat = self.db.create_debate(session["id"], "Normal chat", mode="chat")
        second = self.db.create_debate(session["id"], "Second debate")

        debates = self.db.list_debates(session["id"])

        self.assertEqual(first["name"], "Debate #1")
        self.assertEqual(chat["name"], "Council Assistant Chat")
        self.assertEqual(second["name"], "Debate #2")
        self.assertEqual([debate["id"] for debate in debates], [second["id"], first["id"]])

    def test_hiding_debate_statistics_keeps_chat_messages_visible(self) -> None:
        session = self.db.create_session(max_sessions=10)
        first = self.db.create_debate(session["id"], "First debate")
        self.db.add_message(
            session_id=session["id"],
            debate_id=first["id"],
            role="pro_lead_advocate",
            speaker="Pro Lead Advocate",
            model="mock",
            content="Visible transcript remains.",
        )

        self.assertTrue(self.db.hide_debate_statistics(session["id"], first["id"]))

        self.assertEqual(self.db.list_debates(session["id"]), [])
        self.assertEqual(len(self.db.list_messages(session["id"])), 1)

        reset = self.db.create_debate(session["id"], "Reset debate counter")
        self.assertEqual(reset["name"], "Debate #1")

    def test_renaming_debate_changes_statistics_record(self) -> None:
        session = self.db.create_session(max_sessions=10)
        debate = self.db.create_debate(session["id"], "First debate")

        renamed = self.db.rename_debate(session["id"], debate["id"], "Policy Round")

        self.assertIsNotNone(renamed)
        self.assertEqual(renamed["name"], "Policy Round")


if __name__ == "__main__":
    unittest.main()
