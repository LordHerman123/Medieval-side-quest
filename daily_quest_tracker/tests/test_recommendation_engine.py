import random
from collections import Counter

import pytest

from core.models import PICK_ALIGNED, PICK_NOVEL, PICK_WILDCARD, Weather
from core.preference_tracker import EVENT_COMPLETED, EVENT_OFFERED, MemoryEventStore, PreferenceProfile, PreferenceTracker
from core.recommendation_engine import (
    Constraints,
    EngineConfig,
    RecommendationContext,
    RecommendationEngine,
    weather_fit,
)

from tests.conftest import make_quest

NOW = 1_800_000_000.0
DAY = 86400.0


def profile_from(records):
    store = MemoryEventStore()
    tracker = PreferenceTracker(store, clock=lambda: NOW)
    for quest, event, *age in records:
        tracker.record(quest, event, timestamp=NOW - (age[0] if age else 0))
    return tracker.profile()


def ctx(profile=None, **kwargs):
    return RecommendationContext(profile=profile or PreferenceProfile(), now=NOW, local_hour=12, **kwargs)


# --- scoring ----------------------------------------------------------------

def test_score_total_matches_formula():
    engine = RecommendationEngine()
    s = engine.score(make_quest("a", cost=2, accessibility=3), ctx())
    expected = (s.base + s.category_preference + s.tag_preference + s.difficulty_preference + s.weather_score
                + s.novelty_bonus - s.cost_penalty - s.accessibility_penalty - s.repetition_penalty)
    assert s.total == pytest.approx(expected)


def test_preferred_category_scores_higher():
    liked = make_quest("liked", category="Nature")
    profile = profile_from([(liked, EVENT_COMPLETED)] * 5)
    engine = RecommendationEngine()
    other_nature = make_quest("n2", category="Nature")
    other_art = make_quest("a2", category="Art")
    assert engine.score(other_nature, ctx(profile)).total > engine.score(other_art, ctx(profile)).total


def test_cost_and_accessibility_penalised():
    engine = RecommendationEngine()
    free = engine.score(make_quest("f", cost=0, accessibility=0), ctx())
    pricey = engine.score(make_quest("p", cost=3, accessibility=4), ctx())
    assert pricey.cost_penalty > free.cost_penalty
    assert pricey.accessibility_penalty > free.accessibility_penalty
    assert pricey.total < free.total


def test_recently_completed_quest_is_penalised_and_recovers():
    quest = make_quest("a")
    engine = RecommendationEngine()
    fresh = engine.score(quest, ctx(profile_from([(quest, EVENT_COMPLETED, 1 * DAY)])))
    later = engine.score(quest, ctx(profile_from([(quest, EVENT_COMPLETED, 60 * DAY)])))
    assert fresh.repetition_penalty > later.repetition_penalty
    assert later.repetition_penalty == pytest.approx(0.0)


def test_recently_offered_quest_is_penalised():
    quest = make_quest("a")
    s = RecommendationEngine().score(quest, ctx(profile_from([(quest, EVENT_OFFERED, 0.5 * DAY)])))
    assert s.repetition_penalty > 0


def test_novelty_bonus_for_never_done():
    done = make_quest("done", tags=["x"])
    profile = profile_from([(done, EVENT_COMPLETED, 90 * DAY)])
    engine = RecommendationEngine()
    assert engine.score(make_quest("new", tags=["y"]), ctx(profile)).novelty_bonus > \
        engine.score(done, ctx(profile)).novelty_bonus


def test_difficulty_near_target_preferred():
    engine = RecommendationEngine()
    easyish = engine.score(make_quest("a", difficulty=2), ctx(level=1))
    epic = engine.score(make_quest("b", difficulty=5), ctx(level=1))
    assert easyish.difficulty_preference > epic.difficulty_preference


# --- weather ---------------------------------------------------------------------

def test_rain_favours_indoor():
    rain = Weather(condition="rain", temperature=10)
    indoor = make_quest("i", environment="indoor")
    outdoor = make_quest("o", environment="outdoor", weather=["clear", "cloudy"])
    assert weather_fit(indoor, rain) > 0 > weather_fit(outdoor, rain)


def test_sun_favours_outdoor_nature():
    sun = Weather(condition="clear", temperature=20)
    nature = make_quest("n", category="Nature", environment="outdoor", weather=["clear"])
    indoor = make_quest("i", environment="indoor")
    assert weather_fit(nature, sun) > weather_fit(indoor, sun)


def test_cold_prefers_short_outdoor_trips():
    cold = Weather(condition="cloudy", temperature=-2)
    short = make_quest("s", environment="outdoor", duration=15, weather=["cloudy"])
    long = make_quest("l", environment="outdoor", duration=240, weather=["cloudy"])
    assert weather_fit(short, cold) > weather_fit(long, cold)


def test_heat_prefers_water_and_shade():
    hot = Weather(condition="clear", temperature=33)
    swim = make_quest("s", environment="outdoor", weather=["clear"], tags=["water"], duration=90)
    hike = make_quest("h", environment="outdoor", weather=["clear"], tags=["hiking"], duration=90)
    assert weather_fit(swim, hot) > weather_fit(hike, hot)


def test_weather_is_a_weight_not_a_filter(library):
    """Even in a storm, outdoor quests remain possible."""
    engine = RecommendationEngine()
    storm = Weather(condition="rain", temperature=8)
    envs = Counter()
    for seed in range(60):
        for rec in engine.recommend(library.all(), ctx(weather=storm), 5, random.Random(seed)):
            envs[rec.quest.environment] += 1
    assert envs["indoor"] > envs["outdoor"] > 0


def test_no_weather_is_neutral():
    assert weather_fit(make_quest("a", environment="outdoor"), None) == 0


# --- mix of aligned / novel / wildcard ------------------------------------------------

def test_allocation_respects_shares():
    engine = RecommendationEngine()
    totals = Counter()
    for seed in range(400):
        counts = engine.allocate(10, random.Random(seed))
        assert sum(counts.values()) == 10
        totals.update(counts)
    assert totals[PICK_ALIGNED] / 4000 == pytest.approx(0.7, abs=0.03)
    assert totals[PICK_NOVEL] / 4000 == pytest.approx(0.2, abs=0.03)
    assert totals[PICK_WILDCARD] / 4000 == pytest.approx(0.1, abs=0.03)


def test_small_boards_always_include_a_surprise():
    engine = RecommendationEngine()
    for seed in range(50):
        counts = engine.allocate(3, random.Random(seed))
        assert counts[PICK_NOVEL] + counts[PICK_WILDCARD] >= 1
        assert counts[PICK_ALIGNED] >= 1


def test_recommend_returns_unique_quests_with_priority_first(library):
    recs = RecommendationEngine().recommend(library.all(), ctx(), 5, random.Random(1))
    assert len(recs) == 5
    assert len({r.quest.id for r in recs}) == 5
    assert recs[0].pick_type == PICK_ALIGNED


def test_daily_categories_are_diverse(library):
    engine = RecommendationEngine()
    for seed in range(20):
        recs = engine.recommend(library.all(), ctx(), 5, random.Random(seed))
        assert len({r.quest.category for r in recs}) >= 4


def test_novel_pick_prefers_unexplored(small_library):
    done = [q for q in small_library.all() if q.category == "Nature"]
    profile = profile_from([(q, EVENT_COMPLETED, 40 * DAY) for q in done])
    engine = RecommendationEngine()
    c = ctx(profile)
    recs = engine.rank(small_library.all(), c)
    for seed in range(30):
        pick = engine.pick_novel(recs, c, random.Random(seed))
        assert pick.pick_type == PICK_NOVEL
        assert not profile.has_completed(pick.quest.id)


def test_wildcard_comes_from_outside_the_comfort_zone(small_library):
    # The user loves Nature and Art; wildcards should come from elsewhere.
    loved = [q for q in small_library.all() if q.category in ("Nature", "Art")]
    profile = profile_from([(q, EVENT_COMPLETED, 40 * DAY) for q in loved] * 2)
    engine = RecommendationEngine()
    c = ctx(profile)
    recs = engine.rank(small_library.all(), c)
    pool = engine.wildcard_pool(recs, c)
    assert pool
    picks = Counter(engine.pick_wildcard(recs, c, random.Random(s)).quest.category for s in range(60))
    assert picks["Nature"] + picks["Art"] < 0.3 * sum(picks.values())


def test_preferences_shift_recommendations(library):
    engine = RecommendationEngine()
    nature = [q for q in library.all() if q.category == "Nature"][:10]
    profile = profile_from([(q, EVENT_COMPLETED, 40 * DAY) for q in nature])

    def nature_share(p):
        hits = 0
        for seed in range(80):
            hits += sum(r.quest.category == "Nature" for r in engine.recommend(library.all(), ctx(p), 5, random.Random(seed)))
        return hits / 400

    assert nature_share(profile) > nature_share(PreferenceProfile())


def test_constraints_are_hard_limits(library):
    engine = RecommendationEngine()
    c = ctx(constraints=Constraints(max_cost=0, allow_group_quests=False, max_difficulty=2))
    for seed in range(20):
        for rec in engine.recommend(library.all(), c, 5, random.Random(seed)):
            assert rec.quest.cost == 0 and rec.quest.accessibility < 4 and rec.quest.difficulty <= 2


def test_exclusions_respected(library):
    excluded = {q.id for q in library.all()[:250]}
    recs = RecommendationEngine().recommend(library.all(), ctx(exclude_ids=excluded), 5, random.Random(3))
    assert not excluded & {r.quest.id for r in recs}


def test_config_changes_behaviour_without_ui(library):
    greedy = RecommendationEngine(EngineConfig(aligned_share=1.0, novel_share=0.0, wildcard_share=0.0))
    counts = greedy.allocate(2, random.Random(0))
    assert counts[PICK_ALIGNED] == 2


def test_recommend_is_deterministic_for_a_seed(library):
    engine = RecommendationEngine()
    a = [r.quest.id for r in engine.recommend(library.all(), ctx(), 5, random.Random(42))]
    b = [r.quest.id for r in engine.recommend(library.all(), ctx(), 5, random.Random(42))]
    assert a == b
