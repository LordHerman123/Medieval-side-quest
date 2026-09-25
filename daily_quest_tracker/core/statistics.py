"""Journey statistics. Celebrates what happened; never counts "failures"."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.models import PICK_NOVEL, PICK_WILDCARD, Completion


@dataclass
class Discovery:
    category: str
    title: str
    date: str


@dataclass
class Statistics:
    total_completed: int = 0
    total_xp: int = 0
    level: int = 1
    title: str = ""
    categories_explored: int = 0
    categories_total: int = 0
    wildcards_completed: int = 0
    novel_completed: int = 0
    new_activities: int = 0
    days_adventured: int = 0
    epic_quests: int = 0
    total_minutes: int = 0
    top_categories: List[Tuple[str, int]] = field(default_factory=list)
    top_tags: List[Tuple[str, int]] = field(default_factory=list)
    longest_quest: Optional[Completion] = None
    recent_discoveries: List[Discovery] = field(default_factory=list)
    paths_for_another_day: int = 0
    custom_quests: int = 0


def compute_statistics(completions: List[Completion], *, xp: int, level: int, title: str,
                       categories_total: int, skipped: int = 0, custom_quests: int = 0) -> Statistics:
    ordered = sorted(completions, key=lambda c: c.completed_at)
    categories = Counter(c.category for c in ordered)
    tags = Counter(t for c in ordered for t in c.tags)

    discoveries: List[Discovery] = []
    seen = set()
    for c in ordered:
        if c.category not in seen:
            seen.add(c.category)
            discoveries.append(Discovery(category=c.category, title=c.title, date=c.date))

    return Statistics(
        total_completed=len(ordered),
        total_xp=xp,
        level=level,
        title=title,
        categories_explored=len(categories),
        categories_total=categories_total,
        wildcards_completed=sum(1 for c in ordered if c.pick_type == PICK_WILDCARD),
        novel_completed=sum(1 for c in ordered if c.pick_type == PICK_NOVEL),
        new_activities=len({c.quest_id for c in ordered}),
        days_adventured=len({c.date for c in ordered}),
        epic_quests=sum(1 for c in ordered if c.difficulty >= 4),
        total_minutes=sum(c.duration for c in ordered),
        top_categories=categories.most_common(5),
        top_tags=tags.most_common(6),
        longest_quest=max(ordered, key=lambda c: c.duration) if ordered else None,
        recent_discoveries=list(reversed(discoveries))[:5],
        paths_for_another_day=skipped,
        custom_quests=custom_quests,
    )
