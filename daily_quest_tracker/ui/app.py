"""The Kivy application: wires the game core to the screens."""

from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from core.game import Game
from database.database import DB_FILENAME, Database
from services.weather import CACHE_TTL_SECONDS, WeatherService
from ui import theme
from ui.screens.camp import CampScreen
from ui.screens.journey import JourneyScreen
from ui.screens.library import LibraryScreen
from ui.screens.quest_editor import QuestEditorScreen
from ui.screens.settings import SettingsScreen
from ui.screens.statistics import StatisticsScreen
from ui.screens.today import TodayScreen
from ui.widgets.common import LevelBadge, XpBar, Toast

NAV_ITEMS = [
    ("today", "Today"),
    ("library", "Library"),
    ("camp", "Camp"),
    ("journey", "Journey"),
    ("stats", "Stats"),
    ("settings", "Settings"),
]
WEATHER_WAIT_SECONDS = 6


class TopBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(66), padding=(dp(12), dp(10)), spacing=dp(12), **kwargs)
        self.badge = LevelBadge(text="1")
        self.add_widget(self.badge)
        info = BoxLayout(orientation="vertical", spacing=dp(4))
        row = BoxLayout(size_hint_y=None, height=dp(22))
        self.title_label = Label(text="", bold=True, color=theme.TEXT, font_size=theme.FONT_SIZE, halign="left",
                                 valign="middle", shorten=True)
        self.title_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self.xp_label = Label(text="", color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="right",
                              valign="middle", size_hint_x=None, width=dp(130))
        self.xp_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        row.add_widget(self.title_label)
        row.add_widget(self.xp_label)
        info.add_widget(row)
        self.bar = XpBar(height=dp(12))
        info.add_widget(self.bar)
        self.add_widget(info)
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.BG_RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*theme.GOLD_DARK)
            Rectangle(pos=(self.x, self.y), size=(self.width, dp(1.5)))

    def update(self, game: Game) -> None:
        info = game.level_info()
        self.badge.text = str(info.level)
        self.title_label.text = game.title()
        self.xp_label.text = f"{info.xp_into_level} / {info.xp_needed} XP"
        self.bar.value = info.progress


class NavButton(Button):
    def __init__(self, screen: str, **kwargs):
        super().__init__(font_size=theme.FONT_SMALL, bold=True, **kwargs)
        self.screen = screen
        self.active = False
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def set_active(self, active: bool) -> None:
        self.active = active
        self._draw()

    def _draw(self, *_):
        self.color = theme.GOLD if self.active else theme.TEXT_MUTED
        self.canvas.before.clear()
        if self.active:
            with self.canvas.before:
                Color(*theme.GOLD)
                Rectangle(pos=(self.x + self.width * 0.2, self.top - dp(3)), size=(self.width * 0.6, dp(3)))


class NavBar(BoxLayout):
    def __init__(self, on_select: Callable[[str], None], **kwargs):
        super().__init__(size_hint_y=None, height=dp(56), **kwargs)
        self.buttons = {}
        for name, text in NAV_ITEMS:
            button = NavButton(name, text=text)
            button.bind(on_release=lambda b: on_select(b.screen))
            self.buttons[name] = button
            self.add_widget(button)
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.BG_RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*theme.GOLD_DARK)
            Rectangle(pos=(self.x, self.top - dp(1.5)), size=(self.width, dp(1.5)))

    def highlight(self, screen: str) -> None:
        for name, button in self.buttons.items():
            button.set_active(name == screen)


class DailyQuestApp(App):
    title = "Daily Quest Tracker"
    icon = os.path.join(theme.ASSETS, "images", "icon.png")

    def __init__(self, db_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self.weather_pending = False
        self._weather_waiters: List[Callable[[], None]] = []

    # --- lifecycle ---------------------------------------------------------------
    def build(self):
        theme.register_fonts()
        Window.clearcolor = theme.BG
        Window.bind(on_keyboard=self._on_key)
        self.db = Database(self._db_path or os.path.join(self.user_data_dir, DB_FILENAME))
        self.game = Game(self.db)
        self.weather_service = WeatherService(self.db)
        self.game.set_weather(self.weather_service.cached(CACHE_TTL_SECONDS))

        root = FloatLayout()
        main = BoxLayout(orientation="vertical")
        self.top_bar = TopBar()
        main.add_widget(self.top_bar)
        self.manager = ScreenManager(transition=FadeTransition(duration=0.12))
        self.screens = {
            "today": TodayScreen(self, name="today"),
            "library": LibraryScreen(self, name="library"),
            "camp": CampScreen(self, name="camp"),
            "journey": JourneyScreen(self, name="journey"),
            "stats": StatisticsScreen(self, name="stats"),
            "settings": SettingsScreen(self, name="settings"),
            "editor": QuestEditorScreen(self, name="editor"),
        }
        # Start weather before the first screen so today's quests can take it into account.
        self.load_weather()
        for screen in self.screens.values():
            self.manager.add_widget(screen)
        main.add_widget(self.manager)
        self.nav = NavBar(self.go)
        main.add_widget(self.nav)
        root.add_widget(main)
        self._toast = Toast()
        root.add_widget(self._toast)
        self.refresh_header()
        self.nav.highlight("today")
        self._shown_day = self.game.today()
        Clock.schedule_interval(self._check_new_day, 60)
        return root

    def on_pause(self):
        return True  # keep running in the background on Android

    def on_resume(self):
        self._check_new_day()

    def on_stop(self):
        self.db.close()

    # --- navigation -----------------------------------------------------------------
    def go(self, name: str) -> None:
        if self.manager.current == name:
            self.screens[name].refresh()
        self.manager.current = name
        self.nav.highlight("library" if name == "editor" else name)

    def edit_quest(self, quest) -> None:
        self.screens["editor"].edit(quest)
        self.go("editor")

    def _on_key(self, window, key, *args):
        if key == 27:  # Escape on desktop, Back on Android
            if self.manager.current == "editor":
                self.go("library")
                return True
            if self.manager.current != "today":
                self.go("today")
                return True
        return False

    def refresh_header(self) -> None:
        self.top_bar.update(self.game)

    def toast(self, text: str) -> None:
        self._toast.show(text)

    def _check_new_day(self, *_):
        today = self.game.today()
        if today != self._shown_day:
            self._shown_day = today
            self.load_weather()
            if self.manager.current == "today":
                self.screens["today"].on_enter()

    # --- weather ----------------------------------------------------------------------
    def when_weather_ready(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` now, and again once pending weather arrives (or times out)."""
        callback()
        if self.weather_pending:
            self._weather_waiters.append(callback)

    def load_weather(self, force: bool = False, callback: Optional[Callable[[], None]] = None) -> None:
        game = self.game
        lat, lon = game.setting("latitude"), game.setting("longitude")
        if not game.setting("weather_enabled") or lat is None or lon is None:
            game.set_weather(None)
            self._weather_done(callback)
            return
        if not force:
            cached = self.weather_service.cached(CACHE_TTL_SECONDS)
            if cached is not None and cached.location_name == (game.setting("location_name") or ""):
                game.set_weather(cached)
                self._weather_done(callback)
                return

        self.weather_pending = True
        name = game.setting("location_name") or ""

        def work():
            weather = self.weather_service.get_weather(lat, lon, name, force=force)
            Clock.schedule_once(lambda dt: self._weather_arrived(weather, callback))

        threading.Thread(target=work, daemon=True).start()
        # Never let a slow network hold up today's quests.
        Clock.schedule_once(lambda dt: self._weather_timeout(), WEATHER_WAIT_SECONDS)

    def _weather_arrived(self, weather, callback) -> None:
        self.game.set_weather(weather)
        self._weather_done(callback)

    def _weather_timeout(self) -> None:
        if self.weather_pending:
            self._weather_done(None)

    def _weather_done(self, callback) -> None:
        self.weather_pending = False
        waiters, self._weather_waiters = self._weather_waiters, []
        for waiter in waiters:
            waiter()
        if callback:
            callback()
        if getattr(self, "manager", None) is not None and self.manager.current == "today" and not waiters:
            self.screens["today"].refresh()
