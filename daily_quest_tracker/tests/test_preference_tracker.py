import pytest

from core.preference_tracker import (
    EVENT_COMPLETED,
    EVENT_OFFERED,
    EVENT_SKIPPED,
    MemoryEventStore,
    PreferenceProfile,
    PreferenceTracker,
    SECONDS_PER_DAY,
    recency_weight,
)

from tests.conftest import make_quest

NOW = 1_800_000_000.0


def tracker():
    return PreferenceTracker(MemoryEventStore(), clock=lambda: NOW)


def test_completions_raise_category_and_tag_preference():
    t = tracker()
    quest = make_quest("a", category="Nature", tags=["photography"])
    for _ in range(4):
        t.record(quest, EVENT_COMPLETED)
    profile = t.profile()
    assert profile.category_preference("Nature") > 0.4
    assert profile.tag_preference(["photography"]) > 0.3
    assert profile.category_preference("Art") == 0


def test_skips_lower_preference():
    t = tracker()
    quest = make_quest("s", category="Social")
    for _ in range(4):
        t.record(quest, EVENT_SKIPPED)
    assert t.profile().category_preference("Social") < 0


def test_single_event_does_not_overreact():
    t = tracker()
    t.record(make_quest("a", category="Art"), EVENT_COMPLETED)
    single = t.profile().category_preference("Art")
    assert 0 < single <= 0.3
    for _ in range(9):
        t.record(make_quest("a", category="Art"), EVENT_COMPLETED)
    assert t.profile().category_preference("Art") > single


def test_preferences_stay_bounded():
    t = tracker()
    for _ in range(200):
        t.record(make_quest("a", category="Art"), EVENT_COMPLETED)
    assert t.profile().category_preference("Art") < 1.0


def test_recent_events_count_more_than_old_ones():
    old = tracker()
    old.record(make_quest("a", category="Art"), EVENT_COMPLETED, timestamp=NOW - 200 * SECONDS_PER_DAY)
    recent = tracker()
    recent.record(make_quest("a", category="Art"), EVENT_COMPLETED, timestamp=NOW)
    assert recent.profile().category_preference("Art") > old.profile().category_preference("Art")
    assert recency_weight(0) == pytest.approx(1.0)
    assert recency_weight(45 * SECONDS_PER_DAY) == pytest.approx(0.5)


def test_mixed_signals_net_out():
    t = tracker()
    quest = make_quest("a", category="Food")
    for _ in range(3):
        t.record(quest, EVENT_COMPLETED)
        t.record(quest, EVENT_SKIPPED)
    assert 0 < t.profile().category_preference("Food") < 0.5


def test_offered_is_exposure_not_preference():
    t = tracker()
    t.record(make_quest("a", category="Art"), EVENT_OFFERED)
    profile = t.profile()
    assert profile.category_preference("Art") == 0
    assert profile.last_offered["a"] == NOW


def test_preferred_difficulty_learns_gradually():
    t = tracker()
    assert t.profile().preferred_difficulty == pytest.approx(2.0)
    for _ in range(12):
        t.record(make_quest("hard", difficulty=4), EVENT_COMPLETED)
    profile = t.profile()
    assert 3.3 < profile.preferred_difficulty < 4.0


def test_profile_tracks_completion_facts():
    events = MemoryEventStore()
    t = PreferenceTracker(events, clock=lambda: NOW)
    t.record(make_quest("a", category="Art", tags=["drawing"]), EVENT_COMPLETED, weather="rain")
    profile = PreferenceProfile.from_events(events.load_events(), now=NOW)
    assert profile.has_completed("a")
    assert profile.explored_categories == {"Art"}
    assert profile.unseen_tag_share(["drawing", "music"]) == 0.5
    assert profile.environment_weather.preference("outdoor|rain") > 0


def test_unknown_event_rejected():
    with pytest.raises(ValueError):
        tracker().record(make_quest("a"), "teleported")
