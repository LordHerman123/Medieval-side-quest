"""SQLite schema and row <-> domain object conversion.

Bump ``SCHEMA_VERSION`` and add a step to ``MIGRATIONS`` whenever the schema
changes, so existing players keep their progress.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Dict, List

from core.models import Completion, DailyQuest, Quest, QuestEvent

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_quests (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    category TEXT NOT NULL,
    tags TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    cost INTEGER NOT NULL,
    accessibility INTEGER NOT NULL,
    environment TEXT NOT NULL,
    weather TEXT,
    pick_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_type ON quest_events(event_type);

CREATE TABLE IF NOT EXISTS daily_quests (
    date TEXT NOT NULL,
    quest_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    position INTEGER NOT NULL,
    pick_type TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (date, quest_id)
);

CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    duration INTEGER NOT NULL,
    xp INTEGER NOT NULL,
    date TEXT NOT NULL,
    completed_at REAL NOT NULL,
    pick_type TEXT,
    tags TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS unlocks (
    item_id TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    unlocked_at REAL NOT NULL
);
"""

MIGRATIONS: Dict[int, str] = {
    # 2: "ALTER TABLE completions ADD COLUMN notes TEXT;",
}


def event_to_row(event: QuestEvent) -> tuple:
    return (event.quest_id, event.event_type, event.timestamp, event.category, json.dumps(event.tags),
            event.difficulty, event.cost, event.accessibility, event.environment, event.weather, event.pick_type)


def row_to_event(row: sqlite3.Row) -> QuestEvent:
    return QuestEvent(
        quest_id=row["quest_id"], event_type=row["event_type"], timestamp=row["timestamp"],
        category=row["category"], tags=json.loads(row["tags"]), difficulty=row["difficulty"],
        cost=row["cost"], accessibility=row["accessibility"], environment=row["environment"],
        weather=row["weather"], pick_type=row["pick_type"],
    )


def row_to_daily(row: sqlite3.Row) -> DailyQuest:
    return DailyQuest(date=row["date"], quest_id=row["quest_id"], slot=row["slot"], position=row["position"],
                      pick_type=row["pick_type"], status=row["status"])


def row_to_completion(row: sqlite3.Row) -> Completion:
    return Completion(
        id=row["id"], quest_id=row["quest_id"], title=row["title"], category=row["category"],
        difficulty=row["difficulty"], duration=row["duration"], xp=row["xp"], date=row["date"],
        completed_at=row["completed_at"], pick_type=row["pick_type"], tags=json.loads(row["tags"]),
    )


def quest_to_json(quest: Quest) -> str:
    return json.dumps(quest.to_dict())


def rows_to_quests(rows: List[sqlite3.Row]) -> List[Quest]:
    return [Quest.from_dict(json.loads(row["data"]), custom=True) for row in rows]
