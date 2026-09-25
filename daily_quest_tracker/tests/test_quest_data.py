"""Checks on the shipped quest library itself."""

import json
from collections import Counter

from core.models import ENVIRONMENTS, WEATHER_CONDITIONS
from core.progression import Progression
from core.quest_engine import CATEGORIES_FILE, QUESTS_FILE, load_builtin_quests, load_categories

REQUIRED_CATEGORIES = {
    "Adventure", "Art", "Creativity", "Connection", "Exploration", "Learning", "Nature",
    "Self Care", "Food", "Physical", "Reflection", "Social", "Culture", "Spontaneity",
    "Music", "Crafts", "Kindness", "Seasonal",
}
MUNDANE = ("clean your room", "do the dishes", "make your bed", "drink water", "do laundry")


def test_library_is_large_and_valid():
    quests = load_builtin_quests()
    assert 800 <= len(quests) <= 1000
    assert len({q.id for q in quests}) == len(quests)
    assert len({q.title.lower() for q in quests}) == len(quests)


def test_every_quest_has_complete_metadata():
    with open(QUESTS_FILE, encoding="utf-8") as fh:
        raw = json.load(fh)["quests"]
    fields = {"id", "title", "description", "category", "difficulty", "cost", "accessibility",
              "duration", "environment", "weather", "tags", "xp"}
    for entry in raw:
        assert fields <= set(entry), entry["id"]
        assert 1 <= entry["difficulty"] <= 5
        assert 0 <= entry["cost"] <= 3
        assert 0 <= entry["accessibility"] <= 4
        assert entry["duration"] > 0
        assert entry["environment"] in ENVIRONMENTS
        assert entry["tags"], entry["id"]
        assert entry["xp"] > 0
        for w in entry["weather"]:
            assert w == "any" or w in WEATHER_CONDITIONS


def test_all_categories_present_and_well_stocked():
    quests = load_builtin_quests()
    counts = Counter(q.category for q in quests)
    assert REQUIRED_CATEGORIES <= set(counts)
    assert min(counts[c] for c in REQUIRED_CATEGORIES) >= 25
    names = {c.name for c in load_categories(CATEGORIES_FILE)}
    assert set(counts) <= names


def test_no_mundane_chores():
    for quest in load_builtin_quests():
        assert not any(m in quest.title.lower() for m in MUNDANE), quest.title


def test_harder_quests_give_more_xp_on_average():
    quests = load_builtin_quests()
    avg = {d: sum(q.xp for q in quests if q.difficulty == d) / max(1, sum(q.difficulty == d for q in quests))
           for d in range(1, 6)}
    assert avg[1] < avg[2] < avg[3] < avg[4] < avg[5]


def test_progression_file_loads():
    progression = Progression.load()
    assert progression.items and progression.titles
    assert progression.unlocked_items(1), "the traveler starts with something"
