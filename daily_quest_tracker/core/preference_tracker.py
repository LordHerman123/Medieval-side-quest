"""Hidden preference learning.

Every interaction with a quest (completing, skipping, replacing, picking it by
hand...) is stored as a :class:`~core.models.QuestEvent`. From that log we
compute a :class:`PreferenceProfile` with plain statistics:

* each event carries a signed weight (completing is a strong positive signal,
  skipping a mild negative one);
* older events count for less (exponential decay with a half-life);
* the result is shrunk towards neutral with a prior, so a single choice only
  nudges a preference and it takes a pattern to move it far.

``preference = sum(weight * decay) / (sum(|weight| * decay) + PRIOR)``

which always stays between -1 and 1.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, DefaultDict, Dict, Iterable, List, Optional, Protocol, Set

from core.models import Quest, QuestEvent

EVENT_COMPLETED = "completed"
EVENT_ACCEPTED = "accepted"
EVENT_SELECTED = "selected"  # manually chosen from the library
EVENT_SKIPPED = "skipped"
EVENT_REPLACED = "replaced"
EVENT_ABANDONED = "abandoned"
EVENT_OFFERED = "offered"

EVENT_WEIGHTS: Dict[str, float] = {
    EVENT_COMPLETED: 1.0,
    EVENT_SELECTED: 0.6,
    EVENT_ACCEPTED: 0.2,
    EVENT_SKIPPED: -0.35,
    EVENT_REPLACED: -0.25,
    EVENT_ABANDONED: -0.4,
    EVENT_OFFERED: 0.0,
}

HALF_LIFE_DAYS = 45.0
PRIOR_STRENGTH = 3.0
DEFAULT_DIFFICULTY = 2.0
SECONDS_PER_DAY = 86400.0


def recency_weight(age_seconds: float, half_life_days: float = HALF_LIFE_DAYS) -> float:
    age_days = max(0.0, age_seconds) / SECONDS_PER_DAY
    return 0.5 ** (age_days / half_life_days)


class _Tally:
    """Signed, decayed evidence for one dimension (e.g. all categories)."""

    def __init__(self) -> None:
        self.signal: DefaultDict[str, float] = defaultdict(float)
        self.volume: DefaultDict[str, float] = defaultdict(float)

    def add(self, key: str, weight: float, decay: float) -> None:
        self.signal[key] += weight * decay
        self.volume[key] += abs(weight) * decay

    def preference(self, key: str, prior: float = PRIOR_STRENGTH) -> float:
        return self.signal.get(key, 0.0) / (self.volume.get(key, 0.0) + prior)

    def as_dict(self) -> Dict[str, float]:
        return {key: self.preference(key) for key in self.signal}


@dataclass
class PreferenceProfile:
    """What we have learned about the user, as numbers the recommender can use."""

    categories: _Tally = field(default_factory=_Tally)
    tags: _Tally = field(default_factory=_Tally)
    difficulties: _Tally = field(default_factory=_Tally)
    costs: _Tally = field(default_factory=_Tally)
    environments: _Tally = field(default_factory=_Tally)
    environment_weather: _Tally = field(default_factory=_Tally)

    # Raw facts (not decayed) used for novelty and repetition.
    category_completions: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int))
    tag_completions: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int))
    quest_completions: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_completed: Dict[str, float] = field(default_factory=dict)
    last_offered: Dict[str, float] = field(default_factory=dict)
    last_skipped: Dict[str, float] = field(default_factory=dict)
    preferred_difficulty: float = DEFAULT_DIFFICULTY
    difficulty_confidence: float = 0.0
    total_completions: int = 0

    # --- lookups used by the recommendation engine -----------------------
    def category_preference(self, category: str) -> float:
        return self.categories.preference(category)

    def tag_preference(self, tags: Iterable[str]) -> float:
        tags = list(tags)
        if not tags:
            return 0.0
        return sum(self.tags.preference(t) for t in tags) / len(tags)

    def difficulty_preference(self, difficulty: int) -> float:
        return self.difficulties.preference(str(difficulty))

    def cost_preference(self, cost: int) -> float:
        return self.costs.preference(str(cost))

    def environment_preference(self, environment: str, weather: Optional[str] = None) -> float:
        base = self.environments.preference(environment)
        if weather:
            base += 0.5 * self.environment_weather.preference(f"{environment}|{weather}")
        return base

    def has_completed(self, quest_id: str) -> bool:
        return self.quest_completions.get(quest_id, 0) > 0

    def unseen_tag_share(self, tags: Iterable[str]) -> float:
        tags = list(tags)
        if not tags:
            return 0.0
        return sum(1 for t in tags if self.tag_completions.get(t, 0) == 0) / len(tags)

    @property
    def explored_categories(self) -> Set[str]:
        return {c for c, n in self.category_completions.items() if n > 0}

    # --- construction ----------------------------------------------------
    @classmethod
    def from_events(cls, events: Iterable[QuestEvent], now: Optional[float] = None) -> "PreferenceProfile":
        now = time.time() if now is None else now
        profile = cls()
        difficulty_sum = 0.0
        difficulty_weight = 0.0

        for event in sorted(events, key=lambda e: e.timestamp):
            if event.event_type == EVENT_OFFERED:
                profile.last_offered[event.quest_id] = event.timestamp
                continue

            weight = EVENT_WEIGHTS.get(event.event_type, 0.0)
            decay = recency_weight(now - event.timestamp)

            profile.categories.add(event.category, weight, decay)
            # Split the weight across tags so heavily tagged quests don't dominate.
            if event.tags:
                tag_weight = weight / max(1.0, len(event.tags) ** 0.5)
                for tag in event.tags:
                    profile.tags.add(tag, tag_weight, decay)
            profile.difficulties.add(str(event.difficulty), weight, decay)
            profile.costs.add(str(event.cost), weight, decay)
            profile.environments.add(event.environment, weight * 0.5, decay)
            if event.weather:
                profile.environment_weather.add(f"{event.environment}|{event.weather}", weight, decay)

            if event.event_type == EVENT_COMPLETED:
                profile.total_completions += 1
                profile.category_completions[event.category] += 1
                profile.quest_completions[event.quest_id] += 1
                profile.last_completed[event.quest_id] = event.timestamp
                for tag in event.tags:
                    profile.tag_completions[tag] += 1
                difficulty_sum += event.difficulty * decay
                difficulty_weight += decay
            elif event.event_type in (EVENT_SKIPPED, EVENT_REPLACED):
                profile.last_skipped[event.quest_id] = event.timestamp

        if difficulty_weight > 0:
            learned = difficulty_sum / difficulty_weight
            # Blend with the default until we've seen a handful of completions.
            confidence = difficulty_weight / (difficulty_weight + PRIOR_STRENGTH)
            profile.preferred_difficulty = confidence * learned + (1 - confidence) * DEFAULT_DIFFICULTY
            profile.difficulty_confidence = confidence
        return profile

    def summary(self, top: int = 5) -> Dict[str, List[str]]:
        """Human-readable leanings, mostly for debugging and statistics."""

        def ranked(tally: _Tally, reverse: bool) -> List[str]:
            items = sorted(tally.as_dict().items(), key=lambda kv: kv[1], reverse=reverse)
            return [k for k, v in items if (v > 0.05 if reverse else v < -0.05)][:top]

        return {
            "favoured_categories": ranked(self.categories, True),
            "favoured_tags": ranked(self.tags, True),
            "less_favoured_categories": ranked(self.categories, False),
        }


class EventStore(Protocol):
    def add_event(self, event: QuestEvent) -> None: ...

    def load_events(self) -> List[QuestEvent]: ...


class PreferenceTracker:
    """Records quest interactions and serves an up-to-date profile."""

    def __init__(self, store: EventStore, clock: Callable[[], float] = time.time):
        self._store = store
        self._clock = clock
        self._profile: Optional[PreferenceProfile] = None

    def record(self, quest: Quest, event_type: str, weather: Optional[str] = None,
               pick_type: Optional[str] = None, timestamp: Optional[float] = None) -> QuestEvent:
        if event_type not in EVENT_WEIGHTS:
            raise ValueError(f"Unknown event type {event_type!r}")
        event = QuestEvent(
            quest_id=quest.id,
            event_type=event_type,
            timestamp=self._clock() if timestamp is None else timestamp,
            category=quest.category,
            tags=list(quest.tags),
            difficulty=quest.difficulty,
            cost=quest.cost,
            accessibility=quest.accessibility,
            environment=quest.environment,
            weather=weather,
            pick_type=pick_type,
        )
        self._store.add_event(event)
        self._profile = None
        return event

    def profile(self) -> PreferenceProfile:
        if self._profile is None:
            self._profile = PreferenceProfile.from_events(self._store.load_events(), now=self._clock())
        return self._profile

    def invalidate(self) -> None:
        self._profile = None


class MemoryEventStore:
    """In-memory event store, handy for tests and experiments."""

    def __init__(self) -> None:
        self.events: List[QuestEvent] = []

    def add_event(self, event: QuestEvent) -> None:
        self.events.append(event)

    def load_events(self) -> List[QuestEvent]:
        return list(self.events)
