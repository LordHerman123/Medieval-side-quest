from core.models import Completion, DailyQuest
from core.preference_tracker import EVENT_COMPLETED, PreferenceTracker
from database.database import Database

from tests.conftest import make_quest


def test_settings_roundtrip(db):
    assert db.get_setting("missing", 7) == 7
    db.set_setting("location", {"lat": 1.5, "name": "Ghent"})
    assert db.get_setting("location") == {"lat": 1.5, "name": "Ghent"}


def test_player_starts_at_level_one(db):
    assert db.get_player()["xp"] == 0
    db.set_player(300, 3)
    assert db.get_player()["level"] == 3


def test_custom_quest_crud(db):
    quest = make_quest("custom_1", category="Falconry", tags=["birds"])
    db.save_custom_quest(quest)
    loaded = db.load_custom_quests()
    assert loaded[0].title == quest.title and loaded[0].custom
    quest.title = "Renamed"
    db.save_custom_quest(quest)
    assert [q.title for q in db.load_custom_quests()] == ["Renamed"]
    db.delete_custom_quest("custom_1")
    assert db.load_custom_quests() == []


def test_events_feed_tracker(db):
    tracker = PreferenceTracker(db, clock=lambda: 1000.0)
    tracker.record(make_quest("a", category="Art", tags=["drawing"]), EVENT_COMPLETED, weather="rain")
    events = db.load_events()
    assert events[0].tags == ["drawing"] and events[0].weather == "rain"
    assert db.count_events(EVENT_COMPLETED) == 1


def test_daily_board_persistence(db):
    db.save_daily([DailyQuest("2026-03-01", "a", "priority", 0, "aligned"),
                   DailyQuest("2026-03-01", "b", "secondary", 1, "novel")])
    db.update_daily_status("2026-03-01", "b", "skipped")
    board = db.get_daily("2026-03-01")
    assert [(d.quest_id, d.status) for d in board] == [("a", "offered"), ("b", "skipped")]
    assert db.get_daily("2026-03-02") == []


def test_completions_newest_first(db):
    for i in range(3):
        db.add_completion(Completion(quest_id=f"q{i}", title=f"Q{i}", category="Art", difficulty=2, duration=30,
                                     xp=25, date="2026-03-01", completed_at=100 + i, tags=["x"]))
    history = db.completions()
    assert [c.quest_id for c in history] == ["q2", "q1", "q0"]
    assert db.completions(limit=1)[0].tags == ["x"]


def test_data_survives_reopen(tmp_path):
    path = str(tmp_path / "save.db")
    first = Database(path)
    first.set_player(450, 4)
    first.add_unlock("sword", 13)
    first.save_custom_quest(make_quest("custom_x"))
    first.close()

    second = Database(path)
    assert second.get_player()["xp"] == 450
    assert "sword" in second.unlocks()
    assert second.load_custom_quests()[0].id == "custom_x"
    second.close()


def test_reset_progress_keeps_custom_quests(db):
    db.save_custom_quest(make_quest("custom_keep"))
    db.set_player(999, 5)
    db.add_unlock("sword", 13)
    db.reset_progress()
    assert db.get_player()["xp"] == 0
    assert db.unlocks() == {}
    assert db.load_custom_quests()
