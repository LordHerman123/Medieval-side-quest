"""Plain domain objects shared by the core systems.

Nothing in here depends on Kivy or SQLite, so every core module (and the
tests) can use these without starting the GUI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

DIFFICULTY_LABELS = {1: "Easy", 2: "Moderate", 3: "Challenging", 4: "Adventurous", 5: "Epic"}
COST_LABELS = {0: "Free", 1: "Cheap", 2: "Moderate cost", 3: "Expensive"}
ACCESSIBILITY_LABELS = {
    0: "Very accessible",
    1: "Accessible",
    2: "Requires preparation",
    3: "Requires travel",
    4: "Requires other people",
}
ENVIRONMENTS = ("indoor", "outdoor", "either")
WEATHER_CONDITIONS = ("clear", "cloudy", "fog", "rain", "snow", "storm", "wind")
ANY_WEATHER = "any"

# Quest statuses used for the daily quest board.
STATUS_OFFERED = "offered"
STATUS_ACCEPTED = "accepted"
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_REPLACED = "replaced"
STATUS_ABANDONED = "abandoned"

# How a quest ended up on the daily board.
PICK_ALIGNED = "aligned"
PICK_NOVEL = "novel"
PICK_WILDCARD = "wildcard"
PICK_MANUAL = "manual"

SLOT_PRIORITY = "priority"
SLOT_SECONDARY = "secondary"


class QuestValidationError(ValueError):
    """Raised when quest data is missing fields or holds out-of-range values."""


@dataclass
class Quest:
    id: str
    title: str
    description: str
    category: str
    difficulty: int = 1
    cost: int = 0
    accessibility: int = 0
    duration: int = 30
    environment: str = "either"
    weather: List[str] = field(default_factory=lambda: [ANY_WEATHER])
    tags: List[str] = field(default_factory=list)
    xp: int = 0
    custom: bool = False

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTY_LABELS.get(self.difficulty, str(self.difficulty))

    @property
    def cost_label(self) -> str:
        return COST_LABELS.get(self.cost, str(self.cost))

    @property
    def accessibility_label(self) -> str:
        return ACCESSIBILITY_LABELS.get(self.accessibility, str(self.accessibility))

    @property
    def is_outdoor(self) -> bool:
        return self.environment == "outdoor"

    @property
    def is_indoor(self) -> bool:
        return self.environment == "indoor"

    def suits_weather(self, condition: Optional[str]) -> bool:
        if condition is None or ANY_WEATHER in self.weather:
            return True
        return condition in self.weather

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("custom")
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], custom: bool = False) -> "Quest":
        """Build a quest from a JSON/DB dict, validating every field."""
        required = ("id", "title", "description", "category")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise QuestValidationError(f"Quest is missing {', '.join(missing)}: {data!r}")

        def int_in(key: str, low: int, high: int, default: int) -> int:
            value = data.get(key, default)
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise QuestValidationError(f"{data['id']}: {key} must be a number")
            if not low <= value <= high:
                raise QuestValidationError(f"{data['id']}: {key}={value} outside {low}-{high}")
            return value

        environment = data.get("environment", "either")
        if environment not in ENVIRONMENTS:
            raise QuestValidationError(f"{data['id']}: unknown environment {environment!r}")

        weather = [str(w).lower() for w in data.get("weather") or [ANY_WEATHER]]
        for condition in weather:
            if condition != ANY_WEATHER and condition not in WEATHER_CONDITIONS:
                raise QuestValidationError(f"{data['id']}: unknown weather {condition!r}")

        tags = [str(t).strip().lower() for t in data.get("tags") or [] if str(t).strip()]
        difficulty = int_in("difficulty", 1, 5, 1)
        duration = int_in("duration", 1, 24 * 60, 30)
        xp = int(data.get("xp") or 0)
        if xp <= 0:
            # Imported lazily to keep models free of import cycles.
            from core.leveling import quest_xp

            xp = quest_xp(difficulty, duration)

        return cls(
            id=str(data["id"]),
            title=str(data["title"]).strip(),
            description=str(data["description"]).strip(),
            category=str(data["category"]).strip(),
            difficulty=difficulty,
            cost=int_in("cost", 0, 3, 0),
            accessibility=int_in("accessibility", 0, 4, 0),
            duration=duration,
            environment=environment,
            weather=weather,
            tags=tags,
            xp=xp,
            custom=custom,
        )


@dataclass
class QuestEvent:
    """One thing the user did with a quest. The preference tracker learns from these."""

    quest_id: str
    event_type: str
    timestamp: float
    category: str
    tags: List[str]
    difficulty: int
    cost: int
    accessibility: int
    environment: str
    weather: Optional[str] = None
    pick_type: Optional[str] = None


@dataclass
class DailyQuest:
    """A quest placed on a particular day's quest board."""

    date: str
    quest_id: str
    slot: str
    position: int
    pick_type: str
    status: str = STATUS_OFFERED
    quest: Optional[Quest] = None

    @property
    def is_priority(self) -> bool:
        return self.slot == SLOT_PRIORITY

    @property
    def is_open(self) -> bool:
        return self.status in (STATUS_OFFERED, STATUS_ACCEPTED)


@dataclass
class Completion:
    """A finished quest, stored as a snapshot so history survives quest edits/deletes."""

    quest_id: str
    title: str
    category: str
    difficulty: int
    duration: int
    xp: int
    date: str
    completed_at: float
    pick_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    id: Optional[int] = None


@dataclass
class Weather:
    """Current conditions, reduced to what the quest recommender cares about."""

    condition: str
    temperature: float
    precipitation: float = 0.0
    precipitation_probability: float = 0.0
    wind_speed: float = 0.0
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    is_day: bool = True
    description: str = ""
    fetched_at: float = 0.0
    location_name: str = ""

    @property
    def is_hot(self) -> bool:
        return self.temperature >= 27

    @property
    def is_cold(self) -> bool:
        return self.temperature <= 3

    @property
    def is_wet(self) -> bool:
        return self.condition in ("rain", "storm", "snow") or self.precipitation_probability >= 70

    @property
    def is_windy(self) -> bool:
        return self.wind_speed >= 35

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Weather":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
