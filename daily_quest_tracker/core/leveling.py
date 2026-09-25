"""XP rewards and the level curve.

The curve grows gently: each level needs 50 XP more than the previous one.

    Level 1 -> 0 XP, Level 2 -> 100, Level 3 -> 250, Level 4 -> 450, ...

which is ``25 * (level - 1) * (level + 2)``. XP is never taken away, so
missing a day never costs anything.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DIFFICULTY_BASE_XP = {1: 15, 2: 25, 3: 40, 4: 60, 5: 90}
DURATION_STEP_MINUTES = 30
DURATION_STEP_XP = 5
DURATION_BONUS_CAP = 30

WILDCARD_BONUS_RATE = 0.2  # extra XP for completing a quest outside your comfort zone
DISCOVERY_BONUS_XP = 10  # first quest ever completed in a category


def quest_xp(difficulty: int, duration: int) -> int:
    """Base XP for a quest: difficulty drives it, longer quests earn a little more."""
    base = DIFFICULTY_BASE_XP.get(int(difficulty), DIFFICULTY_BASE_XP[1])
    duration_bonus = min(DURATION_BONUS_CAP, (int(duration) // DURATION_STEP_MINUTES) * DURATION_STEP_XP)
    return base + duration_bonus


@dataclass
class XpAward:
    base: int
    wildcard_bonus: int = 0
    discovery_bonus: int = 0

    @property
    def total(self) -> int:
        return self.base + self.wildcard_bonus + self.discovery_bonus


def completion_award(quest_xp_value: int, is_wildcard: bool = False, is_new_category: bool = False) -> XpAward:
    wildcard = int(round(quest_xp_value * WILDCARD_BONUS_RATE)) if is_wildcard else 0
    discovery = DISCOVERY_BONUS_XP if is_new_category else 0
    return XpAward(base=quest_xp_value, wildcard_bonus=wildcard, discovery_bonus=discovery)


def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level``."""
    if level <= 1:
        return 0
    return 25 * (level - 1) * (level + 2)


def level_for_xp(xp: int) -> int:
    """Highest level whose threshold ``xp`` has reached."""
    if xp <= 0:
        return 1
    # Solve 25(L-1)(L+2) = xp  ->  L^2 + L - (2 + xp/25) = 0
    level = int((-1 + math.sqrt(1 + 4 * (2 + xp / 25))) / 2)
    # Guard against floating point error at the exact thresholds.
    while xp_for_level(level + 1) <= xp:
        level += 1
    while level > 1 and xp_for_level(level) > xp:
        level -= 1
    return max(1, level)


@dataclass
class LevelInfo:
    level: int
    xp: int
    level_floor: int
    next_level_xp: int

    @property
    def xp_into_level(self) -> int:
        return self.xp - self.level_floor

    @property
    def xp_needed(self) -> int:
        return self.next_level_xp - self.level_floor

    @property
    def progress(self) -> float:
        return self.xp_into_level / self.xp_needed if self.xp_needed else 1.0


def level_info(xp: int) -> LevelInfo:
    level = level_for_xp(xp)
    return LevelInfo(level=level, xp=xp, level_floor=xp_for_level(level), next_level_xp=xp_for_level(level + 1))
