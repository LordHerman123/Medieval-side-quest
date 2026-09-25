import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.models import Quest  # noqa: E402
from core.quest_engine import Category, QuestLibrary  # noqa: E402
from database.database import Database  # noqa: E402


def make_quest(qid, category="Nature", difficulty=2, cost=0, accessibility=0, duration=30,
               environment="outdoor", weather=None, tags=None, xp=0):
    return Quest.from_dict({
        "id": qid, "title": f"Quest {qid}", "description": f"Do {qid}", "category": category,
        "difficulty": difficulty, "cost": cost, "accessibility": accessibility, "duration": duration,
        "environment": environment, "weather": weather or ["any"], "tags": tags or [], "xp": xp,
    })


class Clock:
    """A controllable 'now' for the game."""

    def __init__(self, start=datetime(2026, 3, 1, 12, 0)):
        self.current = start

    def __call__(self):
        return self.current

    def advance(self, **kwargs):
        from datetime import timedelta
        self.current += timedelta(**kwargs)


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def library():
    return QuestLibrary.load()


@pytest.fixture
def small_library():
    categories = [Category(n) for n in ("Nature", "Art", "Social", "Learning", "Food")]
    quests = []
    for i, cat in enumerate(["Nature", "Art", "Social", "Learning", "Food"] * 6):
        env = "outdoor" if cat == "Nature" else "indoor"
        quests.append(make_quest(f"q{i:02d}", category=cat, environment=env,
                                 difficulty=1 + i % 4, tags=[cat.lower(), f"t{i % 7}"]))
    return QuestLibrary(quests, categories)


@pytest.fixture
def clock():
    return Clock()
