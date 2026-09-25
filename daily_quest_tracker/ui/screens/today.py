"""Today: the campfire, the priority quest and the day's side quests."""

from __future__ import annotations

from datetime import datetime

from kivy.metrics import dp

from core.models import SLOT_PRIORITY
from services.weather import describe_influence
from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.camp_scene import CampScene, loadout_ids
from ui.widgets.common import EmptyState, QuestButton, SectionHeader, WrapLabel, format_temperature
from ui.widgets.dialogs import RewardDialog
from ui.widgets.quest_card import QuestCard


class TodayScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()
        self.scene = CampScene(size_hint_y=None, height=dp(200))
        self.column.bind(width=self._size_scene)
        self.shown_date = None

    def _size_scene(self, *_):
        self.scene.height = max(dp(170), min(dp(300), self.column.width * 0.5))

    def on_enter(self, *args):
        self.app.when_weather_ready(self.refresh)
        self.scene.start()

    def on_leave(self, *args):
        self.scene.stop()

    # --- building ---------------------------------------------------------------
    def refresh(self) -> None:
        game = self.game
        col = self.column
        col.clear_widgets()
        self.shown_date = game.today()

        self.scene.configure(loadout_ids(game.loadout()), game.level, game.weather, now=game.now())
        col.add_widget(self.scene)

        created = datetime.fromtimestamp(game.db.get_player()["created_at"]).date()
        now = game.now()
        day_number = (now.date() - created).days + 1
        col.add_widget(WrapLabel(text=f"{now:%A %d %B}  ·  Day {day_number} of your journey",
                                 color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center"))
        col.add_widget(self._weather_line())

        if self.app.weather_pending and not game.generator.has_board(game.today()):
            col.add_widget(EmptyState("Consulting the skies before choosing today's quests…"))
            return

        board = game.today_board()
        actions = {
            "accept": self.accept,
            "complete": self.complete,
            "skip": self.skip,
            "replace": self.replace,
            "abandon": self.abandon,
        }
        priority = [e for e in board if e.slot == SLOT_PRIORITY and e.is_open]
        others_open = [e for e in board if not (e.slot == SLOT_PRIORITY and e.is_open) and e.is_open]
        closed = [e for e in board if not e.is_open]

        for entry in priority:
            col.add_widget(QuestCard(entry, actions, self._color(entry.quest.category), priority=True))

        if others_open:
            col.add_widget(SectionHeader("Side Quests"))
            for entry in others_open:
                col.add_widget(QuestCard(entry, actions, self._color(entry.quest.category)))

        if not priority and not others_open:
            col.add_widget(EmptyState("Every quest for today is settled. Rest by the fire, "
                                      "or seek another adventure in the library."))

        if closed:
            col.add_widget(SectionHeader("Today's Deeds"))
            for entry in closed:
                col.add_widget(QuestCard(entry, actions, self._color(entry.quest.category)))

        more = QuestButton(text="Choose a quest from the library", variant="leather")
        more.bind(on_release=lambda *_: self.app.go("library"))
        col.add_widget(more)

    def _weather_line(self):
        game = self.game
        weather = game.weather
        if weather is not None:
            place = f"  ·  {weather.location_name}" if weather.location_name else ""
            head = f"{weather.description}  ·  {format_temperature(weather.temperature, game.setting('temperature_unit'))}{place}"
            text = f"{head}\n{describe_influence(weather)}"
        elif game.setting("weather_enabled") and game.setting("latitude") is None:
            text = "Tell the app your town in Settings and the weather will guide your quests."
        elif self.app.weather_pending:
            text = "Reading the clouds…"
        else:
            text = describe_influence(None)
        return WrapLabel(text=text, color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center", italic=True)

    def _color(self, category: str):
        return theme.hex_color(self.game.library.category(category).color)

    # --- actions -----------------------------------------------------------------
    def accept(self, quest_id: str) -> None:
        self.game.accept(quest_id)
        self.app.toast("Quest accepted. Fortune favours the curious!")
        self.refresh()

    def complete(self, quest_id: str) -> None:
        result = self.game.complete(quest_id)
        self.refresh()
        self.app.refresh_header()
        RewardDialog(result, self.game.progression.title_for_level).open()

    def skip(self, quest_id: str) -> None:
        self.game.skip(quest_id)
        self.app.toast("Another day, perhaps. The road will wait.")
        self.refresh()

    def replace(self, quest_id: str) -> None:
        if self.game.replace(quest_id) is None:
            self.app.toast("No other quest fits right now.")
        self.refresh()

    def abandon(self, quest_id: str) -> None:
        self.game.abandon(quest_id)
        self.app.toast("Set aside for now. No harm done.")
        self.refresh()
