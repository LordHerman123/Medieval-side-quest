"""Rule-based quest recommendation. No machine learning, no external services.

Each quest gets a score built from readable parts::

    score = (base
             + category_preference + tag_preference + difficulty_preference
             + weather_score + novelty_bonus
             - cost_penalty - accessibility_penalty - repetition_penalty)

Picking the day's quests then mixes three kinds of choice so personalisation
never turns into an echo chamber:

* **aligned**  - weighted random draw from the best scoring quests
* **novel**    - quests (and tags/categories) the user has rarely or never done
* **wildcard** - something deliberately off-profile: a neglected category, an
  unusual difficulty or an activity type never tried

All tuning lives in :class:`EngineConfig`, so the algorithm can be adjusted
without touching the UI.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

from core.models import PICK_ALIGNED, PICK_NOVEL, PICK_WILDCARD, Quest, Weather
from core.preference_tracker import SECONDS_PER_DAY, PreferenceProfile

# Tags that make an outdoor quest reasonable in the heat.
HOT_WEATHER_TAGS = {"water", "swimming", "shade", "morning", "evening", "night", "paddling"}
NIGHT_TAGS = {"night", "sky", "moon", "astronomy"}
SUNNY_CATEGORIES = {"Nature", "Exploration", "Adventure"}


@dataclass
class EngineConfig:
    base_score: float = 1.0
    category_weight: float = 1.5
    tag_weight: float = 1.0
    difficulty_weight: float = 0.7
    cost_weight: float = 0.25
    accessibility_weight: float = 0.15
    weather_weight: float = 1.0
    novelty_weight: float = 0.5
    repetition_weight: float = 3.0
    repetition_window_days: float = 30.0
    offered_window_days: float = 3.0
    offered_weight: float = 1.0
    skip_window_days: float = 10.0
    skip_weight: float = 1.2
    same_category_penalty: float = 1.2

    aligned_share: float = 0.7
    novel_share: float = 0.2
    wildcard_share: float = 0.1

    # Lower temperature = more greedy, higher = more random.
    temperature: float = 0.6
    top_k: int = 150


@dataclass
class Constraints:
    """Hard limits from the user's settings. Everything else is a soft weight."""

    max_cost: int = 3
    max_difficulty: int = 5
    max_duration: Optional[int] = None
    allow_group_quests: bool = True  # accessibility 4 = "requires other people"

    def allows(self, quest: Quest) -> bool:
        if quest.cost > self.max_cost or quest.difficulty > self.max_difficulty:
            return False
        if self.max_duration is not None and quest.duration > self.max_duration:
            return False
        if not self.allow_group_quests and quest.accessibility >= 4:
            return False
        return True


@dataclass
class RecommendationContext:
    profile: PreferenceProfile
    weather: Optional[Weather] = None
    now: float = field(default_factory=time.time)
    local_hour: Optional[int] = None
    level: int = 1
    constraints: Constraints = field(default_factory=Constraints)
    exclude_ids: Set[str] = field(default_factory=set)


@dataclass
class ScoreBreakdown:
    base: float = 0.0
    category_preference: float = 0.0
    tag_preference: float = 0.0
    difficulty_preference: float = 0.0
    weather_score: float = 0.0
    novelty_bonus: float = 0.0
    cost_penalty: float = 0.0
    accessibility_penalty: float = 0.0
    repetition_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (self.base + self.category_preference + self.tag_preference + self.difficulty_preference
                + self.weather_score + self.novelty_bonus
                - self.cost_penalty - self.accessibility_penalty - self.repetition_penalty)


@dataclass
class Recommendation:
    quest: Quest
    pick_type: str
    score: ScoreBreakdown


def weather_fit(quest: Quest, weather: Optional[Weather], local_hour: Optional[int] = None) -> float:
    """How well a quest suits the current weather, roughly -1.5 .. 1.5. Never a hard veto."""
    if weather is None:
        return 0.0
    cond = weather.condition
    bad_weather = weather.is_wet or weather.is_cold or weather.is_hot or cond == "storm"
    specific = "any" not in quest.weather
    score = 0.0

    if quest.environment == "outdoor":
        if quest.suits_weather(cond):
            score += 0.4
            if cond == "clear" and not weather.is_hot and quest.category in SUNNY_CATEGORIES:
                score += 0.3
        else:
            score -= 0.8
        if weather.is_wet and not ({"rain", "storm", "snow"} & set(quest.weather)):
            score -= 0.4
        if weather.is_cold:
            # Cold: short outdoor trips are fine, long ones less so.
            score -= 0.2 + 0.5 * min(1.0, quest.duration / 120)
        if weather.is_hot:
            if HOT_WEATHER_TAGS & set(quest.tags):
                score += 0.3
            else:
                score -= 0.2 + 0.5 * min(1.0, quest.duration / 120)
        if weather.is_windy and "wind" in quest.weather:
            score += 0.3
    elif quest.environment == "indoor":
        if specific:
            score += 0.6 if quest.suits_weather(cond) else -0.6
        elif bad_weather:
            score += 0.5
        elif cond == "clear":
            score -= 0.2
    else:  # either
        if specific and not quest.suits_weather(cond):
            score -= 0.4
        elif bad_weather:
            score += 0.15

    is_night = not weather.is_day
    if local_hour is not None and (local_hour >= 22 or local_hour < 5):
        is_night = True
    if NIGHT_TAGS & set(quest.tags):
        score += 0.4 if is_night else -0.1
    elif is_night and quest.environment == "outdoor":
        score -= 0.3
    return max(-1.5, min(1.5, score))


class RecommendationEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()

    # --- scoring -----------------------------------------------------------
    def target_difficulty(self, ctx: RecommendationContext) -> float:
        """Blend the learned difficulty with a gentle level-based default."""
        level_default = min(4.0, 1.6 + 0.1 * (ctx.level - 1))
        learned = ctx.profile.preferred_difficulty
        confidence = ctx.profile.difficulty_confidence
        return confidence * learned + (1 - confidence) * level_default

    def score(self, quest: Quest, ctx: RecommendationContext) -> ScoreBreakdown:
        cfg = self.config
        profile = ctx.profile
        days = SECONDS_PER_DAY

        distance = abs(quest.difficulty - self.target_difficulty(ctx))
        difficulty = cfg.difficulty_weight * (0.5 * profile.difficulty_preference(quest.difficulty)
                                              - min(1.5, (distance / 2.0) ** 2))

        novelty = 0.0
        if not profile.has_completed(quest.id):
            novelty += 0.6
        if profile.category_completions.get(quest.category, 0) < 2:
            novelty += 0.2
        novelty += 0.4 * profile.unseen_tag_share(quest.tags)

        repetition = 0.0
        last_done = profile.last_completed.get(quest.id)
        if last_done is not None:
            age = (ctx.now - last_done) / days
            repetition += cfg.repetition_weight * max(0.0, 1 - age / cfg.repetition_window_days)
            repetition += 0.3 * min(3, profile.quest_completions[quest.id] - 1)
        last_offered = profile.last_offered.get(quest.id)
        if last_offered is not None:
            age = (ctx.now - last_offered) / days
            repetition += cfg.offered_weight * max(0.0, 1 - age / cfg.offered_window_days)
        last_skipped = profile.last_skipped.get(quest.id)
        if last_skipped is not None:
            age = (ctx.now - last_skipped) / days
            repetition += cfg.skip_weight * max(0.0, 1 - age / cfg.skip_window_days)

        weather_name = ctx.weather.condition if ctx.weather else None
        env_pref = profile.environment_preference(quest.environment, weather_name)

        return ScoreBreakdown(
            base=cfg.base_score,
            category_preference=cfg.category_weight * profile.category_preference(quest.category),
            tag_preference=cfg.tag_weight * profile.tag_preference(quest.tags),
            difficulty_preference=difficulty,
            weather_score=cfg.weather_weight * weather_fit(quest, ctx.weather, ctx.local_hour) + 0.3 * env_pref,
            novelty_bonus=cfg.novelty_weight * novelty,
            cost_penalty=cfg.cost_weight * quest.cost - 0.2 * profile.cost_preference(quest.cost),
            accessibility_penalty=cfg.accessibility_weight * max(0, quest.accessibility - 1),
            repetition_penalty=repetition,
        )

    def rank(self, quests: Iterable[Quest], ctx: RecommendationContext) -> List[Recommendation]:
        recs = [Recommendation(q, PICK_ALIGNED, self.score(q, ctx)) for q in self.candidates(quests, ctx)]
        recs.sort(key=lambda r: r.score.total, reverse=True)
        return recs

    def candidates(self, quests: Iterable[Quest], ctx: RecommendationContext) -> List[Quest]:
        return [q for q in quests if q.id not in ctx.exclude_ids and ctx.constraints.allows(q)]

    # --- slot allocation ---------------------------------------------------
    def allocate(self, count: int, rng: random.Random) -> Dict[str, int]:
        """Split ``count`` picks into aligned / novel / wildcard using the configured shares."""
        cfg = self.config
        shares = {PICK_ALIGNED: cfg.aligned_share, PICK_NOVEL: cfg.novel_share, PICK_WILDCARD: cfg.wildcard_share}
        total_share = sum(shares.values()) or 1.0
        expected = {k: count * v / total_share for k, v in shares.items()}
        counts = {k: int(math.floor(v)) for k, v in expected.items()}
        remainder = count - sum(counts.values())
        fractions = {k: expected[k] - counts[k] for k in expected}
        while remainder > 0:
            keys = [k for k in fractions if fractions[k] > 0] or list(fractions)
            weights = [max(fractions[k], 1e-6) for k in keys]
            chosen = rng.choices(keys, weights=weights)[0]
            counts[chosen] += 1
            fractions[chosen] = 0
            remainder -= 1
        # Always leave room for at least one surprise on a board of 3+ quests.
        if count >= 3 and counts[PICK_NOVEL] + counts[PICK_WILDCARD] == 0:
            counts[PICK_ALIGNED] -= 1
            counts[PICK_NOVEL] += 1
        if count >= 1 and counts[PICK_ALIGNED] == 0:
            # The priority quest comes from the aligned pool.
            donor = PICK_NOVEL if counts[PICK_NOVEL] else PICK_WILDCARD
            counts[donor] -= 1
            counts[PICK_ALIGNED] += 1
        return counts

    # --- selection ---------------------------------------------------------
    def _weighted_pick(self, recs: Sequence[Recommendation], rng: random.Random,
                       key=lambda r: r.score.total) -> Optional[Recommendation]:
        if not recs:
            return None
        pool = sorted(recs, key=key, reverse=True)[: self.config.top_k]
        top = key(pool[0])
        temperature = max(0.05, self.config.temperature)
        weights = [math.exp((key(r) - top) / temperature) for r in pool]
        return rng.choices(pool, weights=weights)[0]

    def pick_aligned(self, recs: Sequence[Recommendation], rng: random.Random,
                     chosen_categories: Sequence[str] = ()) -> Optional[Recommendation]:
        penalty = self.config.same_category_penalty

        def key(r: Recommendation) -> float:
            return r.score.total - penalty * chosen_categories.count(r.quest.category)

        rec = self._weighted_pick(recs, rng, key)
        return Recommendation(rec.quest, PICK_ALIGNED, rec.score) if rec else None

    def novel_pool(self, recs: Sequence[Recommendation], ctx: RecommendationContext) -> List[Recommendation]:
        profile = ctx.profile
        pool = [r for r in recs if not profile.has_completed(r.quest.id)
                and (profile.category_completions.get(r.quest.category, 0) <= self._median_category_count(ctx)
                     or profile.unseen_tag_share(r.quest.tags) >= 0.5)]
        return pool or [r for r in recs if not profile.has_completed(r.quest.id)] or list(recs)

    def pick_novel(self, recs: Sequence[Recommendation], ctx: RecommendationContext, rng: random.Random,
                   chosen_categories: Sequence[str] = ()) -> Optional[Recommendation]:
        pool = self.novel_pool(recs, ctx)
        preferred = [r for r in pool if r.quest.category not in chosen_categories] or pool
        # Novel picks care about novelty and weather, and only lightly about preference.
        rec = self._weighted_pick(
            preferred, rng,
            key=lambda r: 2 * r.score.novelty_bonus + r.score.weather_score + 0.3 * r.score.total
            - r.score.repetition_penalty)
        return Recommendation(rec.quest, PICK_NOVEL, rec.score) if rec else None

    def wildcard_pool(self, recs: Sequence[Recommendation], ctx: RecommendationContext) -> List[Recommendation]:
        """Quests from outside the user's usual patterns."""
        profile = ctx.profile
        category_counts = {r.quest.category: profile.category_completions.get(r.quest.category, 0) for r in recs}
        if not category_counts:
            return []
        ordered = sorted(set(category_counts), key=lambda c: (category_counts[c], profile.category_preference(c)))
        rare_categories = set(ordered[: max(1, len(ordered) // 3)])
        target = self.target_difficulty(ctx)
        pool = []
        for r in recs:
            q = r.quest
            if r.score.weather_score < -0.8 or r.score.repetition_penalty > 0.5:
                continue  # a surprise, not a punishment
            unusual = (q.category in rare_categories
                       or abs(q.difficulty - target) >= 1.5
                       or profile.unseen_tag_share(q.tags) == 1.0)
            if unusual:
                pool.append(r)
        return pool

    def pick_wildcard(self, recs: Sequence[Recommendation], ctx: RecommendationContext, rng: random.Random,
                      chosen_categories: Sequence[str] = ()) -> Optional[Recommendation]:
        pool = self.wildcard_pool(recs, ctx)
        pool = [r for r in pool if r.quest.category not in chosen_categories] or pool
        if not pool:
            return None
        # Deliberately ignore preference: a uniform draw from the unusual pool.
        rec = rng.choice(pool)
        return Recommendation(rec.quest, PICK_WILDCARD, rec.score)

    def pick(self, pick_type: str, recs: Sequence[Recommendation], ctx: RecommendationContext,
             rng: random.Random, chosen_categories: Sequence[str] = ()) -> Optional[Recommendation]:
        if pick_type == PICK_WILDCARD:
            return (self.pick_wildcard(recs, ctx, rng, chosen_categories)
                    or self.pick_novel(recs, ctx, rng, chosen_categories))
        if pick_type == PICK_NOVEL:
            return self.pick_novel(recs, ctx, rng, chosen_categories)
        return self.pick_aligned(recs, rng, chosen_categories)

    def recommend(self, quests: Iterable[Quest], ctx: RecommendationContext, count: int,
                  rng: Optional[random.Random] = None) -> List[Recommendation]:
        """Pick ``count`` quests. The first one is always the best fit for the priority slot."""
        rng = rng or random.Random()
        recs = self.rank(quests, ctx)
        if not recs or count <= 0:
            return []
        counts = self.allocate(min(count, len(recs)), rng)
        order = [PICK_ALIGNED] * counts[PICK_ALIGNED] + [PICK_NOVEL] * counts[PICK_NOVEL] \
            + [PICK_WILDCARD] * counts[PICK_WILDCARD]

        chosen: List[Recommendation] = []
        remaining = list(recs)
        for index, pick_type in enumerate(order):
            categories = [c.quest.category for c in chosen]
            if index == 0:
                rec = self.pick_priority(remaining, rng)
            else:
                rec = self.pick(pick_type, remaining, ctx, rng, categories)
            if rec is None:
                continue
            chosen.append(rec)
            remaining = [r for r in remaining if r.quest.id != rec.quest.id]
        # Keep the priority quest first, shuffle the rest so surprises aren't always last.
        rest = chosen[1:]
        rng.shuffle(rest)
        return chosen[:1] + rest

    def pick_priority(self, recs: Sequence[Recommendation], rng: random.Random) -> Optional[Recommendation]:
        """The priority quest should feel like a real quest: slightly favour moderate+ difficulty."""

        def key(r: Recommendation) -> float:
            return r.score.total + (0.3 if r.quest.difficulty >= 2 else 0.0)

        rec = self._weighted_pick(recs, rng, key)
        return Recommendation(rec.quest, PICK_ALIGNED, rec.score) if rec else None

    def recommend_one(self, quests: Iterable[Quest], ctx: RecommendationContext, rng: random.Random,
                      pick_type: str = PICK_ALIGNED, avoid_categories: Sequence[str] = ()) -> Optional[Recommendation]:
        """A single replacement quest of the requested kind."""
        recs = self.rank(quests, ctx)
        return self.pick(pick_type, recs, ctx, rng, list(avoid_categories))

    @staticmethod
    def _median_category_count(ctx: RecommendationContext) -> float:
        counts = sorted(ctx.profile.category_completions.values())
        if not counts:
            return 0
        return counts[len(counts) // 2]
