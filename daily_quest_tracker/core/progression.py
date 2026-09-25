"""Character and camp progression driven by level.

Unlockable items live in ``data/progression.json``. Each item occupies a
*slot*; a newer item in the same slot replaces the older one (a sword
replaces the dagger, plate replaces chainmail), while different slots stack
up to build the camp.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from core.quest_engine import DATA_DIR

PROGRESSION_FILE = os.path.join(DATA_DIR, "progression.json")


@dataclass(frozen=True)
class Item:
    id: str
    level: int
    slot: str
    kind: str
    name: str
    description: str


@dataclass(frozen=True)
class Title:
    level: int
    title: str


class Progression:
    def __init__(self, items: List[Item], titles: List[Title]):
        self.items = sorted(items, key=lambda i: (i.level, i.id))
        self.titles = sorted(titles, key=lambda t: t.level)
        self._by_id = {i.id: i for i in self.items}

    @classmethod
    def load(cls, path: str = PROGRESSION_FILE) -> "Progression":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = [Item(**entry) for entry in data["items"]]
        titles = [Title(**entry) for entry in data["titles"]]
        return cls(items, titles)

    def item(self, item_id: str) -> Optional[Item]:
        return self._by_id.get(item_id)

    def title_for_level(self, level: int) -> str:
        title = self.titles[0].title if self.titles else "Traveler"
        for entry in self.titles:
            if entry.level <= level:
                title = entry.title
        return title

    def unlocked_items(self, level: int) -> List[Item]:
        return [i for i in self.items if i.level <= level]

    def newly_unlocked(self, old_level: int, new_level: int) -> List[Item]:
        return [i for i in self.items if old_level < i.level <= new_level]

    def next_unlocks(self, level: int, count: int = 3) -> List[Item]:
        return [i for i in self.items if i.level > level][:count]

    def loadout(self, level: int) -> Dict[str, Item]:
        """Slot -> the best item unlocked for that slot at ``level``."""
        slots: Dict[str, Item] = {}
        for item in self.unlocked_items(level):
            slots[item.slot] = item
        return slots

    def is_superseded(self, item: Item, level: int) -> bool:
        current = self.loadout(level).get(item.slot)
        return current is not None and current.id != item.id
