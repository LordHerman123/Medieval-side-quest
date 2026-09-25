"""Quest Library: browse, search and filter every quest; open details; create your own."""

from __future__ import annotations

from typing import Optional

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.stacklayout import StackLayout

from core.models import ACCESSIBILITY_LABELS, DIFFICULTY_LABELS, Quest
from core.quest_engine import QuestFilter
from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.common import QuestButton, ThemedInput, ThemedSpinner, WrapLabel
from ui.widgets.dialogs import ConfirmDialog, QuestDetailDialog
from ui.widgets.quest_card import quest_meta_line
from ui.widgets.scroll import ROLL_EDGE, ROLL_LIGHT, ROLL_MID

ANY = "Any"
DIFFICULTY_OPTIONS = {f"Difficulty: {v}": k for k, v in DIFFICULTY_LABELS.items()}
COST_OPTIONS = {"Free only": 0, "Cheap or free": 1, "Moderate or less": 2}
ACCESS_OPTIONS = {f"Up to: {v}": k for k, v in ACCESSIBILITY_LABELS.items() if k < 4}
DURATION_OPTIONS = {"15 min or less": 15, "30 min or less": 30, "1 hour or less": 60, "2 hours or less": 120,
                    "Half a day or less": 240}
ENV_OPTIONS = {"Indoor": "indoor", "Outdoor": "outdoor"}
SOURCE_OPTIONS = {"All quests": False, "My quests": True}


class QuestRow(ButtonBehavior, BoxLayout):
    quest_id = StringProperty("")
    title = StringProperty("")
    meta = StringProperty("")
    stripe = ListProperty(theme.LEATHER)

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=(dp(26), dp(9), dp(20), dp(9)), spacing=dp(2), **kwargs)
        self.title_label = Label(color=theme.INK, bold=True, font_size=theme.FONT_SIZE, halign="left",
                                 valign="middle", shorten=True, shorten_from="right")
        self.meta_label = Label(color=theme.INK_SOFT, font_size=theme.FONT_SMALL, halign="left", valign="middle",
                                shorten=True, shorten_from="right")
        for lbl in (self.title_label, self.meta_label):
            lbl.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            self.add_widget(lbl)
        self.bind(title=lambda *_: setattr(self.title_label, "text", self.title),
                  meta=lambda *_: setattr(self.meta_label, "text", self.meta),
                  pos=self._draw, size=self._draw, stripe=self._draw, state=self._draw)

    def _draw(self, *_):
        """A small scroll unrolled sideways: paper between two upright rolls."""
        self.canvas.before.clear()
        roll = dp(12)
        with self.canvas.before:
            Color(0, 0, 0, 0.3)
            Rectangle(pos=(self.x + roll / 2 + dp(2), self.y + dp(1)), size=(self.width - roll, self.height - dp(6)))
            Color(*(theme.PARCHMENT_DARK if self.state == "down" else theme.PARCHMENT))
            Rectangle(pos=(self.x + roll / 2, self.y + dp(3)), size=(self.width - roll, self.height - dp(6)))
            Color(*self.stripe[:3], 0.85)
            Rectangle(pos=(self.x + roll + dp(3), self.y + dp(3)), size=(dp(4), self.height - dp(6)))
            for i in range(4):
                Color(0.35, 0.25, 0.1, 0.12 * (1 - i / 4))
                Rectangle(pos=(self.x + self.width - roll / 2 - dp(3) * (i + 1), self.y + dp(3)), size=(dp(3), self.height - dp(6)))
            for rx in (self.x, self.x + self.width - roll):
                Color(*ROLL_EDGE)
                RoundedRectangle(pos=(rx, self.y), size=(roll, self.height), radius=[roll / 2])
                Color(*ROLL_MID)
                RoundedRectangle(pos=(rx + dp(1.5), self.y + dp(2)), size=(roll - dp(3), self.height - dp(4)),
                                 radius=[roll / 2])
                Color(*ROLL_LIGHT)
                RoundedRectangle(pos=(rx + roll * 0.55, self.y + dp(5)), size=(roll * 0.2, self.height - dp(10)),
                                 radius=[roll * 0.1])

    def on_release(self):
        screen = self.parent.parent.screen if self.parent and self.parent.parent else None
        if screen is not None:
            screen.open_quest(self.quest_id)


class QuestList(RecycleView):
    def __init__(self, screen, **kwargs):
        super().__init__(**kwargs)
        self.screen = screen
        self.bar_width = dp(4)
        self.bar_color = theme.GOLD_DARK
        layout = RecycleBoxLayout(orientation="vertical", default_size=(None, dp(64)), default_size_hint=(1, None),
                                  size_hint_y=None, spacing=dp(6), padding=(0, 0, 0, dp(24)))
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)
        # Must be set after the layout manager exists, or RecycleView silently drops it.
        self.viewclass = QuestRow


class LibraryScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.outer = BoxLayout(orientation="vertical", padding=theme.PADDING, spacing=dp(8))
        self.add_widget(self.outer)
        self._search_event = None

        top = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.search = ThemedInput(hint_text="Search quests, themes, places…")
        self.search.bind(text=self._search_changed)
        top.add_widget(self.search)
        self.filter_toggle = QuestButton(text="Filters", variant="leather", size_hint_x=None, width=dp(86))
        self.filter_toggle.bind(on_release=lambda *_: self.toggle_filters())
        top.add_widget(self.filter_toggle)
        new = QuestButton(text="+ New", variant="gold", size_hint_x=None, width=dp(78))
        new.bind(on_release=lambda *_: self.app.edit_quest(None))
        top.add_widget(new)
        self.outer.add_widget(top)

        self.filters = StackLayout(size_hint_y=None, spacing=dp(6))
        self.filters.bind(minimum_height=self.filters.setter("height"))
        self.spinners = {}
        self._add_spinner("category", "All categories", [])
        self._add_spinner("difficulty", "Any difficulty", list(DIFFICULTY_OPTIONS))
        self._add_spinner("cost", "Any cost", list(COST_OPTIONS))
        self._add_spinner("access", "Any access", list(ACCESS_OPTIONS))
        self._add_spinner("duration", "Any length", list(DURATION_OPTIONS))
        self._add_spinner("environment", "Indoor & outdoor", list(ENV_OPTIONS))
        self._add_spinner("source", "All quests", list(SOURCE_OPTIONS)[1:])
        clear = QuestButton(text="Clear filters", variant="ghost", size_hint=(None, None), width=dp(118),
                            height=dp(38), font_size=theme.FONT_SMALL)
        clear.color = theme.TEXT_MUTED
        clear.bind(on_release=lambda *_: self.clear_filters())
        self.filters.add_widget(clear)
        self.filters_visible = False

        self.count_label = WrapLabel(text="", color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL)
        self.outer.add_widget(self.count_label)
        self.list = QuestList(self)
        self.outer.add_widget(self.list)

    def _add_spinner(self, key: str, default: str, options):
        spinner = ThemedSpinner(text=default, values=[default] + list(options), size_hint=(None, None), width=dp(150))
        spinner.default_text = default
        spinner.bind(text=lambda *_: self.refresh())
        self.spinners[key] = spinner
        self.filters.add_widget(spinner)

    def toggle_filters(self, visible: Optional[bool] = None) -> None:
        self.filters_visible = (not self.filters_visible) if visible is None else visible
        if self.filters_visible and self.filters.parent is None:
            self.outer.add_widget(self.filters, index=len(self.outer.children) - 1)
        elif not self.filters_visible and self.filters.parent is not None:
            self.outer.remove_widget(self.filters)
        self.filter_toggle.variant = "gold" if self.filters_visible else "leather"

    def clear_filters(self) -> None:
        for spinner in self.spinners.values():
            spinner.text = spinner.default_text
        self.search.text = ""
        self.refresh()

    def _search_changed(self, *_):
        if self._search_event is not None:
            self._search_event.cancel()
        self._search_event = Clock.schedule_once(lambda dt: self.refresh(), 0.25)

    def _value(self, key: str, mapping):
        spinner = self.spinners[key]
        return None if spinner.text == spinner.default_text else mapping.get(spinner.text)

    def current_filter(self) -> QuestFilter:
        category = self.spinners["category"]
        return QuestFilter(
            category=None if category.text == category.default_text else category.text,
            difficulty=self._value("difficulty", DIFFICULTY_OPTIONS),
            max_cost=self._value("cost", COST_OPTIONS),
            max_accessibility=self._value("access", ACCESS_OPTIONS),
            max_duration=self._value("duration", DURATION_OPTIONS),
            environment=self._value("environment", ENV_OPTIONS),
            search=self.search.text.strip(),
            custom_only=bool(self._value("source", SOURCE_OPTIONS)),
        )

    def refresh(self) -> None:
        category = self.spinners["category"]
        category.values = [category.default_text] + sorted(self.game.library.category_names)
        quests = sorted(self.game.library.filter(self.current_filter()),
                        key=lambda q: (not q.custom, q.category, q.difficulty, q.title))
        total = len(self.game.library)
        self.count_label.text = f"{len(quests)} of {total} quests"
        self.list.data = [{
            "quest_id": q.id,
            "title": q.title,
            "meta": f"{quest_meta_line(q)}  ·  {q.duration} min  ·  +{q.xp} XP",
            "stripe": theme.hex_color(self.game.library.category(q.category).color),
        } for q in quests]
        if not quests:
            self.count_label.text = "No quests match. Loosen a filter, or write your own quest."

    # --- details & actions ---------------------------------------------------------
    def open_quest(self, quest_id: str) -> None:
        quest = self.game.library.get(quest_id)
        if quest is None:
            return
        open_ids = {e.quest_id for e in self.game.today_board() if e.is_open and e.status == "accepted"}
        QuestDetailDialog(
            quest,
            theme.hex_color(self.game.library.category(quest.category).color),
            on_take=None if quest.id in open_ids else self.take_quest,
            on_edit=self.app.edit_quest if quest.custom else None,
            on_delete=self.confirm_delete if quest.custom else None,
        ).open()

    def take_quest(self, quest: Quest) -> None:
        try:
            self.game.select_manually(quest.id)
        except ValueError as exc:
            self.app.toast(str(exc))
            return
        self.app.toast("Quest taken! It awaits you on Today's board.")
        self.app.go("today")

    def confirm_delete(self, quest: Quest) -> None:
        def delete():
            self.game.delete_custom_quest(quest.id)
            self.app.toast("Quest struck from the library.")
            self.refresh()

        ConfirmDialog("Delete this quest?", f"“{quest.title}” will be removed. Your journey history keeps "
                      "any time you completed it.", "Delete", delete, danger=True).open()
