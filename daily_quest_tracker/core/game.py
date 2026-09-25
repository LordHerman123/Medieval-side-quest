"""Application service: the single entry point the UI talks to.

It wires together the quest library, recommendation engine, preference
tracker, daily generator, leveling, progression and the database. It has no
Kivy dependency, so the whole game loop can be driven from tests or a shell.
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core import leveling
from core.daily_generator import DailyGenerator
from core.leveling import LevelInfo, XpAward
from core.models import (
    PICK_MANUAL,
    PICK_WILDCARD,
    STATUS_ABANDONED,
    STATUS_ACCEPTED,
    STATUS_COMPLETED,
    STATUS_OFFERED,
    STATUS_SKIPPED,
    Completion,
    DailyQuest,
    Quest,
    Weather,
)
from core.preference_tracker import (
    EVENT_ABANDONED,
    EVENT_ACCEPTED,
    EVENT_COMPLETED,
    EVENT_OFFERED,
    EVENT_REPLACED,
    EVENT_SELECTED,
    EVENT_SKIPPED,
    PreferenceTracker,
)
from core.progression import Item, Progression
from core.quest_engine import QuestLibrary
from core.recommendation_engine import Constraints, EngineConfig, RecommendationContext, RecommendationEngine
from core.statistics import Statistics, compute_statistics
from database.database import Database

DEFAULT_SETTINGS: Dict[str, Any] = {
    "secondary_count": 4,
    "max_cost": 3,
    "max_difficulty": 5,
    "allow_group_quests": True,
    "exploration": 0.3,  # share of novel + wildcard picks
    "weather_enabled": True,
    "location_name": "",
    "latitude": None,
    "longitude": None,
    "temperature_unit": "C",
}


@dataclass
class CompletionResult:
    quest: Quest
    award: XpAward
    old_level: int
    new_level: int
    new_items: List[Item] = field(default_factory=list)

    @property
    def leveled_up(self) -> bool:
        return self.new_level > self.old_level


class Game:
    def __init__(self, db: Database, library: Optional[QuestLibrary] = None,
                 progression: Optional[Progression] = None, engine_config: Optional[EngineConfig] = None,
                 now: Callable[[], datetime] = datetime.now):
        self.db = db
        self._now = now
        self.library = library or QuestLibrary.load()
        for quest in db.load_custom_quests():
            self.library.add_custom(quest)
        self.progression = progression or Progression.load()
        self.engine = RecommendationEngine(engine_config)
        self.tracker = PreferenceTracker(db, clock=lambda: self._now().timestamp())
        seed = db.get_setting("seed")
        if seed is None:
            seed = random.randint(0, 2 ** 31)
            db.set_setting("seed", seed)
        self.generator = DailyGenerator(self.library, self.engine, db, seed=seed)
        self.weather: Optional[Weather] = None
        self._apply_exploration()
        self._sync_unlocks()

    # --- settings ----------------------------------------------------------
    def setting(self, key: str) -> Any:
        return self.db.get_setting(key, DEFAULT_SETTINGS.get(key))

    def set_setting(self, key: str, value: Any) -> None:
        self.db.set_setting(key, value)
        if key == "exploration":
            self._apply_exploration()

    def _apply_exploration(self) -> None:
        exploration = max(0.0, min(0.8, float(self.setting("exploration"))))
        cfg = self.engine.config
        cfg.aligned_share = 1.0 - exploration
        cfg.novel_share = exploration * 2 / 3
        cfg.wildcard_share = exploration / 3

    def constraints(self) -> Constraints:
        return Constraints(max_cost=int(self.setting("max_cost")),
                           max_difficulty=int(self.setting("max_difficulty")),
                           allow_group_quests=bool(self.setting("allow_group_quests")))

    # --- time ---------------------------------------------------------------
    def now(self) -> datetime:
        return self._now()

    def today(self) -> str:
        return self._now().date().isoformat()

    def _timestamp(self) -> float:
        return self._now().timestamp()

    # --- player -------------------------------------------------------------
    @property
    def xp(self) -> int:
        return int(self.db.get_player()["xp"])

    def level_info(self) -> LevelInfo:
        return leveling.level_info(self.xp)

    @property
    def level(self) -> int:
        return self.level_info().level

    def title(self) -> str:
        return self.progression.title_for_level(self.level)

    def loadout(self) -> Dict[str, Item]:
        return self.progression.loadout(self.level)

    def _sync_unlocks(self) -> None:
        level = self.level
        owned = self.db.unlocks()
        for item in self.progression.unlocked_items(level):
            if item.id not in owned:
                self.db.add_unlock(item.id, item.level)

    # --- weather --------------------------------------------------------------
    def set_weather(self, weather: Optional[Weather]) -> None:
        self.weather = weather if self.setting("weather_enabled") else None

    def _weather_name(self) -> Optional[str]:
        return self.weather.condition if self.weather else None

    # --- recommendation context ----------------------------------------------------
    def context(self) -> RecommendationContext:
        now = self._now()
        return RecommendationContext(
            profile=self.tracker.profile(),
            weather=self.weather,
            now=now.timestamp(),
            local_hour=now.hour,
            level=self.level,
            constraints=self.constraints(),
        )

    # --- daily board ------------------------------------------------------------------
    def today_board(self) -> List[DailyQuest]:
        """Today's quests, generating them on the first call of the day."""
        date = self.today()
        if self.generator.has_board(date):
            return self.generator.board(date)
        board = self.generator.generate(date, self.context(), int(self.setting("secondary_count")))
        for entry in board:
            if entry.status == STATUS_OFFERED and entry.quest is not None:
                self.tracker.record(entry.quest, EVENT_OFFERED, self._weather_name(), entry.pick_type)
        return board

    def _entry(self, quest_id: str) -> DailyQuest:
        for entry in self.generator.board(self.today()):
            if entry.quest_id == quest_id:
                return entry
        raise KeyError(f"{quest_id} is not on today's board")

    def accept(self, quest_id: str) -> DailyQuest:
        entry = self._entry(quest_id)
        if entry.status == STATUS_OFFERED:
            self.generator.set_status(entry.date, quest_id, STATUS_ACCEPTED)
            self.tracker.record(entry.quest, EVENT_ACCEPTED, self._weather_name(), entry.pick_type)
            entry.status = STATUS_ACCEPTED
        return entry

    def skip(self, quest_id: str) -> DailyQuest:
        entry = self._entry(quest_id)
        if entry.is_open:
            self.generator.set_status(entry.date, quest_id, STATUS_SKIPPED)
            self.tracker.record(entry.quest, EVENT_SKIPPED, self._weather_name(), entry.pick_type)
            entry.status = STATUS_SKIPPED
        return entry

    def abandon(self, quest_id: str) -> DailyQuest:
        entry = self._entry(quest_id)
        if entry.status == STATUS_ACCEPTED:
            self.generator.set_status(entry.date, quest_id, STATUS_ABANDONED)
            self.tracker.record(entry.quest, EVENT_ABANDONED, self._weather_name(), entry.pick_type)
            entry.status = STATUS_ABANDONED
        return entry

    def replace(self, quest_id: str) -> Optional[DailyQuest]:
        entry = self._entry(quest_id)
        if not entry.is_open:
            return None
        new_entry = self.generator.replace(entry.date, quest_id, self.context())
        if new_entry is not None:
            self.tracker.record(entry.quest, EVENT_REPLACED, self._weather_name(), entry.pick_type)
            self.tracker.record(new_entry.quest, EVENT_OFFERED, self._weather_name(), new_entry.pick_type)
        return new_entry

    def select_manually(self, quest_id: str) -> DailyQuest:
        quest = self.library.get(quest_id)
        if quest is None:
            raise KeyError(quest_id)
        entry = self.generator.add_manual(self.today(), quest)
        self.tracker.record(quest, EVENT_SELECTED, self._weather_name(), PICK_MANUAL)
        return entry

    def complete(self, quest_id: str) -> CompletionResult:
        entry = self._entry(quest_id)
        if entry.status == STATUS_COMPLETED:
            raise ValueError("Quest already completed")
        quest = entry.quest
        profile = self.tracker.profile()
        award = leveling.completion_award(
            quest.xp,
            is_wildcard=entry.pick_type == PICK_WILDCARD,
            is_new_category=quest.category not in profile.explored_categories,
        )
        old_level = self.level
        new_xp = self.xp + award.total
        new_level = leveling.level_for_xp(new_xp)

        self.db.set_player(new_xp, new_level)
        self.db.add_completion(Completion(
            quest_id=quest.id, title=quest.title, category=quest.category, difficulty=quest.difficulty,
            duration=quest.duration, xp=award.total, date=entry.date, completed_at=self._timestamp(),
            pick_type=entry.pick_type, tags=list(quest.tags)))
        self.generator.set_status(entry.date, quest_id, STATUS_COMPLETED)
        self.tracker.record(quest, EVENT_COMPLETED, self._weather_name(), entry.pick_type)

        new_items = self.progression.newly_unlocked(old_level, new_level)
        for item in new_items:
            self.db.add_unlock(item.id, item.level)
        return CompletionResult(quest=quest, award=award, old_level=old_level, new_level=new_level,
                                new_items=new_items)

    # --- custom quests ------------------------------------------------------------------
    def save_custom_quest(self, data: Dict[str, Any], quest_id: Optional[str] = None) -> Quest:
        """Create (or update when ``quest_id`` is given) a user quest. Raises QuestValidationError."""
        payload = dict(data)
        payload["id"] = quest_id or f"custom_{uuid.uuid4().hex[:10]}"
        if isinstance(payload.get("tags"), str):
            payload["tags"] = [t for t in re.split(r"[,;]", payload["tags"]) if t.strip()]
        payload["xp"] = 0  # always derive XP from difficulty and duration
        quest = Quest.from_dict(payload, custom=True)
        self.db.save_custom_quest(quest)
        self.library.add_custom(quest)
        return quest

    def delete_custom_quest(self, quest_id: str) -> None:
        quest = self.library.get(quest_id)
        if quest is None or not quest.custom:
            raise KeyError(f"{quest_id} is not a custom quest")
        self.db.delete_custom_quest(quest_id)
        self.library.remove_custom(quest_id)

    # --- history & statistics -----------------------------------------------------------
    def journey(self, limit: Optional[int] = None) -> List[Completion]:
        return self.db.completions(limit)

    def statistics(self) -> Statistics:
        info = self.level_info()
        return compute_statistics(
            self.db.completions(),
            xp=info.xp,
            level=info.level,
            title=self.progression.title_for_level(info.level),
            categories_total=len(self.library.category_names),
            skipped=self.db.count_events(EVENT_SKIPPED) + self.db.count_events(EVENT_REPLACED),
            custom_quests=len(self.library.custom_quests),
        )

    def reset_progress(self) -> None:
        self.db.reset_progress()
        self.tracker.invalidate()
        self._sync_unlocks()
