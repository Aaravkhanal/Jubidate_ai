from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Iterator
from uuid import uuid4

from .costing import normalize_currency


SESSION_COUNTER_KEY = "session_counter"
DEFAULT_SESSION_PREFIX = "Debate Session #"
DEFAULT_DEBATE_PREFIX = "Debate #"
DEFAULT_PRACTICE_PREFIX = "Practice Debate #"
COUNCIL_SETTINGS_KEY = "council_settings"
USER_DEBATE_PROFILE_KEY = "user_debate_profile"
CHAT_MODES = {"ai_vs_ai", "ai_vs_human"}
DEFAULT_CONFIRMATION_PREFERENCES = {
    "delete_chat": False,
    "clear_chat_history": False,
    "clear_chat_memory": False,
}
DEFAULT_COUNCIL_SETTINGS = {
    "universal_experience": True,
    "use_agent_identity_profiles": True,
    "use_user_debate_profile": True,
    "theme": "Light",
    "debate_intelligence_depth": "Normal",
    "use_value_consequence_system": True,
    "default_judge_mode": "Hybrid",
    "confirmation_preferences": DEFAULT_CONFIRMATION_PREFERENCES,
}
COUNCIL_SETTING_CHOICES = {
    "debate_intelligence_depth": {"Light", "Normal", "Deep"},
    "default_judge_mode": {"Debate Performance", "Truth-Seeking", "Hybrid"},
    "theme": {"Light", "Dark", "System"},
}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


DEFAULT_DEBATE_ROUNDS = _int_env("DEBATE_ROUNDS", 2, 1, 6)
AGENT_ROLE_KEYS = (
    "council_assistant",
    "practice_debater",
    "debate_trainer",
    "lead_advocate",
    "rebuttal_critic",
    "evidence_researcher",
    "cross_examiner",
    "judge_assistant",
    "judge",
)
LEGACY_ROLE_MODEL_ALIASES = {
    "advocate": "lead_advocate",
    "critic": "rebuttal_critic",
    "researcher": "evidence_researcher",
    "devils_advocate": "cross_examiner",
}
DEFAULT_ROLE_MODELS = {role: "" for role in AGENT_ROLE_KEYS}
DEFAULT_AGENT_SETTINGS = {
    role: {
        "model": "",
        "temperature": 0.55,
        "max_tokens": 700,
        "response_length": "Normal",
        "web_search": False,
        "always_on": False,
    }
    for role in AGENT_ROLE_KEYS
}
DEFAULT_SESSION_SETTINGS = {
    "overall_model": "",
    "debaters_per_team": 2,
    "discussion_messages_per_team": 3,
    "judge_assistant_enabled": True,
    "agent_settings": DEFAULT_AGENT_SETTINGS,
    "role_models": DEFAULT_ROLE_MODELS,
    "temperature": 0.55,
    "max_tokens": 700,
    "debate_tone": "Academic",
    "language": "English",
    "response_length": "Normal",
    "auto_scroll": True,
    "show_timestamps": False,
    "show_token_count": False,
    "show_money_cost": True,
    "cost_currency": "USD",
    "show_model_costs": False,
    "show_every_message_cost_in_debate": False,
    "context_window": 2,
    "debate_rounds": DEFAULT_DEBATE_ROUNDS,
    "researcher_web_search": False,
    "fact_check_mode": False,
    "export_format": "Markdown",
    "auto_save_interval": 30,
    "use_experience": True,
    "judge_mode": "Hybrid",
    "evidence_strictness": "Normal",
    "practice_settings": {
        "human_side": "Auto",
        "practice_flow": "Free",
        "structured_rounds": 3,
        "use_user_profile": True,
        "trainer_style": "Coach",
        "training_focus": "Full Debate",
        "opponent_difficulty": "Adaptive",
    },
    "judging_settings": {
        "judge_panel_size": 1,
        "analytics_weight": 0.25,
        "allow_user_verdict_challenge": True,
    },
}
DEFAULT_USER_DEBATE_PROFILE = {
    "version": 1,
    "debates_completed": 0,
    "practice_debates_completed": 0,
    "wins": {"pro": 0, "con": 0, "unclear": 0},
    "side_history": {"pro": 0, "con": 0, "auto": 0},
    "strengths": [],
    "weaknesses": [],
    "trainer_notes": [],
    "style_tags": [],
    "last_updated_at": "",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def debate_row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    payload = dict(row)
    raw_metadata = payload.get("metadata")
    if raw_metadata:
        try:
            payload["metadata"] = json.loads(raw_metadata)
        except json.JSONDecodeError:
            payload["metadata"] = {}
    else:
        payload["metadata"] = {}
    return payload


def message_row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("cost_summary", "debate_cost_summary"):
        raw_summary = payload.get(key)
        if raw_summary:
            try:
                payload[key] = json.loads(raw_summary)
            except json.JSONDecodeError:
                payload[key] = None
        else:
            payload[key] = None
    return payload


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            if immediate:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self) -> None:
        with self.lock, self.session(immediate=True) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'ai_vs_ai',
                    ai_a_model TEXT NOT NULL DEFAULT '',
                    ai_b_model TEXT NOT NULL DEFAULT '',
                    judge_model TEXT NOT NULL DEFAULT '',
                    rounds INTEGER NOT NULL DEFAULT 2,
                    default_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_settings (
                    session_id TEXT PRIMARY KEY,
                    overall_model TEXT NOT NULL DEFAULT '',
                    debaters_per_team INTEGER NOT NULL DEFAULT 2,
                    discussion_messages_per_team INTEGER NOT NULL DEFAULT 3,
                    judge_assistant_enabled INTEGER NOT NULL DEFAULT 1,
                    agent_settings TEXT NOT NULL DEFAULT '{}',
                    role_models TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    max_tokens INTEGER NOT NULL,
                    debate_tone TEXT NOT NULL,
                    language TEXT NOT NULL,
                    response_length TEXT NOT NULL,
                    auto_scroll INTEGER NOT NULL,
                    show_timestamps INTEGER NOT NULL,
                    show_token_count INTEGER NOT NULL,
                    show_money_cost INTEGER NOT NULL DEFAULT 1,
                    cost_currency TEXT NOT NULL DEFAULT 'USD',
                    show_model_costs INTEGER NOT NULL DEFAULT 0,
                    show_every_message_cost_in_debate INTEGER NOT NULL DEFAULT 0,
                    context_window INTEGER NOT NULL,
                    debate_rounds INTEGER NOT NULL,
                    researcher_web_search INTEGER NOT NULL,
                    fact_check_mode INTEGER NOT NULL,
                    export_format TEXT NOT NULL,
                    auto_save_interval INTEGER NOT NULL,
                    use_experience INTEGER NOT NULL DEFAULT 1,
                    judge_mode TEXT NOT NULL DEFAULT 'Hybrid',
                    evidence_strictness TEXT NOT NULL DEFAULT 'Normal',
                    practice_settings TEXT NOT NULL DEFAULT '{}',
                    judging_settings TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS debates (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    default_index INTEGER NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL DEFAULT 'debate',
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    judge_summary TEXT,
                    error TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    hidden_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    debate_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    model TEXT NOT NULL,
                    content TEXT NOT NULL,
                    cost_summary TEXT,
                    debate_cost_summary TEXT,
                    phase_key TEXT,
                    phase_title TEXT,
                    phase_index INTEGER,
                    phase_total INTEGER,
                    phase_kind TEXT,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    hidden_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY(debate_id) REFERENCES debates(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_sequence
                    ON messages(session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_messages_debate_id
                    ON messages(debate_id);
                CREATE TABLE IF NOT EXISTS debate_intelligence (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    debate_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    team TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    agent_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL DEFAULT '{}',
                    basis TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    hidden_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY(debate_id) REFERENCES debates(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_experience (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    session_id TEXT,
                    agent_id TEXT NOT NULL,
                    lesson_type TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    confidence TEXT NOT NULL DEFAULT 'low',
                    basis TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    hidden_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS post_debate_feedback (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    debate_id TEXT NOT NULL,
                    question_key TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY(debate_id) REFERENCES debates(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_debates_session_started
                    ON debates(session_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_intelligence_debate
                    ON debate_intelligence(session_id, debate_id, record_type);
                CREATE INDEX IF NOT EXISTS idx_experience_agent
                    ON agent_experience(scope, session_id, agent_id);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO app_metadata (key, value)
                VALUES (?, '0')
                """,
                (SESSION_COUNTER_KEY,),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO app_metadata (key, value)
                VALUES (?, ?)
                """,
                (COUNCIL_SETTINGS_KEY, json.dumps(DEFAULT_COUNCIL_SETTINGS)),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO app_metadata (key, value)
                VALUES (?, ?)
                """,
                (USER_DEBATE_PROFILE_KEY, json.dumps(DEFAULT_USER_DEBATE_PROFILE)),
            )
            connection.execute(
                """
                UPDATE app_metadata
                SET value = (
                    SELECT CAST(COALESCE(MAX(default_index), 0) AS TEXT)
                    FROM sessions
                )
                WHERE key = ?
                  AND CAST(value AS INTEGER) < (
                    SELECT COALESCE(MAX(default_index), 0)
                    FROM sessions
                  )
                """,
                (SESSION_COUNTER_KEY,),
            )
            self._ensure_settings_schema(connection)
            self._ensure_history_schema(connection)
            self._ensure_session_schema(connection)
            rows = connection.execute("SELECT id FROM sessions").fetchall()
            for row in rows:
                self._ensure_settings(connection, row["id"])

    def _ensure_session_schema(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "mode" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'ai_vs_ai'"
            )
        if "ai_a_model" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN ai_a_model TEXT NOT NULL DEFAULT ''"
            )
        if "ai_b_model" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN ai_b_model TEXT NOT NULL DEFAULT ''"
            )
        if "judge_model" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN judge_model TEXT NOT NULL DEFAULT ''"
            )
        if "rounds" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN rounds INTEGER NOT NULL DEFAULT 2"
            )

    def _ensure_settings_schema(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(session_settings)").fetchall()
        }
        if "overall_model" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN overall_model TEXT NOT NULL DEFAULT ''"
            )
        if "debaters_per_team" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN debaters_per_team INTEGER NOT NULL DEFAULT 2"
            )
        if "discussion_messages_per_team" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN discussion_messages_per_team INTEGER NOT NULL DEFAULT 3"
            )
        if "judge_assistant_enabled" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN judge_assistant_enabled INTEGER NOT NULL DEFAULT 1"
            )
        if "agent_settings" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN agent_settings TEXT NOT NULL DEFAULT '{}'"
            )
        if "show_money_cost" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN show_money_cost INTEGER NOT NULL DEFAULT 1"
            )
        if "cost_currency" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN cost_currency TEXT NOT NULL DEFAULT 'USD'"
            )
        if "show_model_costs" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN show_model_costs INTEGER NOT NULL DEFAULT 0"
            )
        if "show_every_message_cost_in_debate" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN show_every_message_cost_in_debate INTEGER NOT NULL DEFAULT 0"
            )
        if "use_experience" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN use_experience INTEGER NOT NULL DEFAULT 1"
            )
        if "judge_mode" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN judge_mode TEXT NOT NULL DEFAULT 'Hybrid'"
            )
        if "evidence_strictness" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN evidence_strictness TEXT NOT NULL DEFAULT 'Normal'"
            )
        if "practice_settings" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN practice_settings TEXT NOT NULL DEFAULT '{}'"
            )
        if "judging_settings" not in columns:
            connection.execute(
                "ALTER TABLE session_settings ADD COLUMN judging_settings TEXT NOT NULL DEFAULT '{}'"
            )

    def _ensure_history_schema(self, connection: sqlite3.Connection) -> None:
        debate_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(debates)").fetchall()
        }
        if "hidden_at" not in debate_columns:
            connection.execute("ALTER TABLE debates ADD COLUMN hidden_at TEXT")
        if "name" not in debate_columns:
            connection.execute("ALTER TABLE debates ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        if "default_index" not in debate_columns:
            connection.execute(
                "ALTER TABLE debates ADD COLUMN default_index INTEGER NOT NULL DEFAULT 0"
            )
        if "mode" not in debate_columns:
            connection.execute(
                "ALTER TABLE debates ADD COLUMN mode TEXT NOT NULL DEFAULT 'debate'"
            )
        if "metadata" not in debate_columns:
            connection.execute("ALTER TABLE debates ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")

        debate_rows = connection.execute(
            "SELECT id, session_id, started_at FROM debates ORDER BY session_id, started_at ASC"
        ).fetchall()
        index_by_session: dict[str, int] = {}
        for row in debate_rows:
            session_id = row["session_id"]
            index_by_session[session_id] = index_by_session.get(session_id, 0) + 1
            debate_index = index_by_session[session_id]
            role_counts = {
                item["role"]: item["total"]
                for item in connection.execute(
                    """
                    SELECT role, COUNT(*) AS total
                    FROM messages
                    WHERE debate_id = ?
                    GROUP BY role
                    """,
                    (row["id"],),
                ).fetchall()
            }
            roles = set(role_counts)
            is_practice = bool(
                roles & {"practice_user", "practice_debater", "debate_trainer"}
            )
            is_chat_only = bool(roles) and roles <= {"user", "assistant"}
            inferred_mode = "practice" if is_practice else ("chat" if is_chat_only else "debate")
            inferred_prefix = (
                DEFAULT_PRACTICE_PREFIX if inferred_mode == "practice" else DEFAULT_DEBATE_PREFIX
            )
            connection.execute(
                """
                UPDATE debates
                SET name = CASE WHEN name = '' THEN ? ELSE name END,
                    default_index = CASE WHEN default_index = 0 THEN ? ELSE default_index END,
                    mode = CASE
                        WHEN mode = '' THEN ?
                        WHEN mode = 'chat' AND ? != 'chat' THEN ?
                        WHEN mode NOT IN ('debate', 'chat', 'practice') THEN ?
                        ELSE mode
                    END
                WHERE id = ?
                """,
                (
                    f"{inferred_prefix}{debate_index}",
                    debate_index,
                    inferred_mode,
                    inferred_mode,
                    inferred_mode,
                    inferred_mode,
                    row["id"],
                ),
            )

        message_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "hidden_at" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN hidden_at TEXT")
        if "cost_summary" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN cost_summary TEXT")
        if "debate_cost_summary" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN debate_cost_summary TEXT")
        if "phase_key" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN phase_key TEXT")
        if "phase_title" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN phase_title TEXT")
        if "phase_index" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN phase_index INTEGER")
        if "phase_total" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN phase_total INTEGER")
        if "phase_kind" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN phase_kind TEXT")


    def _json_payload(self, value: object, default: object) -> object:
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            return default

    def _intelligence_row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        payload = dict(row)
        payload["payload"] = self._json_payload(payload.get("payload"), {})
        payload["basis"] = self._json_payload(payload.get("basis"), [])
        return payload

    def _experience_row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        payload = dict(row)
        payload["basis"] = self._json_payload(payload.get("basis"), [])
        return payload

    def _council_settings_from_connection(self, connection: sqlite3.Connection) -> dict:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", (COUNCIL_SETTINGS_KEY,)
        ).fetchone()
        if not row:
            return DEFAULT_COUNCIL_SETTINGS.copy()
        return self._normalize_council_settings(self._json_payload(row["value"], {}))

    def get_council_settings(self) -> dict:
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (COUNCIL_SETTINGS_KEY,)
            ).fetchone()
            try:
                raw = json.loads(row["value"] or "{}") if row else {}
            except json.JSONDecodeError:
                raw = {}
            return self._normalize_council_settings(raw)

    def update_council_settings(self, updates: dict) -> dict:
        allowed = set(DEFAULT_COUNCIL_SETTINGS)
        cleaned = {key: value for key, value in updates.items() if key in allowed}
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (COUNCIL_SETTINGS_KEY,)
            ).fetchone()
            try:
                current = json.loads(row["value"] or "{}") if row else {}
            except json.JSONDecodeError:
                current = {}
            if isinstance(cleaned.get("confirmation_preferences"), dict):
                current_preferences = (
                    current.get("confirmation_preferences")
                    if isinstance(current.get("confirmation_preferences"), dict)
                    else {}
                )
                cleaned = {
                    **cleaned,
                    "confirmation_preferences": {
                        **current_preferences,
                        **cleaned["confirmation_preferences"],
                    },
                }
            next_settings = self._normalize_council_settings({**current, **cleaned})
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (COUNCIL_SETTINGS_KEY, json.dumps(next_settings)),
            )
            return next_settings

    def _normalize_council_settings(self, payload: dict) -> dict:
        merged = {**DEFAULT_COUNCIL_SETTINGS, **(payload or {})}
        raw_preferences = merged.get("confirmation_preferences")
        preferences = (
            raw_preferences
            if isinstance(raw_preferences, dict)
            else DEFAULT_CONFIRMATION_PREFERENCES
        )
        return {
            "universal_experience": bool(merged.get("universal_experience", True)),
            "use_agent_identity_profiles": bool(merged.get("use_agent_identity_profiles", True)),
            "use_user_debate_profile": bool(merged.get("use_user_debate_profile", True)),
            "debate_intelligence_depth": self._normalize_choice(
                merged.get("debate_intelligence_depth", "Normal"),
                COUNCIL_SETTING_CHOICES["debate_intelligence_depth"],
                "Normal",
            ),
            "use_value_consequence_system": bool(
                merged.get("use_value_consequence_system", True)
            ),
            "default_judge_mode": self._normalize_choice(
                merged.get("default_judge_mode", "Hybrid"),
                COUNCIL_SETTING_CHOICES["default_judge_mode"],
                "Hybrid",
            ),
            "theme": self._normalize_choice(
                merged.get("theme", "Light"),
                COUNCIL_SETTING_CHOICES["theme"],
                "Light",
            ),
            "confirmation_preferences": {
                key: bool(preferences.get(key, default_value))
                for key, default_value in DEFAULT_CONFIRMATION_PREFERENCES.items()
            },
        }

    def get_user_debate_profile(self) -> dict:
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (USER_DEBATE_PROFILE_KEY,)
            ).fetchone()
            raw = self._json_payload(row["value"], {}) if row else {}
            return self._normalize_user_debate_profile(raw)

    def update_user_debate_profile(self, updates: dict) -> dict:
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (USER_DEBATE_PROFILE_KEY,)
            ).fetchone()
            current = self._normalize_user_debate_profile(
                self._json_payload(row["value"], {}) if row else {}
            )
            next_profile = self._normalize_user_debate_profile({**current, **updates})
            next_profile["last_updated_at"] = utc_now()
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (USER_DEBATE_PROFILE_KEY, json.dumps(next_profile)),
            )
            return next_profile

    def reset_user_debate_profile(self) -> dict:
        with self.lock, self.session() as connection:
            next_profile = {**DEFAULT_USER_DEBATE_PROFILE, "last_updated_at": utc_now()}
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (USER_DEBATE_PROFILE_KEY, json.dumps(next_profile)),
            )
            return next_profile

    def _normalize_user_debate_profile(self, payload: object) -> dict:
        raw = payload if isinstance(payload, dict) else {}
        merged = {**DEFAULT_USER_DEBATE_PROFILE, **raw}
        wins = merged.get("wins") if isinstance(merged.get("wins"), dict) else {}
        side_history = (
            merged.get("side_history") if isinstance(merged.get("side_history"), dict) else {}
        )
        return {
            "version": 1,
            "debates_completed": self._bounded_int(
                merged.get("debates_completed", 0), 0, 0, 1_000_000
            ),
            "practice_debates_completed": self._bounded_int(
                merged.get("practice_debates_completed", 0), 0, 0, 1_000_000
            ),
            "wins": {
                key: self._bounded_int(wins.get(key, 0), 0, 0, 1_000_000)
                for key in ("pro", "con", "unclear")
            },
            "side_history": {
                key: self._bounded_int(side_history.get(key, 0), 0, 0, 1_000_000)
                for key in ("pro", "con", "auto")
            },
            "strengths": self._bounded_string_list(merged.get("strengths"), 18),
            "weaknesses": self._bounded_string_list(merged.get("weaknesses"), 18),
            "trainer_notes": self._bounded_string_list(merged.get("trainer_notes"), 30),
            "style_tags": self._bounded_string_list(merged.get("style_tags"), 12),
            "last_updated_at": str(merged.get("last_updated_at", "")),
        }

    def _bounded_string_list(self, value: object, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            text = " ".join(str(item).split()).strip()
            if text and text not in cleaned:
                cleaned.append(text[:260])
            if len(cleaned) >= limit:
                break
        return cleaned

    def list_sessions(self) -> list[dict]:
        with self.lock, self.session() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM sessions
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row_to_dict(row)

    def create_session(
        self,
        max_sessions: int,
        *,
        mode: str = "ai_vs_ai",
        ai_a_model: str = "",
        ai_b_model: str = "",
        judge_model: str = "",
        rounds: int = 2,
        settings_updates: dict | None = None,
    ) -> dict:
        cleaned_mode = mode if mode in CHAT_MODES else "ai_vs_ai"
        with self.lock, self.session(immediate=True) as connection:
            session_count = connection.execute(
                "SELECT COUNT(*) AS total FROM sessions"
            ).fetchone()["total"]
            if session_count >= max_sessions:
                to_delete_count = session_count - max_sessions + 1
                oldest_sessions = connection.execute(
                    "SELECT id FROM sessions ORDER BY updated_at ASC LIMIT ?",
                    (to_delete_count,)
                ).fetchall()
                for old in oldest_sessions:
                    connection.execute("DELETE FROM sessions WHERE id = ?", (old["id"],))
                session_count = connection.execute(
                    "SELECT COUNT(*) AS total FROM sessions"
                ).fetchone()["total"]

            # Monotonic while any chat exists; reset only after the last chat is deleted.
            if session_count == 0:
                counter = 0
            else:
                counter = int(
                    connection.execute(
                        "SELECT value FROM app_metadata WHERE key = ?",
                        (SESSION_COUNTER_KEY,),
                    ).fetchone()["value"]
                )

            counter += 1
            now = utc_now()
            session_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO sessions (id, name, mode, default_index, created_at, updated_at, ai_a_model, ai_b_model, judge_model, rounds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    f"{DEFAULT_SESSION_PREFIX}{counter}",
                    cleaned_mode,
                    counter,
                    now,
                    now,
                    ai_a_model,
                    ai_b_model,
                    judge_model,
                    rounds,
                ),
            )
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (SESSION_COUNTER_KEY, str(counter)),
            )
            self._ensure_settings(connection, session_id)
            if settings_updates:
                current = self._settings_row_to_dict(
                    connection.execute(
                        "SELECT * FROM session_settings WHERE session_id = ?", (session_id,)
                    ).fetchone()
                )
                next_settings = self._normalize_settings({**(current or {}), **settings_updates})
                self._update_settings_from_connection(connection, session_id, next_settings)
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row_to_dict(row) or {}

    def _ensure_settings(self, connection: sqlite3.Connection, session_id: str) -> None:
        now = utc_now()
        council_defaults = self._council_settings_from_connection(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO session_settings (
                session_id,
                overall_model,
                debaters_per_team,
                discussion_messages_per_team,
                judge_assistant_enabled,
                agent_settings,
                role_models,
                temperature,
                max_tokens,
                debate_tone,
                language,
                response_length,
                auto_scroll,
                show_timestamps,
                show_token_count,
                show_money_cost,
                cost_currency,
                show_model_costs,
                show_every_message_cost_in_debate,
                context_window,
                debate_rounds,
                researcher_web_search,
                fact_check_mode,
                export_format,
                auto_save_interval,
                use_experience,
                judge_mode,
                evidence_strictness,
                practice_settings,
                judging_settings,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                DEFAULT_SESSION_SETTINGS["overall_model"],
                DEFAULT_SESSION_SETTINGS["debaters_per_team"],
                DEFAULT_SESSION_SETTINGS["discussion_messages_per_team"],
                int(DEFAULT_SESSION_SETTINGS["judge_assistant_enabled"]),
                json.dumps(DEFAULT_SESSION_SETTINGS["agent_settings"]),
                json.dumps(DEFAULT_SESSION_SETTINGS["role_models"]),
                DEFAULT_SESSION_SETTINGS["temperature"],
                DEFAULT_SESSION_SETTINGS["max_tokens"],
                DEFAULT_SESSION_SETTINGS["debate_tone"],
                DEFAULT_SESSION_SETTINGS["language"],
                DEFAULT_SESSION_SETTINGS["response_length"],
                int(DEFAULT_SESSION_SETTINGS["auto_scroll"]),
                int(DEFAULT_SESSION_SETTINGS["show_timestamps"]),
                int(DEFAULT_SESSION_SETTINGS["show_token_count"]),
                int(DEFAULT_SESSION_SETTINGS["show_money_cost"]),
                DEFAULT_SESSION_SETTINGS["cost_currency"],
                int(DEFAULT_SESSION_SETTINGS["show_model_costs"]),
                int(DEFAULT_SESSION_SETTINGS["show_every_message_cost_in_debate"]),
                DEFAULT_SESSION_SETTINGS["context_window"],
                DEFAULT_SESSION_SETTINGS["debate_rounds"],
                int(DEFAULT_SESSION_SETTINGS["researcher_web_search"]),
                int(DEFAULT_SESSION_SETTINGS["fact_check_mode"]),
                DEFAULT_SESSION_SETTINGS["export_format"],
                DEFAULT_SESSION_SETTINGS["auto_save_interval"],
                int(DEFAULT_SESSION_SETTINGS["use_experience"]),
                council_defaults["default_judge_mode"],
                DEFAULT_SESSION_SETTINGS["evidence_strictness"],
                json.dumps(DEFAULT_SESSION_SETTINGS["practice_settings"]),
                json.dumps(DEFAULT_SESSION_SETTINGS["judging_settings"]),
                now,
            ),
        )

    def get_session_settings(self, session_id: str) -> dict | None:
        with self.lock, self.session() as connection:
            if not connection.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone():
                return None
            self._ensure_settings(connection, session_id)
            row = connection.execute(
                "SELECT * FROM session_settings WHERE session_id = ?", (session_id,)
            ).fetchone()
            return self._settings_row_to_dict(row)

    def update_session_settings(self, session_id: str, updates: dict) -> dict | None:
        allowed = set(DEFAULT_SESSION_SETTINGS)
        cleaned = {key: value for key, value in updates.items() if key in allowed}
        if not cleaned:
            return self.get_session_settings(session_id)

        with self.lock, self.session() as connection:
            if not connection.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone():
                return None
            self._ensure_settings(connection, session_id)
            current = self._settings_row_to_dict(
                connection.execute(
                    "SELECT * FROM session_settings WHERE session_id = ?", (session_id,)
                ).fetchone()
            )
            next_settings = self._normalize_settings({**(current or {}), **cleaned})
            self._update_settings_from_connection(connection, session_id, next_settings)
            return next_settings

    def _update_settings_from_connection(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        next_settings: dict,
    ) -> None:
        connection.execute(
            """
            UPDATE session_settings
            SET overall_model = ?,
                debaters_per_team = ?,
                discussion_messages_per_team = ?,
                judge_assistant_enabled = ?,
                agent_settings = ?,
                role_models = ?,
                temperature = ?,
                max_tokens = ?,
                debate_tone = ?,
                language = ?,
                response_length = ?,
                auto_scroll = ?,
                show_timestamps = ?,
                show_token_count = ?,
                show_money_cost = ?,
                cost_currency = ?,
                show_model_costs = ?,
                show_every_message_cost_in_debate = ?,
                context_window = ?,
                debate_rounds = ?,
                researcher_web_search = ?,
                fact_check_mode = ?,
                export_format = ?,
                auto_save_interval = ?,
                use_experience = ?,
                judge_mode = ?,
                evidence_strictness = ?,
                practice_settings = ?,
                judging_settings = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                next_settings["overall_model"],
                next_settings["debaters_per_team"],
                next_settings["discussion_messages_per_team"],
                int(next_settings["judge_assistant_enabled"]),
                json.dumps(next_settings["agent_settings"]),
                json.dumps(next_settings["role_models"]),
                next_settings["temperature"],
                next_settings["max_tokens"],
                next_settings["debate_tone"],
                next_settings["language"],
                next_settings["response_length"],
                int(next_settings["auto_scroll"]),
                int(next_settings["show_timestamps"]),
                int(next_settings["show_token_count"]),
                int(next_settings["show_money_cost"]),
                next_settings["cost_currency"],
                int(next_settings["show_model_costs"]),
                int(next_settings["show_every_message_cost_in_debate"]),
                next_settings["context_window"],
                next_settings["debate_rounds"],
                int(next_settings["researcher_web_search"]),
                int(next_settings["fact_check_mode"]),
                next_settings["export_format"],
                next_settings["auto_save_interval"],
                int(next_settings["use_experience"]),
                next_settings["judge_mode"],
                next_settings["evidence_strictness"],
                json.dumps(next_settings["practice_settings"]),
                json.dumps(next_settings["judging_settings"]),
                utc_now(),
                session_id,
            ),
        )

    def _settings_row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        try:
            role_models = json.loads(row["role_models"] or "{}")
        except json.JSONDecodeError:
            role_models = {}
        try:
            agent_settings = json.loads(row["agent_settings"] or "{}")
        except json.JSONDecodeError:
            agent_settings = {}
        return self._normalize_settings(
            {
                "role_models": role_models,
                "overall_model": row["overall_model"],
                "debaters_per_team": row["debaters_per_team"],
                "discussion_messages_per_team": row["discussion_messages_per_team"],
                "judge_assistant_enabled": bool(row["judge_assistant_enabled"]),
                "agent_settings": agent_settings,
                "temperature": row["temperature"],
                "max_tokens": row["max_tokens"],
                "debate_tone": row["debate_tone"],
                "language": row["language"],
                "response_length": row["response_length"],
                "auto_scroll": bool(row["auto_scroll"]),
                "show_timestamps": bool(row["show_timestamps"]),
                "show_token_count": bool(row["show_token_count"]),
                "show_money_cost": bool(row["show_money_cost"]),
                "cost_currency": row["cost_currency"],
                "show_model_costs": bool(row["show_model_costs"]),
                "show_every_message_cost_in_debate": bool(row["show_every_message_cost_in_debate"]),
                "context_window": row["context_window"],
                "debate_rounds": row["debate_rounds"],
                "researcher_web_search": bool(row["researcher_web_search"]),
                "fact_check_mode": bool(row["fact_check_mode"]),
                "export_format": row["export_format"],
                "auto_save_interval": row["auto_save_interval"],
                "use_experience": bool(row["use_experience"]),
                "judge_mode": row["judge_mode"],
                "evidence_strictness": row["evidence_strictness"],
                "practice_settings": self._json_payload(row["practice_settings"], {}),
                "judging_settings": self._json_payload(row["judging_settings"], {}),
                "updated_at": row["updated_at"],
            }
        )

    def _normalize_settings(self, settings_payload: dict) -> dict:
        merged = {**DEFAULT_SESSION_SETTINGS, **settings_payload}
        role_models = self._normalize_role_models(merged.get("role_models") or {})
        agent_settings = self._normalize_agent_settings(
            merged.get("agent_settings") or {},
            role_models,
            merged,
        )
        return {
            "overall_model": str(merged.get("overall_model", "")).strip(),
            "debaters_per_team": max(1, min(4, int(merged.get("debaters_per_team", 2)))),
            "discussion_messages_per_team": max(1, min(4, int(merged.get("discussion_messages_per_team", 3)))),
            "judge_assistant_enabled": bool(merged.get("judge_assistant_enabled", True)),
            "agent_settings": agent_settings,
            "role_models": role_models,
            "temperature": max(0.0, min(1.0, float(merged.get("temperature", 0.55)))),
            "max_tokens": max(120, min(2000, int(merged.get("max_tokens", 700)))),
            "debate_tone": str(merged.get("debate_tone", "Academic")),
            "language": str(merged.get("language", "English")),
            "response_length": str(merged.get("response_length", "Normal")),
            "auto_scroll": bool(merged.get("auto_scroll", True)),
            "show_timestamps": bool(merged.get("show_timestamps", False)),
            "show_token_count": bool(merged.get("show_token_count", False)),
            "show_money_cost": bool(merged.get("show_money_cost", True)),
            "cost_currency": normalize_currency(str(merged.get("cost_currency", "USD"))),
            "show_model_costs": bool(merged.get("show_model_costs", False)),
            "show_every_message_cost_in_debate": bool(merged.get("show_every_message_cost_in_debate", False)),
            "context_window": max(0, min(6, int(merged.get("context_window", 2)))),
            "debate_rounds": max(1, min(6, int(merged.get("debate_rounds", 2)))),
            "researcher_web_search": bool(merged.get("researcher_web_search", False)),
            "fact_check_mode": bool(merged.get("fact_check_mode", False)),
            "export_format": str(merged.get("export_format", "Markdown")),
            "auto_save_interval": max(5, min(300, int(merged.get("auto_save_interval", 30)))),
            "use_experience": bool(merged.get("use_experience", True)),
            "judge_mode": self._normalize_choice(
                merged.get("judge_mode", "Hybrid"),
                {"Debate Performance", "Truth-Seeking", "Hybrid"},
                "Hybrid",
            ),
            "evidence_strictness": self._normalize_choice(
                merged.get("evidence_strictness", "Normal"),
                {"Relaxed", "Normal", "Strict"},
                "Normal",
            ),
            "practice_settings": self._normalize_practice_settings(
                merged.get("practice_settings") or {}
            ),
            "judging_settings": self._normalize_judging_settings(
                merged.get("judging_settings") or {}
            ),
            "updated_at": str(merged.get("updated_at", utc_now())),
        }

    def _normalize_judging_settings(self, payload: object) -> dict:
        raw = payload if isinstance(payload, dict) else {}
        merged = {**DEFAULT_SESSION_SETTINGS["judging_settings"], **raw}
        try:
            panel_size = int(merged.get("judge_panel_size", 1))
        except (TypeError, ValueError):
            panel_size = 1
        if panel_size not in {1, 3, 5}:
            panel_size = 1
        return {
            "judge_panel_size": panel_size,
            "analytics_weight": self._bounded_float(
                merged.get("analytics_weight", 0.25),
                0.25,
                0.0,
                0.75,
            ),
            "allow_user_verdict_challenge": bool(
                merged.get("allow_user_verdict_challenge", True)
            ),
        }

    def _normalize_practice_settings(self, payload: object) -> dict:
        raw = payload if isinstance(payload, dict) else {}
        merged = {**DEFAULT_SESSION_SETTINGS["practice_settings"], **raw}
        return {
            "human_side": self._normalize_choice(
                merged.get("human_side", "Auto"),
                {"Auto", "Pro", "Con"},
                "Auto",
            ),
            "practice_flow": self._normalize_choice(
                merged.get("practice_flow", "Free"),
                {"Free", "Structured"},
                "Free",
            ),
            "structured_rounds": self._bounded_int(
                merged.get("structured_rounds", 3),
                3,
                1,
                12,
            ),
            "use_user_profile": bool(merged.get("use_user_profile", True)),
            "trainer_style": self._normalize_choice(
                merged.get("trainer_style", "Coach"),
                {"Coach", "Direct", "Gentle", "Examiner"},
                "Coach",
            ),
            "training_focus": self._normalize_choice(
                merged.get("training_focus", "Full Debate"),
                {"Full Debate", "Rebuttal", "Evidence", "Clarity", "Cross-Examination"},
                "Full Debate",
            ),
            "opponent_difficulty": self._normalize_choice(
                merged.get("opponent_difficulty", "Adaptive"),
                {"Adaptive", "Beginner", "Normal", "Hard"},
                "Adaptive",
            ),
        }

    def _normalize_agent_settings(
        self,
        agent_payload: dict,
        role_models: dict,
        merged: dict,
    ) -> dict:
        normalized = {}
        for role in AGENT_ROLE_KEYS:
            base = DEFAULT_AGENT_SETTINGS[role]
            raw = agent_payload.get(role, {}) if isinstance(agent_payload, dict) else {}
            if not isinstance(raw, dict):
                raw = {}
            raw_model = str(raw.get("model", "")).strip()
            model = raw_model or role_models.get(role, "")
            normalized[role] = {
                "model": model,
                "temperature": self._bounded_float(
                    raw.get("temperature", merged.get("temperature", base["temperature"])),
                    base["temperature"],
                    0.0,
                    1.0,
                ),
                "max_tokens": self._bounded_int(
                    raw.get("max_tokens", merged.get("max_tokens", base["max_tokens"])),
                    base["max_tokens"],
                    120,
                    2000,
                ),
                "response_length": self._normalize_choice(
                    raw.get("response_length", merged.get("response_length", base["response_length"])),
                    {"Concise", "Normal", "Detailed"},
                    "Normal",
                ),
                "web_search": bool(raw.get("web_search", merged.get("researcher_web_search", base["web_search"]))),
                "always_on": bool(raw.get("always_on", base["always_on"])),
            }
        return normalized

    def _bounded_int(self, value: object, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(float(str(value).strip()))
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _bounded_float(self, value: object, default: float, minimum: float, maximum: float) -> float:
        try:
            parsed = float(str(value).strip())
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _normalize_role_models(self, role_models: dict) -> dict:
        normalized = {role: "" for role in AGENT_ROLE_KEYS}
        if not isinstance(role_models, dict):
            return normalized
        for raw_key, raw_value in role_models.items():
            role = LEGACY_ROLE_MODEL_ALIASES.get(str(raw_key), str(raw_key))
            if role in normalized:
                normalized[role] = str(raw_value).strip()
        return normalized

    def _normalize_choice(self, value: object, choices: set[str], default: str) -> str:
        cleaned = str(value).strip()
        return cleaned if cleaned in choices else default

    def rename_session(self, session_id: str, name: str) -> dict | None:
        cleaned = " ".join(name.strip().split())
        if not cleaned:
            raise ValueError("EMPTY_NAME")
        if len(cleaned) > 80:
            raise ValueError("NAME_TOO_LONG")

        with self.lock, self.session() as connection:
            now = utc_now()
            cursor = connection.execute(
                """
                UPDATE sessions
                SET name = ?, updated_at = ?
                WHERE id = ?
                """,
                (cleaned, now, session_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row_to_dict(row)

    def delete_session(self, session_id: str) -> bool:
        with self.lock, self.session(immediate=True) as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            deleted = cursor.rowcount > 0
            remaining = connection.execute(
                "SELECT COUNT(*) AS total FROM sessions"
            ).fetchone()["total"]
            if remaining == 0:
                connection.execute(
                    """
                    INSERT INTO app_metadata (key, value)
                    VALUES (?, '0')
                    ON CONFLICT(key) DO UPDATE SET value = '0'
                    """,
                    (SESSION_COUNTER_KEY,),
                )
            return deleted

    def delete_all_sessions(self) -> int:
        with self.lock, self.session(immediate=True) as connection:
            deleted = connection.execute("SELECT COUNT(*) AS total FROM sessions").fetchone()["total"]
            connection.execute("DELETE FROM sessions")
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES (?, '0')
                ON CONFLICT(key) DO UPDATE SET value = '0'
                """,
                (SESSION_COUNTER_KEY,),
            )
            return int(deleted)

    def update_session_models(
        self,
        session_id: str,
        ai_a_model: str | None = None,
        ai_b_model: str | None = None,
        judge_model: str | None = None,
        rounds: int | None = None,
    ) -> dict | None:
        with self.lock, self.session(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            
            updates = []
            params = []
            if ai_a_model is not None:
                updates.append("ai_a_model = ?")
                params.append(ai_a_model)
            if ai_b_model is not None:
                updates.append("ai_b_model = ?")
                params.append(ai_b_model)
            if judge_model is not None:
                updates.append("judge_model = ?")
                params.append(judge_model)
            if rounds is not None:
                updates.append("rounds = ?")
                params.append(rounds)
                
            if updates:
                updates.append("updated_at = ?")
                params.append(utc_now())
                params.append(session_id)
                connection.execute(
                    f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                    tuple(params),
                )
            
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row_to_dict(row)

    def touch_session(self, session_id: str) -> None:
        with self.lock, self.session() as connection:
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (utc_now(), session_id),
            )

    def create_debate(
        self,
        session_id: str,
        topic: str,
        *,
        mode: str = "debate",
        metadata: dict | None = None,
    ) -> dict:
        cleaned_mode = mode if mode in {"debate", "chat", "practice"} else "debate"
        with self.lock, self.session(immediate=True) as connection:
            now = utc_now()
            if not connection.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone():
                raise ValueError("SESSION_NOT_FOUND")
            debate_id = str(uuid4())
            if cleaned_mode in {"debate", "practice"}:
                prefix = DEFAULT_PRACTICE_PREFIX if cleaned_mode == "practice" else DEFAULT_DEBATE_PREFIX
                visible_debate_count = connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM debates
                    WHERE session_id = ?
                      AND mode = ?
                      AND hidden_at IS NULL
                    """,
                    (session_id, cleaned_mode),
                ).fetchone()["total"]
                if visible_debate_count == 0:
                    debate_index = 1
                else:
                    debate_index = (
                        connection.execute(
                            """
                            SELECT COALESCE(MAX(default_index), 0) + 1 AS next_index
                            FROM debates
                            WHERE session_id = ?
                              AND mode = ?
                            """,
                            (session_id, cleaned_mode),
                        ).fetchone()["next_index"]
                        or 1
                    )
                debate_name = f"{prefix}{debate_index}"
            else:
                debate_index = 0
                debate_name = "Council Assistant Chat"
            connection.execute(
                """
                INSERT INTO debates
                    (id, session_id, name, default_index, mode, topic, status, metadata, started_at, hidden_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, NULL)
                """,
                (
                    debate_id,
                    session_id,
                    debate_name,
                    debate_index,
                    cleaned_mode,
                    topic,
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            row = connection.execute(
                "SELECT * FROM debates WHERE id = ?", (debate_id,)
            ).fetchone()
            return debate_row_to_dict(row) or {}

    def complete_debate(self, debate_id: str, judge_summary: str) -> None:
        with self.lock, self.session() as connection:
            connection.execute(
                """
                UPDATE debates
                SET status = 'completed', judge_summary = ?, finished_at = ?
                WHERE id = ?
                """,
                (judge_summary, utc_now(), debate_id),
            )

    def fail_debate(self, debate_id: str, error: str) -> None:
        with self.lock, self.session() as connection:
            connection.execute(
                """
                UPDATE debates
                SET status = 'failed', error = ?, finished_at = ?
                WHERE id = ?
                """,
                (error[:1000], utc_now(), debate_id),
            )

    def update_debate_metadata(self, debate_id: str, updates: dict) -> dict | None:
        with self.lock, self.session(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM debates WHERE id = ?", (debate_id,)
            ).fetchone()
            current = debate_row_to_dict(row)
            if not current:
                return None
            metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
            next_metadata = {**metadata, **updates}
            connection.execute(
                """
                UPDATE debates
                SET metadata = ?
                WHERE id = ?
                """,
                (json.dumps(next_metadata), debate_id),
            )
            updated = connection.execute(
                "SELECT * FROM debates WHERE id = ?", (debate_id,)
            ).fetchone()
            return debate_row_to_dict(updated)

    def list_debates(self, session_id: str, *, include_hidden: bool = False) -> list[dict]:
        with self.lock, self.session() as connection:
            visibility_clause = "" if include_hidden else "AND hidden_at IS NULL"
            rows = connection.execute(
                f"""
                SELECT *
                FROM debates
                WHERE session_id = ?
                  AND mode IN ('debate', 'practice')
                  {visibility_clause}
                ORDER BY default_index DESC, started_at DESC
                """,
                (session_id,),
            ).fetchall()
            return [debate_row_to_dict(row) or {} for row in rows]

    def get_debate(
        self, session_id: str, debate_id: str, *, include_hidden: bool = False
    ) -> dict | None:
        with self.lock, self.session() as connection:
            visibility_clause = "" if include_hidden else "AND hidden_at IS NULL"
            row = connection.execute(
                f"""
                SELECT *
                FROM debates
                WHERE id = ?
                  AND session_id = ?
                  AND mode IN ('debate', 'practice')
                  {visibility_clause}
                """,
                (debate_id, session_id),
            ).fetchone()
            return debate_row_to_dict(row)

    def get_active_practice_debate(self, session_id: str) -> dict | None:
        with self.lock, self.session(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM debates
                WHERE session_id = ?
                  AND mode = 'practice'
                  AND status = 'running'
                  AND hidden_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return debate_row_to_dict(row)

    def rename_debate(self, session_id: str, debate_id: str, name: str) -> dict | None:
        cleaned = " ".join(name.strip().split())
        if not cleaned:
            raise ValueError("EMPTY_NAME")
        if len(cleaned) > 80:
            raise ValueError("NAME_TOO_LONG")

        with self.lock, self.session() as connection:
            cursor = connection.execute(
                """
                UPDATE debates
                SET name = ?
                WHERE id = ?
                  AND session_id = ?
                  AND mode IN ('debate', 'practice')
                  AND hidden_at IS NULL
                """,
                (cleaned, debate_id, session_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (utc_now(), session_id)
            )
            row = connection.execute(
                """
                SELECT *
                FROM debates
                WHERE id = ?
                  AND session_id = ?
                  AND mode IN ('debate', 'practice')
                  AND hidden_at IS NULL
                """,
                (debate_id, session_id),
            ).fetchone()
            return debate_row_to_dict(row)

    def hide_debate_statistics(self, session_id: str, debate_id: str) -> bool:
        with self.lock, self.session() as connection:
            now = utc_now()
            cursor = connection.execute(
                """
                UPDATE debates
                SET hidden_at = ?
                WHERE id = ?
                  AND session_id = ?
                  AND mode IN ('debate', 'practice')
                  AND hidden_at IS NULL
                """,
                (now, debate_id, session_id),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            return True

    def add_message(
        self,
        *,
        session_id: str,
        debate_id: str,
        role: str,
        speaker: str,
        model: str,
        content: str,
        cost_summary: dict | None = None,
        debate_cost_summary: dict | None = None,
        phase: dict | None = None,
    ) -> dict:
        with self.lock, self.session(immediate=True) as connection:
            sequence = (
                connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                    FROM messages
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()["next_sequence"]
                or 1
            )
            now = utc_now()
            message_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO messages
                    (id, session_id, debate_id, role, speaker, model, content, cost_summary, debate_cost_summary, phase_key, phase_title, phase_index, phase_total, phase_kind, sequence, created_at, hidden_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    message_id,
                    session_id,
                    debate_id,
                    role,
                    speaker,
                    model,
                    content,
                    json.dumps(cost_summary) if cost_summary else None,
                    json.dumps(debate_cost_summary) if debate_cost_summary else None,
                    phase.get("key") if isinstance(phase, dict) else None,
                    phase.get("title") if isinstance(phase, dict) else None,
                    phase.get("index") if isinstance(phase, dict) else None,
                    phase.get("total") if isinstance(phase, dict) else None,
                    phase.get("kind") if isinstance(phase, dict) else None,
                    sequence,
                    now,
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            return message_row_to_dict(row) or {}

    def list_messages(self, session_id: str, *, include_hidden: bool = False) -> list[dict]:
        with self.lock, self.session() as connection:
            visibility_clause = "" if include_hidden else "AND hidden_at IS NULL"
            rows = connection.execute(
                f"""
                SELECT *
                FROM messages
                WHERE session_id = ?
                  {visibility_clause}
                ORDER BY sequence ASC
                """,
                (session_id,),
            ).fetchall()
            return [message_row_to_dict(row) or {} for row in rows]

    def list_messages_for_debate(
        self, session_id: str, debate_id: str, *, include_hidden: bool = False
    ) -> list[dict]:
        with self.lock, self.session() as connection:
            visibility_clause = "" if include_hidden else "AND hidden_at IS NULL"
            rows = connection.execute(
                f"""
                SELECT *
                FROM messages
                WHERE session_id = ?
                  AND debate_id = ?
                  {visibility_clause}
                ORDER BY sequence ASC, created_at ASC
                """,
                (session_id, debate_id),
            ).fetchall()
            return [message_row_to_dict(row) or {} for row in rows]


    def add_intelligence_record(
        self,
        *,
        session_id: str,
        debate_id: str,
        record_type: str,
        title: str,
        content: str,
        team: str = "",
        role: str = "",
        agent_id: str = "",
        status: str = "",
        confidence: float = 0.0,
        payload: dict | None = None,
        basis: list | None = None,
    ) -> dict:
        with self.lock, self.session() as connection:
            now = utc_now()
            record_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO debate_intelligence
                    (id, session_id, debate_id, record_type, team, role, agent_id, title, content, status, confidence, payload, basis, created_at, updated_at, hidden_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    record_id,
                    session_id,
                    debate_id,
                    record_type,
                    team,
                    role,
                    agent_id,
                    title[:160],
                    content[:4000],
                    status[:80],
                    max(0.0, min(1.0, float(confidence))),
                    json.dumps(payload or {}),
                    json.dumps(basis or []),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM debate_intelligence WHERE id = ?", (record_id,)
            ).fetchone()
            return self._intelligence_row_to_dict(row) or {}

    def list_intelligence_records(self, session_id: str, debate_id: str | None = None) -> list[dict]:
        with self.lock, self.session() as connection:
            if debate_id:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM debate_intelligence
                    WHERE session_id = ?
                      AND debate_id = ?
                      AND hidden_at IS NULL
                    ORDER BY created_at ASC
                    """,
                    (session_id, debate_id),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM debate_intelligence
                    WHERE session_id = ?
                      AND hidden_at IS NULL
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            return [self._intelligence_row_to_dict(row) or {} for row in rows]

    def list_global_intelligence_records(
        self,
        *,
        record_types: tuple[str, ...] | None = None,
        limit: int = 60,
    ) -> list[dict]:
        clauses = ["hidden_at IS NULL"]
        params: list[object] = []
        if record_types:
            placeholders = ", ".join("?" for _ in record_types)
            clauses.append(f"record_type IN ({placeholders})")
            params.extend(record_types)
        query = f"""
            SELECT *
            FROM debate_intelligence
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """
        params.append(max(1, min(200, int(limit))))
        with self.lock, self.session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._intelligence_row_to_dict(row) or {} for row in rows]

    def update_intelligence_record(
        self,
        record_id: str,
        *,
        status: str | None = None,
        confidence: float | None = None,
        payload: dict | None = None,
        basis: list | None = None,
        content: str | None = None,
        title: str | None = None,
    ) -> dict | None:
        with self.lock, self.session() as connection:
            row = connection.execute(
                "SELECT * FROM debate_intelligence WHERE id = ? AND hidden_at IS NULL",
                (record_id,),
            ).fetchone()
            existing = self._intelligence_row_to_dict(row)
            if not existing:
                return None
            next_payload = existing["payload"] if payload is None else payload
            next_basis = existing["basis"] if basis is None else basis
            next_status = existing["status"] if status is None else status[:80]
            next_confidence = (
                existing["confidence"]
                if confidence is None
                else max(0.0, min(1.0, float(confidence)))
            )
            next_content = existing["content"] if content is None else content[:4000]
            next_title = existing["title"] if title is None else title[:160]
            connection.execute(
                """
                UPDATE debate_intelligence
                SET title = ?,
                    content = ?,
                    status = ?,
                    confidence = ?,
                    payload = ?,
                    basis = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_title,
                    next_content,
                    next_status,
                    next_confidence,
                    json.dumps(next_payload or {}),
                    json.dumps(next_basis or []),
                    utc_now(),
                    record_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM debate_intelligence WHERE id = ?", (record_id,)
            ).fetchone()
            return self._intelligence_row_to_dict(updated)

    def add_agent_experience(
        self,
        *,
        scope: str,
        agent_id: str,
        lesson_type: str,
        lesson: str,
        session_id: str | None = None,
        confidence: str = "low",
        basis: list | None = None,
    ) -> dict:
        cleaned_scope = "chat" if scope == "chat" else "universal"
        cleaned_confidence = confidence if confidence in {"low", "medium", "high"} else "low"
        with self.lock, self.session() as connection:
            now = utc_now()
            record_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO agent_experience
                    (id, scope, session_id, agent_id, lesson_type, lesson, confidence, basis, created_at, last_used_at, use_count, hidden_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
                """,
                (
                    record_id,
                    cleaned_scope,
                    session_id if cleaned_scope == "chat" else None,
                    agent_id,
                    lesson_type[:80],
                    lesson[:1200],
                    cleaned_confidence,
                    json.dumps(basis or []),
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM agent_experience WHERE id = ?", (record_id,)
            ).fetchone()
            return self._experience_row_to_dict(row) or {}

    def list_agent_experience(
        self,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        include_universal: bool = True,
        limit: int = 20,
    ) -> list[dict]:
        clauses = ["hidden_at IS NULL"]
        params: list[object] = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        scope_clauses = []
        if include_universal:
            scope_clauses.append("scope = 'universal'")
        if session_id:
            scope_clauses.append("(scope = 'chat' AND session_id = ?)")
            params.append(session_id)
        if scope_clauses:
            clauses.append("(" + " OR ".join(scope_clauses) + ")")
        elif not include_universal:
            return []
        query = f"""
            SELECT *
            FROM agent_experience
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(max(1, min(200, int(limit))))
        with self.lock, self.session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._experience_row_to_dict(row) or {} for row in rows]

    def list_global_agent_experience(self, *, limit: int = 200) -> list[dict]:
        with self.lock, self.session() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM agent_experience
                WHERE hidden_at IS NULL
                ORDER BY COALESCE(last_used_at, created_at) DESC, created_at DESC
                LIMIT ?
                """,
                (max(1, min(500, int(limit))),),
            ).fetchall()
            return [self._experience_row_to_dict(row) or {} for row in rows]

    def list_recent_debates_global(
        self,
        *,
        modes: tuple[str, ...] = ("debate", "practice"),
        limit: int = 24,
    ) -> list[dict]:
        valid_modes = tuple(mode for mode in modes if mode in {"debate", "practice", "chat"})
        if not valid_modes:
            return []
        placeholders = ", ".join("?" for _ in valid_modes)
        with self.lock, self.session() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM debates
                WHERE hidden_at IS NULL
                  AND mode IN ({placeholders})
                ORDER BY COALESCE(finished_at, started_at) DESC, started_at DESC
                LIMIT ?
                """,
                (*valid_modes, max(1, min(200, int(limit)))),
            ).fetchall()
            return [debate_row_to_dict(row) or {} for row in rows]

    def reset_agent_experience(
        self,
        *,
        scope: str = "universal",
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> int:
        clauses = ["hidden_at IS NULL"]
        params: list[object] = [utc_now()]
        if scope == "chat":
            clauses.append("scope = 'chat'")
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
        else:
            clauses.append("scope = 'universal'")
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        with self.lock, self.session() as connection:
            cursor = connection.execute(
                f"UPDATE agent_experience SET hidden_at = ? WHERE {' AND '.join(clauses)}",
                tuple(params),
            )
            return cursor.rowcount

    def add_post_debate_feedback(
        self, *, session_id: str, debate_id: str, question_key: str, answer: str
    ) -> dict:
        with self.lock, self.session() as connection:
            now = utc_now()
            record_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO post_debate_feedback (id, session_id, debate_id, question_key, answer, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, session_id, debate_id, question_key[:80], answer[:1200], now),
            )
            return {
                "id": record_id,
                "session_id": session_id,
                "debate_id": debate_id,
                "question_key": question_key,
                "answer": answer,
                "created_at": now,
            }

    def add_verdict_review(
        self,
        *,
        session_id: str,
        debate_id: str,
        action: str,
        winner: str,
        note: str,
    ) -> dict | None:
        action_value = action.strip().lower()
        winner_value = winner.strip().lower()
        if action_value not in {"challenge", "override"}:
            return None
        if winner_value not in {"pro", "con", "unclear"}:
            winner_value = "unclear"

        with self.lock, self.session() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM debates
                WHERE id = ?
                  AND session_id = ?
                  AND mode IN ('debate', 'practice')
                  AND hidden_at IS NULL
                """,
                (debate_id, session_id),
            ).fetchone()
            if not row:
                return None
            now = utc_now()
            metadata = self._json_payload(row["metadata"], {})
            reviews = metadata.get("verdict_reviews")
            if not isinstance(reviews, list):
                reviews = []
            review = {
                "id": str(uuid4()),
                "action": action_value,
                "winner": winner_value,
                "note": note.strip()[:1200],
                "created_at": now,
            }
            reviews.append(review)
            reviews = reviews[-20:]
            metadata["verdict_reviews"] = reviews
            if action_value == "override":
                metadata["user_verdict_override"] = {
                    "winner": winner_value,
                    "note": review["note"],
                    "created_at": now,
                    "review_id": review["id"],
                }
            elif action_value == "challenge":
                metadata["user_verdict_challenge"] = {
                    "winner": winner_value,
                    "note": review["note"],
                    "created_at": now,
                    "review_id": review["id"],
                }
            connection.execute(
                "UPDATE debates SET metadata = ? WHERE id = ?",
                (json.dumps(metadata), debate_id),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            return {
                **review,
                "session_id": session_id,
                "debate_id": debate_id,
            }

    def clear_visible_history(self, session_id: str) -> bool:
        with self.lock, self.session() as connection:
            if not connection.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone():
                return False

            now = utc_now()
            connection.execute(
                """
                UPDATE messages
                SET hidden_at = ?
                WHERE session_id = ?
                  AND hidden_at IS NULL
                """,
                (now, session_id),
            )
            connection.execute(
                """
                UPDATE debates
                SET hidden_at = ?
                WHERE session_id = ?
                  AND hidden_at IS NULL
                """,
                (now, session_id),
            )
            connection.execute("DELETE FROM post_debate_feedback WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM debate_intelligence WHERE session_id = ?", (session_id,))
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            return True

    def clear_memory(self, session_id: str) -> bool:
        with self.lock, self.session() as connection:
            if not connection.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone():
                return False

            now = utc_now()
            connection.execute("DELETE FROM post_debate_feedback WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM debate_intelligence WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM debates WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM agent_experience WHERE scope = 'chat' AND session_id = ?", (session_id,))
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            return True
