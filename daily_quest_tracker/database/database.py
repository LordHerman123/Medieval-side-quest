"""SQLite persistence for everything the player owns.

Uses only the standard library ``sqlite3`` module so it works unchanged on
desktop and on Android. Pass ``":memory:"`` as the path for tests.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from core.models import Completion, DailyQuest, Quest, QuestEvent
from database.models import (
    MIGRATIONS,
    SCHEMA,
    SCHEMA_VERSION,
    event_to_row,
    quest_to_json,
    row_to_completion,
    row_to_daily,
    row_to_event,
    rows_to_quests,
)

DB_FILENAME = "daily_quest_tracker.db"


def default_db_path() -> str:
    """Location used when no app data directory is supplied (desktop development)."""
    base = os.environ.get("DAILY_QUEST_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".daily_quest_tracker")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, DB_FILENAME)


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = path or default_db_path()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        # The weather service runs on a background thread, so allow cross-thread use
        # and serialise access ourselves.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # --- infrastructure ----------------------------------------------------
    def _migrate(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            version = int(row["value"]) if row else SCHEMA_VERSION
            for target in sorted(v for v in MIGRATIONS if v > version):
                conn.executescript(MIGRATIONS[target])
                version = target
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                         (str(max(version, SCHEMA_VERSION)),))
            conn.execute("INSERT OR IGNORE INTO player(id, xp, level, created_at) VALUES (1, 0, 1, ?)",
                         (time.time(),))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- settings ------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self._query("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def all_settings(self) -> Dict[str, Any]:
        return {row["key"]: json.loads(row["value"]) for row in self._query("SELECT key, value FROM settings")}

    # --- player --------------------------------------------------------------
    def get_player(self) -> Dict[str, Any]:
        row = self._query("SELECT xp, level, created_at FROM player WHERE id = 1")[0]
        return {"xp": row["xp"], "level": row["level"], "created_at": row["created_at"]}

    def set_player(self, xp: int, level: int) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE player SET xp = ?, level = ? WHERE id = 1", (xp, level))

    # --- custom quests -----------------------------------------------------------
    def save_custom_quest(self, quest: Quest) -> None:
        now = time.time()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO custom_quests(id, data, created_at, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at""",
                (quest.id, quest_to_json(quest), now, now))

    def delete_custom_quest(self, quest_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM custom_quests WHERE id = ?", (quest_id,))
            # Drop it from any still-open daily boards; history keeps its snapshot.
            conn.execute("DELETE FROM daily_quests WHERE quest_id = ? AND status IN ('offered', 'accepted')",
                         (quest_id,))

    def load_custom_quests(self) -> List[Quest]:
        return rows_to_quests(self._query("SELECT data FROM custom_quests ORDER BY created_at"))

    # --- quest events (preference tracking) ----------------------------------------
    def add_event(self, event: QuestEvent) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO quest_events(quest_id, event_type, timestamp, category, tags, difficulty, cost,
                   accessibility, environment, weather, pick_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                event_to_row(event))

    def load_events(self) -> List[QuestEvent]:
        return [row_to_event(r) for r in self._query("SELECT * FROM quest_events ORDER BY timestamp")]

    def count_events(self, event_type: str) -> int:
        return self._query("SELECT COUNT(*) AS n FROM quest_events WHERE event_type = ?", (event_type,))[0]["n"]

    # --- daily quest board --------------------------------------------------------
    def get_daily(self, date: str) -> List[DailyQuest]:
        rows = self._query("SELECT * FROM daily_quests WHERE date = ? ORDER BY position", (date,))
        return [row_to_daily(r) for r in rows]

    def save_daily(self, quests: List[DailyQuest]) -> None:
        now = time.time()
        with self.transaction() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO daily_quests(date, quest_id, slot, position, pick_type, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(d.date, d.quest_id, d.slot, d.position, d.pick_type, d.status, now) for d in quests])

    def update_daily_status(self, date: str, quest_id: str, status: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE daily_quests SET status = ?, updated_at = ? WHERE date = ? AND quest_id = ?",
                         (status, time.time(), date, quest_id))

    def daily_quest_ids_since(self, date: str) -> List[str]:
        return [r["quest_id"] for r in self._query("SELECT quest_id FROM daily_quests WHERE date >= ?", (date,))]

    # --- completions / journey ---------------------------------------------------------
    def add_completion(self, completion: Completion) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO completions(quest_id, title, category, difficulty, duration, xp, date, completed_at,
                   pick_type, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (completion.quest_id, completion.title, completion.category, completion.difficulty,
                 completion.duration, completion.xp, completion.date, completion.completed_at,
                 completion.pick_type, json.dumps(completion.tags)))
            return int(cur.lastrowid)

    def completions(self, limit: Optional[int] = None) -> List[Completion]:
        sql = "SELECT * FROM completions ORDER BY completed_at DESC"
        params: tuple = ()
        if limit:
            sql += " LIMIT ?"
            params = (limit,)
        return [row_to_completion(r) for r in self._query(sql, params)]

    # --- unlocks ---------------------------------------------------------------------
    def add_unlock(self, item_id: str, level: int) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO unlocks(item_id, level, unlocked_at) VALUES (?, ?, ?)",
                         (item_id, level, time.time()))

    def unlocks(self) -> Dict[str, float]:
        return {r["item_id"]: r["unlocked_at"] for r in self._query("SELECT * FROM unlocks ORDER BY unlocked_at")}

    # --- maintenance --------------------------------------------------------------
    def reset_progress(self, keep_custom_quests: bool = True, keep_settings: bool = True) -> None:
        with self.transaction() as conn:
            for table in ("quest_events", "daily_quests", "completions", "unlocks"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("UPDATE player SET xp = 0, level = 1, created_at = ? WHERE id = 1", (time.time(),))
            if not keep_custom_quests:
                conn.execute("DELETE FROM custom_quests")
            if not keep_settings:
                conn.execute("DELETE FROM settings")
