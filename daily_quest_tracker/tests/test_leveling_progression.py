import pytest

from core import leveling
from core.progression import Progression


@pytest.mark.parametrize("level, xp", [(1, 0), (2, 100), (3, 250), (4, 450), (5, 700)])
def test_level_thresholds(level, xp):
    assert leveling.xp_for_level(level) == xp


def test_level_for_xp_boundaries():
    assert leveling.level_for_xp(0) == 1
    assert leveling.level_for_xp(99) == 1
    assert leveling.level_for_xp(100) == 2
    assert leveling.level_for_xp(249) == 2
    assert leveling.level_for_xp(250) == 3
    for level in range(1, 80):
        assert leveling.level_for_xp(leveling.xp_for_level(level)) == level
        assert leveling.level_for_xp(leveling.xp_for_level(level) - 1) == max(1, level - 1)


def test_curve_gets_steeper():
    gaps = [leveling.xp_for_level(l + 1) - leveling.xp_for_level(l) for l in range(1, 20)]
    assert all(b > a for a, b in zip(gaps, gaps[1:]))


def test_quest_xp_scales_with_difficulty_and_duration():
    assert leveling.quest_xp(1, 30) < leveling.quest_xp(3, 30) < leveling.quest_xp(5, 30)
    assert leveling.quest_xp(2, 10) < leveling.quest_xp(2, 120)
    # Duration bonus is capped so long quests don't dominate.
    assert leveling.quest_xp(1, 10_000) - leveling.quest_xp(1, 10) == leveling.DURATION_BONUS_CAP


def test_completion_bonuses():
    plain = leveling.completion_award(40)
    assert plain.total == 40
    bonus = leveling.completion_award(40, is_wildcard=True, is_new_category=True)
    assert bonus.wildcard_bonus == 8
    assert bonus.discovery_bonus == leveling.DISCOVERY_BONUS_XP
    assert bonus.total == 58


def test_level_info_progress():
    info = leveling.level_info(175)
    assert info.level == 2
    assert info.xp_into_level == 75
    assert info.xp_needed == 150
    assert info.progress == pytest.approx(0.5)


def test_progression_unlocks_and_slots():
    progression = Progression.load()
    assert progression.title_for_level(1) == "Lone Traveler"
    assert progression.title_for_level(40) == "Legend of the Realm"
    early = progression.loadout(1)
    assert early["fire"].id == "campfire_small"
    assert "shelter" not in early
    late = progression.loadout(30)
    assert late["fire"].id == "campfire_large"
    assert late["body"].id == "plate_armour"
    assert late["shelter"].id == "pavilion"
    new = progression.newly_unlocked(9, 13)
    assert [i.id for i in new] == ["dog", "campfire_medium", "wooden_shield", "sword"]
    assert progression.next_unlocks(1, 2)[0].level > 1


def test_progression_has_gear_camp_animals_npcs_and_structures():
    kinds = {i.kind for i in Progression.load().items}
    assert {"clothing", "weapon", "armour", "shield", "camp", "animal", "npc", "companion", "structure"} <= kinds
