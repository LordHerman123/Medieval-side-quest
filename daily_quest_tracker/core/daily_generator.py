"""Builds and maintains the daily quest board.

A board is generated once per day and persisted, so reopening the app shows
the same quests. Generation is seeded by the date, which makes it
reproducible (and testable) while still varying day to day.
"""

from __future__ import annotations

import random
from datetime import date as date_cls, timedelta
from typing import List, Optional, Protocol

from core.models import (
    PICK_ALIGNED,
    PICK_MANUAL,
    SLOT_PRIORITY,
    SLOT_SECONDARY,
    STATUS_ACCEPTED,
    STATUS_COMPLETED,
    STATUS_OFFERED,
    STATUS_REPLACED,
    DailyQuest,
    Quest,
)
from core.quest_engine import QuestLibrary
from core.recommendation_engine import RecommendationContext, RecommendationEngine

STATUS_CARRIED = "carried"
CARRY_OVER_DAYS = 3


class DailyStore(Protocol):
    def get_daily(self, date: str) -> List[DailyQuest]: ...

    def save_daily(self, quests: List[DailyQuest]) -> None: ...

    def update_daily_status(self, date: str, quest_id: str, status: str) -> None: ...


def day_rng(seed: object, date: str, salt: object = "") -> random.Random:
    return random.Random(f"{seed}:{date}:{salt}")


class DailyGenerator:
    def __init__(self, library: QuestLibrary, engine: RecommendationEngine, store: DailyStore, seed: object = 0):
        self.library = library
        self.engine = engine
        self.store = store
        self.seed = seed

    def _attach(self, entries: List[DailyQuest]) -> List[DailyQuest]:
        for entry in entries:
            entry.quest = self.library.get(entry.quest_id)
        # Quests whose definition vanished (a deleted custom quest) are hidden.
        return [e for e in entries if e.quest is not None]

    def board(self, date: str) -> List[DailyQuest]:
        """The stored board for ``date`` (empty if not generated), excluding replaced quests."""
        return [e for e in self._attach(self.store.get_daily(date)) if e.status not in (STATUS_REPLACED, STATUS_CARRIED)]

    def has_board(self, date: str) -> bool:
        return bool(self.store.get_daily(date))

    def generate(self, date: str, ctx: RecommendationContext, secondary_count: int) -> List[DailyQuest]:
        """Create today's board: carried-over quests, one priority quest and ``secondary_count`` others."""
        existing = self.board(date)
        if existing:
            return existing

        carried = self._carry_over(date)
        ctx.exclude_ids = set(ctx.exclude_ids) | {c.quest_id for c in carried}
        rng = day_rng(self.seed, date)
        recs = self.engine.recommend(self.library.all(), ctx, 1 + secondary_count, rng)

        entries: List[DailyQuest] = []
        for index, rec in enumerate(recs):
            entries.append(DailyQuest(
                date=date, quest_id=rec.quest.id, slot=SLOT_PRIORITY if index == 0 else SLOT_SECONDARY,
                position=index, pick_type=rec.pick_type, status=STATUS_OFFERED, quest=rec.quest))
        for offset, entry in enumerate(carried, start=len(entries)):
            entry.position = offset
            entries.append(entry)
        self.store.save_daily(entries)
        return self._attach(entries)

    def _carry_over(self, date: str) -> List[DailyQuest]:
        """Accepted-but-unfinished quests from the last few days travel with you."""
        carried: List[DailyQuest] = []
        today = date_cls.fromisoformat(date)
        seen = set()
        for back in range(1, CARRY_OVER_DAYS + 1):
            previous = (today - timedelta(days=back)).isoformat()
            for entry in self.store.get_daily(previous):
                if entry.status != STATUS_ACCEPTED or entry.quest_id in seen:
                    continue
                if self.library.get(entry.quest_id) is None:
                    continue
                seen.add(entry.quest_id)
                self.store.update_daily_status(previous, entry.quest_id, STATUS_CARRIED)
                carried.append(DailyQuest(date=date, quest_id=entry.quest_id, slot=SLOT_SECONDARY, position=0,
                                          pick_type=entry.pick_type, status=STATUS_ACCEPTED))
        return carried

    def replace(self, date: str, quest_id: str, ctx: RecommendationContext) -> Optional[DailyQuest]:
        """Swap a quest for a new one of the same kind. Returns the new entry (or None if nothing fits)."""
        all_entries = self.store.get_daily(date)
        target = next((e for e in all_entries if e.quest_id == quest_id), None)
        if target is None:
            raise KeyError(f"{quest_id} is not on the board for {date}")

        ctx.exclude_ids = set(ctx.exclude_ids) | {e.quest_id for e in all_entries}
        others = [self.library.get(e.quest_id) for e in all_entries
                  if e.quest_id != quest_id and e.status != STATUS_REPLACED]
        avoid = [q.category for q in others if q is not None]
        replacements = sum(1 for e in all_entries if e.status == STATUS_REPLACED)
        rng = day_rng(self.seed, date, f"replace-{replacements}")
        pick_type = target.pick_type if target.pick_type != PICK_MANUAL else PICK_ALIGNED
        rec = self.engine.recommend_one(self.library.all(), ctx, rng, pick_type, avoid)
        if rec is None:
            return None

        self.store.update_daily_status(date, quest_id, STATUS_REPLACED)
        new_entry = DailyQuest(date=date, quest_id=rec.quest.id, slot=target.slot, position=target.position,
                               pick_type=rec.pick_type, status=STATUS_OFFERED, quest=rec.quest)
        self.store.save_daily([new_entry])
        return new_entry

    def add_manual(self, date: str, quest: Quest) -> DailyQuest:
        """Put a hand-picked quest on the board, already accepted."""
        entries = self.store.get_daily(date)
        existing = next((e for e in entries if e.quest_id == quest.id), None)
        if existing is not None:
            if existing.status == STATUS_COMPLETED:
                raise ValueError("That quest is already completed today")
            # Offered, skipped or even replaced earlier: the traveler changed their mind.
            self.store.update_daily_status(date, quest.id, STATUS_ACCEPTED)
            existing.status = STATUS_ACCEPTED
            existing.quest = quest
            return existing
        position = max((e.position for e in entries), default=-1) + 1
        entry = DailyQuest(date=date, quest_id=quest.id, slot=SLOT_SECONDARY, position=position,
                           pick_type=PICK_MANUAL, status=STATUS_ACCEPTED, quest=quest)
        self.store.save_daily([entry])
        return entry

    def set_status(self, date: str, quest_id: str, status: str) -> None:
        self.store.update_daily_status(date, quest_id, status)
