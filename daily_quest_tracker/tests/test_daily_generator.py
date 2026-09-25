from core.daily_generator import DailyGenerator
from core.models import PICK_MANUAL, SLOT_PRIORITY, SLOT_SECONDARY, STATUS_ACCEPTED, STATUS_REPLACED
from core.preference_tracker import PreferenceProfile
from core.recommendation_engine import RecommendationContext, RecommendationEngine


def ctx():
    return RecommendationContext(profile=PreferenceProfile(), now=1_800_000_000.0, local_hour=10)


def test_generate_creates_priority_and_secondaries(db, library):
    gen = DailyGenerator(library, RecommendationEngine(), db, seed=1)
    board = gen.generate("2026-03-01", ctx(), 4)
    assert len(board) == 5
    assert board[0].slot == SLOT_PRIORITY
    assert all(e.slot == SLOT_SECONDARY for e in board[1:])
    assert all(e.quest is not None for e in board)
    # Persisted, and generating again returns the same board.
    again = gen.generate("2026-03-01", ctx(), 4)
    assert [e.quest_id for e in again] == [e.quest_id for e in board]


def test_generation_is_seeded_by_date(db, library):
    from database.database import Database

    a = DailyGenerator(library, RecommendationEngine(), db, seed=7).generate("2026-03-01", ctx(), 4)
    b = DailyGenerator(library, RecommendationEngine(), Database(":memory:"), seed=7).generate("2026-03-01", ctx(), 4)
    c = DailyGenerator(library, RecommendationEngine(), Database(":memory:"), seed=7).generate("2026-03-02", ctx(), 4)
    assert [e.quest_id for e in a] == [e.quest_id for e in b]
    assert [e.quest_id for e in a] != [e.quest_id for e in c]


def test_replace_keeps_slot(db, library):
    gen = DailyGenerator(library, RecommendationEngine(), db, seed=1)
    board = gen.generate("2026-03-01", ctx(), 4)
    new = gen.replace("2026-03-01", board[0].quest_id, ctx())
    assert new.slot == SLOT_PRIORITY
    stored = {e.quest_id: e.status for e in db.get_daily("2026-03-01")}
    assert stored[board[0].quest_id] == STATUS_REPLACED
    assert gen.board("2026-03-01")[0].quest_id == new.quest_id


def test_manual_add(db, library):
    gen = DailyGenerator(library, RecommendationEngine(), db, seed=1)
    gen.generate("2026-03-01", ctx(), 2)
    quest = library.get("quest_100")
    entry = gen.add_manual("2026-03-01", quest)
    assert entry.pick_type == PICK_MANUAL and entry.status == STATUS_ACCEPTED
    assert quest.id in {e.quest_id for e in gen.board("2026-03-01")}


def test_board_without_generation_is_empty(db, library):
    gen = DailyGenerator(library, RecommendationEngine(), db)
    assert gen.board("2030-01-01") == []
    assert not gen.has_board("2030-01-01")
