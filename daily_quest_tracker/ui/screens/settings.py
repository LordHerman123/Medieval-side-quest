"""Settings: location & weather, quest preferences, and a progress reset."""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider

from core.models import DIFFICULTY_LABELS
from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.common import (
    OnOffToggle,
    Panel,
    QuestButton,
    SectionHeader,
    ThemedInput,
    ThemedSpinner,
    WrapLabel,
    format_temperature,
)
from ui.widgets.dialogs import ConfirmDialog

COUNT_CHOICES = {f"{n} side quests": n for n in range(2, 7)}
COST_CHOICES = {"Free quests only": 0, "Up to cheap": 1, "Up to moderate": 2, "Any cost": 3}
DIFFICULTY_CHOICES = {f"Up to {label}": level for level, label in DIFFICULTY_LABELS.items()}
UNIT_CHOICES = {"Celsius": "C", "Fahrenheit": "F"}


def setting_row(title: str, widget, hint: str = "") -> BoxLayout:
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
    box.add_widget(WrapLabel(text=title, bold=True, font_size=theme.FONT_SMALL))
    if hint:
        box.add_widget(WrapLabel(text=hint, color=theme.INK_SOFT, font_size=theme.FONT_SMALL))
    box.add_widget(widget)
    box.bind(minimum_height=box.setter("height"))
    return box


def switch_row(title: str, active: bool, on_change) -> BoxLayout:
    row = BoxLayout(size_hint_y=None, height=dp(40))
    lbl = Label(text=title, color=theme.INK, bold=True, font_size=theme.FONT_SMALL, halign="left", valign="middle")
    lbl.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
    row.add_widget(lbl)
    switch = OnOffToggle(active=active)
    switch.bind(active=lambda _, value: on_change(value))
    anchor = AnchorLayout(size_hint_x=None, width=dp(80), anchor_x="right")
    anchor.add_widget(switch)
    row.add_widget(anchor)
    return row


class SettingsScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()

    def refresh(self) -> None:
        game = self.game
        col = self.column
        col.clear_widgets()

        # --- weather ---------------------------------------------------------
        col.add_widget(SectionHeader("Weather & Location"))
        panel = Panel(spacing=dp(8))
        location = game.setting("location_name") or "not set"
        self.location_label = WrapLabel(text=f"Home town: {location}", bold=True)
        panel.add_widget(self.location_label)
        search_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.place_input = ThemedInput(hint_text="Search your town or city")
        self.place_input.bind(on_text_validate=lambda *_: self.search_places())
        search_row.add_widget(self.place_input)
        find = QuestButton(text="Find", variant="leather", size_hint_x=None, width=dp(80))
        find.bind(on_release=lambda *_: self.search_places())
        search_row.add_widget(find)
        panel.add_widget(search_row)
        self.place_results = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=dp(4))
        self.place_results.bind(minimum_height=self.place_results.setter("height"))
        panel.add_widget(self.place_results)
        self.weather_status = WrapLabel(text=self._weather_status(), color=theme.INK_SOFT, font_size=theme.FONT_SMALL)
        panel.add_widget(self.weather_status)
        panel.add_widget(switch_row("Let the weather guide quests", bool(game.setting("weather_enabled")),
                                    self._toggle_weather))
        units = ThemedSpinner(text=next(k for k, v in UNIT_CHOICES.items() if v == game.setting("temperature_unit")),
                              values=list(UNIT_CHOICES))
        units.bind(text=lambda _, t: game.set_setting("temperature_unit", UNIT_CHOICES[t]))
        panel.add_widget(setting_row("Temperature", units))
        refresh = QuestButton(text="Refresh weather now", variant="ghost")
        refresh.bind(on_release=lambda *_: self.app.load_weather(force=True, callback=self._weather_updated))
        panel.add_widget(refresh)
        col.add_widget(panel)

        # --- quests ------------------------------------------------------------
        col.add_widget(SectionHeader("Your Quests"))
        panel = Panel(spacing=dp(10))
        panel.add_widget(self._choice("Quests each day", "Besides the priority quest. Applies from the next day.",
                                      COUNT_CHOICES, "secondary_count"))
        panel.add_widget(self._choice("Budget", "", COST_CHOICES, "max_cost"))
        panel.add_widget(self._choice("Difficulty", "", DIFFICULTY_CHOICES, "max_difficulty"))
        panel.add_widget(switch_row("Include quests that need other people", bool(game.setting("allow_group_quests")),
                                    lambda v: game.set_setting("allow_group_quests", v)))

        exploration = float(game.setting("exploration"))
        slider = Slider(min=0.1, max=0.6, value=exploration, step=0.05, size_hint_y=None, height=dp(40),
                        cursor_size=(dp(26), dp(26)))
        self.exploration_label = WrapLabel(text=self._exploration_text(exploration), color=theme.INK_SOFT,
                                           font_size=theme.FONT_SMALL)
        slider.bind(value=self._exploration_changed)
        panel.add_widget(setting_row("Sense of adventure", slider,
                                     "How often the app offers something outside your usual favourites."))
        panel.add_widget(self.exploration_label)
        col.add_widget(panel)

        # --- data ----------------------------------------------------------------
        col.add_widget(SectionHeader("Your Journey"))
        panel = Panel(spacing=dp(8))
        panel.add_widget(WrapLabel(text="Everything is stored on this device. Nothing is sent anywhere except the "
                                        "optional weather lookup for your town.", color=theme.INK_SOFT,
                                   font_size=theme.FONT_SMALL))
        reset = QuestButton(text="Start a new journey (reset progress)", variant="ghost")
        reset.bind(on_release=lambda *_: self.confirm_reset())
        panel.add_widget(reset)
        col.add_widget(panel)
        col.add_widget(WrapLabel(text="Daily Quest Tracker · Weather data by Open-Meteo.com",
                                 color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center"))

    # --- helpers ---------------------------------------------------------------
    def _choice(self, title, hint, choices, key):
        current = self.game.setting(key)
        text = next((k for k, v in choices.items() if v == current), list(choices)[-1])
        spinner = ThemedSpinner(text=text, values=list(choices))
        spinner.bind(text=lambda _, t: self.game.set_setting(key, choices[t]))
        return setting_row(title, spinner, hint)

    def _exploration_text(self, value: float) -> str:
        pct = round(value * 100)
        return f"About {100 - pct}% familiar favourites, {pct}% new paths and wildcards."

    def _exploration_changed(self, _, value):
        self.game.set_setting("exploration", round(value, 2))
        self.exploration_label.text = self._exploration_text(value)

    def _weather_status(self) -> str:
        weather = self.game.weather
        if not self.game.setting("weather_enabled"):
            return "Weather is switched off. Quests are chosen without it."
        if self.game.setting("latitude") is None:
            return "Set your town to enable weather-aware quests."
        if self.app.weather_pending:
            return "Reading the clouds…"
        if weather is None:
            return "Weather unavailable right now (offline?). Quests work normally without it."
        unit = self.game.setting("temperature_unit")
        return f"Now: {weather.description}, {format_temperature(weather.temperature, unit)}"

    def _weather_updated(self):
        self.weather_status.text = self._weather_status()

    def _toggle_weather(self, value: bool):
        self.game.set_setting("weather_enabled", value)
        self.app.load_weather(callback=self._weather_updated)
        self.weather_status.text = self._weather_status()

    def search_places(self):
        name = self.place_input.text.strip()
        if not name:
            return
        self.place_results.clear_widgets()
        self.place_results.add_widget(WrapLabel(text="Searching the maps…", color=theme.INK_SOFT,
                                                font_size=theme.FONT_SMALL))

        def work():
            places = self.app.weather_service.search_places(name)
            Clock.schedule_once(lambda dt: self._show_places(places))

        threading.Thread(target=work, daemon=True).start()

    def _show_places(self, places):
        self.place_results.clear_widgets()
        if not places:
            self.place_results.add_widget(WrapLabel(
                text="No place found (or no connection). Check the spelling and try again.",
                color=theme.EMBER_DARK, font_size=theme.FONT_SMALL))
            return
        for place in places:
            button = QuestButton(text=place.label, variant="leather", font_size=theme.FONT_SMALL)
            button.bind(on_release=lambda _, p=place: self._choose_place(p))
            self.place_results.add_widget(button)

    def _choose_place(self, place):
        game = self.game
        game.set_setting("location_name", place.name)
        game.set_setting("latitude", place.latitude)
        game.set_setting("longitude", place.longitude)
        self.place_results.clear_widgets()
        self.location_label.text = f"Home town: {place.name}"
        self.app.toast(f"Home set to {place.name}.")
        self.app.load_weather(force=True, callback=self._weather_updated)
        self.weather_status.text = self._weather_status()

    def confirm_reset(self):
        def reset():
            self.game.reset_progress()
            self.app.refresh_header()
            self.app.toast("A new journey begins.")
            self.app.go("today")

        ConfirmDialog("Start a new journey?",
                      "Your XP, level, camp, history and learned preferences will be erased. Your own quests "
                      "and settings are kept. This cannot be undone.", "Reset", reset, danger=True).open()
