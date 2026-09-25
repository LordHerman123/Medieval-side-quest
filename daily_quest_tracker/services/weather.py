"""Optional weather lookups via the free Open-Meteo API (no key required).

The app never depends on this: every public method swallows network and
parsing errors and returns cached data or ``None``, in which case the
recommender simply treats the weather as neutral.

Only the standard library is used (``urllib``), which keeps it friendly to
python-for-android. ``certifi`` is used for TLS certificates when installed.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol

from core.models import Weather

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_KEY = "weather_cache"
CACHE_TTL_SECONDS = 30 * 60
MAX_STALE_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = 8
WINDY_KMH = 35

WMO_DESCRIPTIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def condition_from_code(code: int, wind_speed: float = 0.0) -> str:
    """Map a WMO weather code to one of the quest weather conditions."""
    if code in (0, 1):
        condition = "clear"
    elif code in (2, 3):
        condition = "cloudy"
    elif code in (45, 48):
        condition = "fog"
    elif 51 <= code <= 67 or 80 <= code <= 82:
        condition = "rain"
    elif 71 <= code <= 77 or code in (85, 86):
        condition = "snow"
    elif code >= 95:
        condition = "storm"
    else:
        condition = "cloudy"
    if condition in ("clear", "cloudy") and wind_speed >= WINDY_KMH:
        condition = "wind"
    return condition


def parse_forecast(data: Dict[str, Any], location_name: str = "") -> Weather:
    current = data["current"]
    daily = data.get("daily", {})

    def first(key: str) -> Any:
        values = daily.get(key) or [None]
        return values[0]

    code = int(current.get("weather_code", 3))
    wind = float(current.get("wind_speed_10m") or 0.0)
    return Weather(
        condition=condition_from_code(code, wind),
        temperature=float(current["temperature_2m"]),
        precipitation=float(current.get("precipitation") or 0.0),
        precipitation_probability=float(first("precipitation_probability_max") or 0.0),
        wind_speed=wind,
        sunrise=first("sunrise"),
        sunset=first("sunset"),
        is_day=bool(current.get("is_day", 1)),
        description=WMO_DESCRIPTIONS.get(code, "Unsettled"),
        fetched_at=time.time(),
        location_name=location_name,
    )


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # certifi missing or broken: fall back to system certificates
        return ssl.create_default_context()


def http_get_json(url: str, timeout: float = REQUEST_TIMEOUT) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "DailyQuestTracker/1.0"})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


class CacheStore(Protocol):
    def get_setting(self, key: str, default: Any = None) -> Any: ...

    def set_setting(self, key: str, value: Any) -> None: ...


@dataclass
class Place:
    name: str
    latitude: float
    longitude: float
    country: str = ""
    region: str = ""

    @property
    def label(self) -> str:
        return ", ".join(p for p in (self.name, self.region, self.country) if p)


class WeatherService:
    def __init__(self, cache: Optional[CacheStore] = None,
                 fetch_json: Callable[[str], Dict[str, Any]] = http_get_json,
                 clock: Callable[[], float] = time.time):
        self._cache = cache
        self._fetch_json = fetch_json
        self._clock = clock

    def forecast_url(self, latitude: float, longitude: float) -> str:
        params = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "temperature_2m,precipitation,weather_code,wind_speed_10m,is_day",
            "daily": "sunrise,sunset,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": "1",
        }
        return f"{FORECAST_URL}?{urllib.parse.urlencode(params)}"

    def cached(self, max_age: float = MAX_STALE_SECONDS) -> Optional[Weather]:
        if self._cache is None:
            return None
        try:
            data = self._cache.get_setting(CACHE_KEY)
            if not data:
                return None
            weather = Weather.from_dict(data)
            if self._clock() - weather.fetched_at > max_age:
                return None
            return weather
        except Exception:
            log.exception("Ignoring unreadable weather cache")
            return None

    def get_weather(self, latitude: Optional[float], longitude: Optional[float],
                    location_name: str = "", force: bool = False) -> Optional[Weather]:
        """Current weather, or a recent cached copy, or ``None``. Never raises."""
        if latitude is None or longitude is None:
            return None
        fresh = None if force else self.cached(CACHE_TTL_SECONDS)
        if fresh is not None and fresh.location_name == location_name:
            return fresh
        try:
            weather = parse_forecast(self._fetch_json(self.forecast_url(latitude, longitude)), location_name)
            weather.fetched_at = self._clock()
        except Exception as exc:  # network down, API changed, DNS failure...
            log.info("Weather unavailable (%s); continuing without it", exc)
            return self.cached()
        if self._cache is not None:
            try:
                self._cache.set_setting(CACHE_KEY, weather.to_dict())
            except Exception:
                log.exception("Could not cache weather")
        return weather

    def search_places(self, name: str, count: int = 5) -> List[Place]:
        """Look up a town by name. Returns an empty list on any failure."""
        name = name.strip()
        if not name:
            return []
        url = f"{GEOCODE_URL}?{urllib.parse.urlencode({'name': name, 'count': count, 'format': 'json'})}"
        try:
            data = self._fetch_json(url)
            return [Place(name=r["name"], latitude=float(r["latitude"]), longitude=float(r["longitude"]),
                          country=r.get("country", ""), region=r.get("admin1", ""))
                    for r in data.get("results") or []]
        except Exception as exc:
            log.info("Place search failed (%s)", exc)
            return []


def describe_influence(weather: Optional[Weather]) -> str:
    """A short in-world line explaining how the weather shapes today's quests."""
    if weather is None:
        return "The skies keep their secrets today. Quests are chosen without the weather."
    if weather.condition == "storm":
        return "A storm rages. The hearth calls; indoor quests are favoured."
    if weather.condition in ("rain",) or weather.is_wet:
        return "Rain on the road. Indoor quests are favoured, but a brave soul may still venture out."
    if weather.condition == "snow":
        return "Snow blankets the land. Short outdoor trips and cosy indoor quests are favoured."
    if weather.is_hot:
        return "The sun blazes. Seek water, shade, or the cool of morning and evening."
    if weather.is_cold:
        return "A bitter chill. Shorter outdoor quests and warm indoor ones are favoured."
    if weather.condition == "wind":
        return "A strong wind blows. Perhaps a good day for kites."
    if weather.condition == "fog":
        return "Mist hangs over the land. A mysterious day for wandering."
    if weather.condition == "clear":
        return "Fair skies! Exploration and nature quests are favoured."
    return "Grey skies, but the road is dry. Any quest will do."
