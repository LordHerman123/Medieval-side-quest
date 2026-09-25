import urllib.parse

import pytest

from core.models import Weather
from services.weather import (
    CACHE_TTL_SECONDS,
    WeatherService,
    condition_from_code,
    describe_influence,
    parse_forecast,
)

SAMPLE = {
    "current": {"temperature_2m": 14.2, "precipitation": 0.4, "weather_code": 61, "wind_speed_10m": 12.0,
                "is_day": 1},
    "daily": {"sunrise": ["2026-03-01T07:10"], "sunset": ["2026-03-01T18:05"],
              "precipitation_probability_max": [85]},
}


class FakeClock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def failing_fetch(url):
    raise OSError("network unreachable")


@pytest.mark.parametrize("code, expected", [
    (0, "clear"), (2, "cloudy"), (45, "fog"), (63, "rain"), (81, "rain"), (73, "snow"), (95, "storm")])
def test_wmo_codes(code, expected):
    assert condition_from_code(code) == expected


def test_strong_wind_marks_windy():
    assert condition_from_code(1, wind_speed=50) == "wind"
    assert condition_from_code(63, wind_speed=50) == "rain"


def test_parse_forecast():
    weather = parse_forecast(SAMPLE, "Ghent")
    assert weather.condition == "rain"
    assert weather.temperature == pytest.approx(14.2)
    assert weather.precipitation_probability == 85
    assert weather.sunrise == "2026-03-01T07:10"
    assert weather.is_wet
    assert weather.location_name == "Ghent"


def test_successful_fetch_is_cached(db):
    calls = []

    def fetch(url):
        calls.append(url)
        return SAMPLE

    clock = FakeClock()
    service = WeatherService(db, fetch, clock)
    first = service.get_weather(51.05, 3.72, "Ghent")
    assert first.condition == "rain"
    query = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0]).query)
    assert query["latitude"] == ["51.0500"]
    # Second call inside the TTL uses the cache.
    service.get_weather(51.05, 3.72, "Ghent")
    assert len(calls) == 1
    clock.t += CACHE_TTL_SECONDS + 1
    service.get_weather(51.05, 3.72, "Ghent")
    assert len(calls) == 2


def test_fallback_to_cache_when_api_fails(db):
    clock = FakeClock()
    WeatherService(db, lambda url: SAMPLE, clock).get_weather(1, 2, "Home")
    clock.t += CACHE_TTL_SECONDS + 60
    weather = WeatherService(db, failing_fetch, clock).get_weather(1, 2, "Home")
    assert weather is not None and weather.condition == "rain"


def test_returns_none_without_cache_or_network(db):
    assert WeatherService(db, failing_fetch).get_weather(1, 2) is None
    assert WeatherService(None, failing_fetch).get_weather(1, 2) is None


def test_stale_cache_is_not_used(db):
    clock = FakeClock()
    WeatherService(db, lambda url: SAMPLE, clock).get_weather(1, 2)
    clock.t += 24 * 3600
    assert WeatherService(db, failing_fetch, clock).get_weather(1, 2) is None


def test_garbage_response_is_survived(db):
    assert WeatherService(db, lambda url: {"nonsense": True}).get_weather(1, 2) is None


def test_no_location_means_no_weather():
    service = WeatherService(None, lambda url: pytest.fail("should not fetch"))
    assert service.get_weather(None, None) is None


def test_place_search_and_failure():
    service = WeatherService(None, lambda url: {"results": [
        {"name": "Bruges", "latitude": 51.2, "longitude": 3.22, "country": "Belgium", "admin1": "Flanders"}]})
    places = service.search_places("Bruges")
    assert places[0].label == "Bruges, Flanders, Belgium"
    assert WeatherService(None, failing_fetch).search_places("Bruges") == []


def test_influence_text_always_available():
    assert "secrets" in describe_influence(None)
    assert "Indoor" in describe_influence(Weather(condition="rain", temperature=10))
    assert describe_influence(Weather(condition="clear", temperature=20))


def test_game_works_without_weather(db, clock):
    from core.game import Game

    game = Game(db, now=clock)
    game.set_weather(WeatherService(db, failing_fetch).get_weather(1, 2))
    assert game.weather is None
    assert len(game.today_board()) == 1 + game.setting("secondary_count")
