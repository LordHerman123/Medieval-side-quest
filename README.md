# Daily Quest Tracker

*What small adventure awaits me today?*

A daily quest app with a medieval fantasy look. Each day it gives you one **priority quest** and
several **side quests**: small adventures that take you a little outside your usual routine, such as
exploring a street you've never walked down, painting today's sky, learning five constellations or
cooking a medieval recipe. Completing quests earns XP. As you level up, your lone traveler by the
campfire becomes a seasoned adventurer, and the camp grows into a stronghold.

It's a normal Python/Kivy desktop app that can be packaged for Android with Buildozer.

- **306 hand-written quests** in 14 categories, with structured metadata (`daily_quest_tracker/data/quests.json`)
- **Rule-based recommendations, no AI.** Plain statistics: recency-weighted preferences, novelty,
  repetition penalties and weather fit. About 70% of picks follow your preferences, 20% are new paths and 10% are wildcards.
- **Hidden preference learning** from completions, skips, replacements, manual picks and abandoned quests
- **Optional weather** (Open-Meteo, no API key) nudges quests indoors or outdoors. The app works fine without it.
- **XP and levels with no penalties.** There are no streaks, and a missed day never costs XP.
- **A procedurally drawn camp** that reacts to your level, the time of day and the weather
- **Your own quests**: create, edit and delete them. They go through the same recommender.
- **Journey history and statistics** that celebrate what you did. Skips aren't counted as failures.
- **SQLite** for local persistence. Works offline.

## Running on desktop

Requires Python 3.9+.

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
python daily_quest_tracker/main.py
```

The desktop window starts phone-shaped (420×820). Resize it to try wider layouts, or set
`DQT_WIDTH` / `DQT_HEIGHT`. Your save file is stored in Kivy's per-user data directory. Set
`DQT_DB_PATH=/some/file.db` to use a different save, for example a throwaway one for testing.

To make quests weather-aware, open **Settings** and search for your town.

## Tests

```bash
pip install pytest
pytest
```

The tests (≈110) cover quest data validation, filtering, scoring, preference updates, novelty and
wildcard selection, daily generation, XP and levels, progression, the weather fallback, database
persistence and the full game loop. None of them start the GUI.

## Project layout

```text
daily_quest_tracker/
    main.py                     entry point (desktop and Android)
    core/                       game logic, no Kivy imports
        models.py               Quest, QuestEvent, DailyQuest, Completion, Weather
        quest_engine.py         loads quests/categories, filtering and search, custom quests
        recommendation_engine.py  scoring + aligned/novel/wildcard selection (EngineConfig)
        preference_tracker.py   event log -> PreferenceProfile (recency-weighted, shrunk)
        daily_generator.py      daily board: generate, replace, manual pick, carry-over
        leveling.py             XP rewards and the level curve
        progression.py          unlockable gear/camp items and titles
        statistics.py           journey statistics
        game.py                 application service the UI talks to
    database/
        database.py             SQLite access (settings, player, events, board, history, unlocks)
        models.py               schema, migrations, row conversion
    services/
        weather.py              Open-Meteo client with caching and graceful fallback
    data/
        quests.json             the built-in quest library
        categories.json         categories (name, colour, motto)
        progression.json        unlocks per level and character titles
    ui/                         Kivy screens and widgets (the only part that imports Kivy)
        app.py                  App, top bar, navigation, weather loading
        screens/                today, library, quest_editor, camp, journey, statistics, settings
        widgets/                camp_scene (procedural art), quest cards, dialogs, common widgets
    assets/                     fonts (DejaVu Serif), icon, presplash
    tests/
buildozer.spec                  Android packaging configuration
```

The core has no Kivy dependency. From inside `daily_quest_tracker/`, you can run the whole game loop in a Python shell:

```python
from database.database import Database
from core.game import Game

game = Game(Database(":memory:"))
board = game.today_board()
print(board[0].quest.title)
result = game.complete(board[0].quest_id)
print(result.award.total, game.level_info())
```

## How recommendations work

All tuning lives in `EngineConfig` in `core/recommendation_engine.py`, so you can change the
algorithm without touching the UI.

**Scoring.** Every quest gets a readable score:

```text
score = base
      + category_preference + tag_preference + difficulty_preference
      + weather_score + novelty_bonus
      - cost_penalty - accessibility_penalty - repetition_penalty
```

- **Preferences** come from the event log (`preference_tracker.py`). Each event has a signed weight
  (completed +1.0, manually selected +0.6, accepted +0.2, replaced −0.25, skipped −0.35, abandoned −0.4).
  Weights decay with a 45-day half-life and are shrunk toward neutral:
  `pref = Σ w·decay / (Σ |w|·decay + 3)`. One choice only nudges a preference; a pattern moves it.
- **Difficulty** compares each quest with a target that blends a level-based default and the learned
  average difficulty of your completed quests.
- **Novelty** favours quests you've never done, and categories and tags you rarely do.
- **Repetition** penalises quests completed within the last 30 days, offered in the last 3 days or
  skipped in the last 10. The penalty fades over time.
- **Weather** is a weight, never a filter. Rain favours indoor quests, sun favours outdoor
  exploration and nature, cold favours short outdoor trips, heat favours water, shade and
  morning or evening quests, and nightfall favours stargazing. In a simulation, rain gives roughly
  77% indoor quests, but outdoor ones still appear.

**Picking the day's quests.** Picks are split between three kinds (default 70/20/10, adjustable
with the "Sense of adventure" setting):

- **aligned**: a softmax-weighted random draw from the best-scoring quests
- **novel**: never-done quests from under-explored categories or with unfamiliar tags
- **wildcard**: a uniform draw from off-profile quests, such as neglected categories, unusual
  difficulty or activity types you've never tried. Wildcards earn +20% XP.

Boards of three or more quests always include at least one surprise. Quests on one board avoid
sharing a category. Each board is seeded by the date and saved, so reopening the app shows the
same quests. Quests you accepted but didn't finish carry over for up to three days.

## XP and levels

- Quest XP = difficulty base (15/25/40/60/90) + 5 per 30 minutes (up to +30).
- Bonuses: +20% for a wildcard, +10 for your first quest in a category.
- Level curve: `xp_for_level(L) = 25·(L−1)·(L+2)`, which gives 0, 100, 250, 450, 700, … Each level
  needs 50 XP more than the previous one.
- Unlocks (`data/progression.json`): 31 items from the small campfire and tunic at level 1 to the
  distant keep at level 35. Items occupy slots, so a sword replaces the dagger. The traveler's
  title goes from *Lone Traveler* to *Legend of the Realm*.

## Extending

- **Add quests:** append entries to `data/quests.json` with a unique `id`. Required fields are
  `title`, `description` and `category`. Optional fields: `difficulty` 1–5, `cost` 0–3,
  `accessibility` 0–4, `duration` (minutes), `environment` (`indoor`/`outdoor`/`either`),
  `weather` (`any` or any of `clear, cloudy, fog, rain, snow, storm, wind`), `tags` and `xp`
  (derived from difficulty and duration when omitted). `tests/test_quest_data.py` validates the file.
- **Add a category:** add it to `data/categories.json` with a colour. No code changes needed.
- **Add unlocks:** add items to `data/progression.json`. To draw a new slot in the camp, add a
  drawing method in `ui/widgets/camp_scene.py`.
- **Schema changes:** bump `SCHEMA_VERSION` and add a migration in `database/models.py`.

## Android packaging

The app is built to package with Buildozer/python-for-android without code changes:

- Pure-Python dependencies only: Kivy, and the standard library's `sqlite3`, `urllib`, `json` and `ssl`.
- The save file lives in `App.user_data_dir`, which is app-private storage on Android.
- Network is optional. Only the weather uses it, from a background thread with a timeout.
- The Android back button goes back to Today instead of closing the app, and the app keeps its
  state when paused.
- The UI uses `dp`/`sp` units, a centred max-width column and scrolling screens, so it adapts to
  phone and desktop sizes.

### Build steps

Buildozer runs on Linux or macOS. On Windows, use WSL2.

```bash
# 1. System packages (Ubuntu/Debian)
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev

# 2. Buildozer and Cython
pip install --user --upgrade buildozer cython

# 3. From the repository root (where buildozer.spec is)
buildozer -v android debug          # first run downloads the Android SDK/NDK (slow)

# 4. Install on a phone with USB debugging enabled
buildozer android deploy run logcat
```

The APK is written to `bin/`. For a Play Store build, run `buildozer android release`. That
produces an `.aab` file, which you must sign with your own keystore.

Useful notes:

- `buildozer.spec` sets `source.dir = daily_quest_tracker` and excludes `tests/`.
- `requirements` includes `sqlite3` and `openssl`. python-for-android needs these recipes for
  the standard-library `sqlite3` and `ssl` modules.
- `android.permissions = INTERNET` is used only for the weather lookup.
- To view the app's logs: `buildozer android logcat | grep python`.
- If a build fails after you change requirements, run `buildozer android clean` and rebuild.

## Design notes

- **Kivy without KivyMD.** The medieval look needs custom-drawn widgets anyway (parchment panels,
  ember buttons, the camp scene). KivyMD 2.x is not yet released on PyPI and 1.x is deprecated, so
  plain Kivy has fewer packaging risks for python-for-android. Everything is themed from `ui/theme.py`.
- **No image assets for the scene.** The camp is drawn with canvas primitives. That keeps the APK
  small and lets gear, animals, NPCs, structures, weather and time of day combine freely.
- **Fonts.** DejaVu Serif is bundled under its permissive licence (`assets/fonts/DejaVu-LICENSE.txt`).
- **Weather data** comes from [Open-Meteo](https://open-meteo.com/) (free, no key).
