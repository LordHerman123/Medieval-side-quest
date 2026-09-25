import pytest

from core.models import Quest, QuestValidationError
from core.quest_engine import QuestFilter, QuestLibrary

from tests.conftest import make_quest


def test_filter_by_category(library):
    art = library.filter(QuestFilter(category="Art"))
    assert art and all(q.category == "Art" for q in art)


def test_filter_by_numeric_limits(library):
    result = library.filter(QuestFilter(max_cost=0, max_accessibility=1, max_duration=30))
    assert result
    assert all(q.cost == 0 and q.accessibility <= 1 and q.duration <= 30 for q in result)


def test_filter_exact_difficulty(library):
    result = library.filter(QuestFilter(difficulty=5))
    assert result and all(q.difficulty == 5 for q in result)


def test_environment_filter_includes_either(library):
    outdoor = library.filter(QuestFilter(environment="outdoor"))
    envs = {q.environment for q in outdoor}
    assert envs == {"outdoor", "either"}


def test_search_matches_title_description_and_tags(library):
    assert any("sunrise" in q.title.lower() for q in library.search("sunrise"))
    by_tag = library.search("calligraphy")
    assert by_tag and all("calligraphy" in (q.title + q.description + " ".join(q.tags)).lower() for q in by_tag)
    # All words must match.
    assert library.search("sunrise zzzznotaword") == []


def test_custom_quests_join_library_and_new_categories():
    lib = QuestLibrary([make_quest("a")], [])
    custom = make_quest("mine", category="Falconry")
    lib.add_custom(custom)
    assert lib.get("mine").custom
    assert "Falconry" in lib.category_names
    assert lib.filter(QuestFilter(custom_only=True)) == [custom]
    lib.remove_custom("mine")
    assert lib.get("mine") is None


def test_validation_rejects_bad_quests():
    with pytest.raises(QuestValidationError):
        Quest.from_dict({"id": "x", "title": "", "description": "d", "category": "Art"})
    with pytest.raises(QuestValidationError):
        make_quest("x", difficulty=9)
    with pytest.raises(QuestValidationError):
        make_quest("x", environment="underwater")
    with pytest.raises(QuestValidationError):
        make_quest("x", weather=["meteor-shower"])


def test_missing_xp_is_derived_from_difficulty():
    easy = make_quest("e", difficulty=1, duration=20)
    epic = make_quest("p", difficulty=5, duration=20)
    assert 0 < easy.xp < epic.xp
