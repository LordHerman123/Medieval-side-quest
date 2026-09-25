"""Quest library: loads the built-in quests, merges custom quests, filters and searches.

The built-in quests live in ``data/quests.json`` and the categories in
``data/categories.json``. Adding a category only requires adding it to that
file; nothing in the code lists categories by name.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from core.models import Quest, QuestValidationError

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
QUESTS_FILE = os.path.join(DATA_DIR, "quests.json")
CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")

DEFAULT_CATEGORY_COLOR = "#8B6F47"


@dataclass
class Category:
    name: str
    color: str = DEFAULT_CATEGORY_COLOR
    motto: str = ""


def load_categories(path: str = CATEGORIES_FILE) -> List[Category]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [Category(name=c["name"], color=c.get("color", DEFAULT_CATEGORY_COLOR), motto=c.get("motto", ""))
            for c in data["categories"]]


def load_builtin_quests(path: str = QUESTS_FILE) -> List[Quest]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    quests = [Quest.from_dict(entry) for entry in data["quests"]]
    ids = [q.id for q in quests]
    if len(ids) != len(set(ids)):
        raise QuestValidationError("Duplicate quest ids in built-in quest file")
    return quests


@dataclass
class QuestFilter:
    """Criteria for browsing the library. ``None`` means "don't filter on this"."""

    category: Optional[str] = None
    difficulty: Optional[int] = None
    max_difficulty: Optional[int] = None
    max_cost: Optional[int] = None
    max_accessibility: Optional[int] = None
    max_duration: Optional[int] = None
    environment: Optional[str] = None
    search: str = ""
    custom_only: bool = False

    def matches(self, quest: Quest) -> bool:
        if self.category and quest.category != self.category:
            return False
        if self.difficulty is not None and quest.difficulty != self.difficulty:
            return False
        if self.max_difficulty is not None and quest.difficulty > self.max_difficulty:
            return False
        if self.max_cost is not None and quest.cost > self.max_cost:
            return False
        if self.max_accessibility is not None and quest.accessibility > self.max_accessibility:
            return False
        if self.max_duration is not None and quest.duration > self.max_duration:
            return False
        if self.environment:
            # "either" quests can be done anywhere, so they match both filters.
            if quest.environment != self.environment and quest.environment != "either":
                return False
        if self.custom_only and not quest.custom:
            return False
        if self.search:
            haystack = " ".join([quest.title, quest.description, quest.category, " ".join(quest.tags)]).lower()
            if not all(word in haystack for word in self.search.lower().split()):
                return False
        return True


class QuestLibrary:
    """All quests the recommender can choose from: built-in plus the user's own."""

    def __init__(self, builtin: Iterable[Quest], categories: Iterable[Category], custom: Iterable[Quest] = ()):
        self._builtin: Dict[str, Quest] = {q.id: q for q in builtin}
        self._custom: Dict[str, Quest] = {}
        self._categories: Dict[str, Category] = {c.name: c for c in categories}
        for quest in custom:
            self.add_custom(quest)

    @classmethod
    def load(cls, custom: Iterable[Quest] = ()) -> "QuestLibrary":
        return cls(load_builtin_quests(), load_categories(), custom)

    # --- categories -------------------------------------------------------
    @property
    def categories(self) -> List[Category]:
        return list(self._categories.values())

    @property
    def category_names(self) -> List[str]:
        return list(self._categories)

    def category(self, name: str) -> Category:
        return self._categories.get(name) or Category(name=name)

    # --- quests -----------------------------------------------------------
    def all(self) -> List[Quest]:
        return list(self._builtin.values()) + list(self._custom.values())

    def get(self, quest_id: str) -> Optional[Quest]:
        return self._custom.get(quest_id) or self._builtin.get(quest_id)

    def __len__(self) -> int:
        return len(self._builtin) + len(self._custom)

    def __contains__(self, quest_id: str) -> bool:
        return quest_id in self._builtin or quest_id in self._custom

    def filter(self, criteria: Optional[QuestFilter] = None) -> List[Quest]:
        quests = self.all()
        if criteria is None:
            return quests
        return [q for q in quests if criteria.matches(q)]

    def search(self, text: str) -> List[Quest]:
        return self.filter(QuestFilter(search=text))

    # --- custom quests ----------------------------------------------------
    def add_custom(self, quest: Quest) -> None:
        quest.custom = True
        if quest.category not in self._categories:
            # User categories become first-class categories automatically.
            self._categories[quest.category] = Category(name=quest.category)
        self._custom[quest.id] = quest

    def remove_custom(self, quest_id: str) -> None:
        self._custom.pop(quest_id, None)

    @property
    def custom_quests(self) -> List[Quest]:
        return list(self._custom.values())
