"""End-to-end game loop: daily generation, quest actions, XP, unlocks, custom quests."""

import pytest

from core.game import Game
from core.models import (
    PICK_MANUAL,
    SLOT_PRIORITY,
    STATUS_ABANDONED,
    STATUS_ACCEPTED,
    STATUS_COMPLETED,
    STATUS_SKIPPED,
    QuestValidationError,
)
from database.database import Database


@pytest.fixture
def game(db, clock):
    return Game(db, now=clock)


def test_daily_board_generated_once_per_day(game, clock):
    board = game.today_board()
    assert len(board) == 5
    assert board[0].slot == SLOT_PRIORITY
    assert [e.quest_id for e in game.today_board()] == [e.quest_id for e in board]
    clock.advance(days=1)
    tomorrow = game.today_board()
    assert {e.quest_id for e in tomorrow}.isdisjoint({e.quest_id for e in board})


def test_board_persists_across_restart(tmp_path, clock):
    path = str(tmp_path / "save.db")
    first = [e.quest_id for e in Game(Database(path), now=clock).today_board()]
    second = [e.quest_id for e in Game(Database(path), now=clock).today_board()]
    assert first == second


def test_accept_and_complete_awards_xp(game):
    entry = game.today_board()[0]
    game.accept(entry.quest_id)
    result = game.complete(entry.quest_id)
    assert result.award.total >= entry.quest.xp
    assert game.xp == result.award.total
    assert game.journey()[0].quest_id == entry.quest_id
    statuses = {e.quest_id: e.status for e in game.today_board()}
    assert statuses[entry.quest_id] == STATUS_COMPLETED
    with pytest.raises(ValueError):
        game.complete(entry.quest_id)


def test_skip_and_abandon(game):
    board = game.today_board()
    assert game.skip(board[1].quest_id).status == STATUS_SKIPPED
    game.accept(board[2].quest_id)
    assert game.abandon(board[2].quest_id).status == STATUS_ABANDONED


def test_replace_swaps_in_a_new_quest(game):
    board = game.today_board()
    old = board[1]
    new = game.replace(old.quest_id)
    assert new is not None and new.quest_id not in {e.quest_id for e in board}
    current = game.today_board()
    assert old.quest_id not in {e.quest_id for e in current}
    assert new.quest_id in {e.quest_id for e in current}
    assert len(current) == len(board)


def test_manual_selection(game):
    board_ids = {e.quest_id for e in game.today_board()}
    quest = next(q for q in game.library.all() if q.id not in board_ids)
    entry = game.select_manually(quest.id)
    assert entry.status == STATUS_ACCEPTED and entry.pick_type == PICK_MANUAL
    assert game.complete(quest.id).quest.id == quest.id


def test_level_up_unlocks_items(game):
    game.db.set_player(90, 1)
    entry = game.today_board()[0]
    result = game.complete(entry.quest_id)
    assert result.leveled_up
    assert result.new_level == 2
    assert "walking_staff" in {i.id for i in result.new_items}
    assert "walking_staff" in game.db.unlocks()


def test_accepted_quests_carry_over(game, clock):
    entry = game.today_board()[2]
    game.accept(entry.quest_id)
    clock.advance(days=1)
    tomorrow = game.today_board()
    carried = [e for e in tomorrow if e.quest_id == entry.quest_id]
    assert carried and carried[0].status == STATUS_ACCEPTED
    game.complete(entry.quest_id)


def test_no_xp_lost_for_missed_days(game, clock):
    game.complete(game.today_board()[0].quest_id)
    xp = game.xp
    clock.advance(days=30)
    game.today_board()
    assert game.xp == xp


def test_wildcard_completion_earns_bonus(game):
    board = game.today_board()
    entry = board[0]
    game.db.update_daily_status(entry.date, entry.quest_id, "accepted")
    # Mark it as a wildcard to check the bonus path.
    with game.db.transaction() as conn:
        conn.execute("UPDATE daily_quests SET pick_type='wildcard' WHERE quest_id=?", (entry.quest_id,))
    result = game.complete(entry.quest_id)
    assert result.award.wildcard_bonus > 0


def test_custom_quest_lifecycle(game):
    quest = game.save_custom_quest({
        "title": "Joust a scarecrow", "description": "Charge bravely at a scarecrow with a broom.",
        "category": "Adventure", "difficulty": 3, "cost": 0, "accessibility": 1, "duration": 20,
        "environment": "outdoor", "weather": ["clear"], "tags": "playful, medieval",
    })
    assert quest.custom and quest.tags == ["playful", "medieval"] and quest.xp > 0
    assert game.library.get(quest.id)
    edited = game.save_custom_quest({**quest.to_dict(), "title": "Joust two scarecrows"}, quest_id=quest.id)
    assert game.library.get(quest.id).title == "Joust two scarecrows" == edited.title
    # Custom quests enter the same recommendation system.
    assert quest.id in {r.quest.id for r in game.engine.rank(game.library.all(), game.context())}
    game.select_manually(quest.id)
    game.complete(quest.id)
    game.delete_custom_quest(quest.id)
    assert game.library.get(quest.id) is None
    assert game.journey()[0].title == "Joust two scarecrows"  # history keeps the snapshot
    # Reloading the game doesn't bring it back.
    assert Game(game.db).library.get(quest.id) is None


def test_invalid_custom_quest_rejected(game):
    with pytest.raises(QuestValidationError):
        game.save_custom_quest({"title": "", "description": "x", "category": "Art"})


def test_statistics(game):
    board = game.today_board()
    game.complete(board[0].quest_id)
    game.skip(board[1].quest_id)
    stats = game.statistics()
    assert stats.total_completed == 1
    assert stats.categories_explored == 1
    assert stats.categories_total >= 14
    assert stats.paths_for_another_day == 1
    assert stats.recent_discoveries[0].category == board[0].quest.category
    assert stats.longest_quest.quest_id == board[0].quest_id


def test_settings_change_board_size_and_constraints(db, clock):
    game = Game(db, now=clock)
    game.set_setting("secondary_count", 2)
    game.set_setting("max_cost", 0)
    board = game.today_board()
    assert len(board) == 3
    assert all(e.quest.cost == 0 for e in board)


def test_reset_progress(game):
    game.complete(game.today_board()[0].quest_id)
    game.reset_progress()
    assert game.xp == 0 and game.journey() == []
    assert len(game.today_board()) == 5
