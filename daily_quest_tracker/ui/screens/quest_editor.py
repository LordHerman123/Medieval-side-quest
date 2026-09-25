"""Create or edit a custom quest."""

from __future__ import annotations

from typing import Optional

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.togglebutton import ToggleButton

from core.models import (
    ACCESSIBILITY_LABELS,
    COST_LABELS,
    DIFFICULTY_LABELS,
    WEATHER_CONDITIONS,
    Quest,
    QuestValidationError,
)
from core.leveling import quest_xp
from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.common import QuestButton, SectionHeader, ThemedInput, ThemedSpinner, WrapLabel, button_row
from ui.widgets.dialogs import ConfirmDialog
from ui.widgets.scroll import ScrollPanel

NEW_CATEGORY = "New category…"
ENVIRONMENT_LABELS = {"Indoor": "indoor", "Outdoor": "outdoor", "Either": "either"}


def _labelled(mapping):
    return {f"{k} – {v}": k for k, v in mapping.items()}


DIFFICULTY_CHOICES = _labelled(DIFFICULTY_LABELS)
COST_CHOICES = _labelled(COST_LABELS)
ACCESS_CHOICES = _labelled(ACCESSIBILITY_LABELS)


class WeatherToggle(ToggleButton):
    def __init__(self, condition: str, **kwargs):
        super().__init__(text=condition.capitalize(), size_hint_y=None, height=dp(36), font_size=theme.FONT_SMALL,
                         **kwargs)
        self.condition = condition
        self.background_normal = ""
        self.background_down = ""
        self.bind(state=self._style)
        self._style()

    def _style(self, *_):
        self.background_color = theme.MOSS if self.state == "down" else theme.hex_color("#3A3026")
        self.color = theme.TEXT


class QuestEditorScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()
        self.quest: Optional[Quest] = None

    def edit(self, quest: Optional[Quest]) -> None:
        self.quest = quest
        self.build_form()

    def refresh(self) -> None:
        if not self.column.children:
            self.build_form()

    def _field(self, panel, title: str, widget):
        panel.add_widget(WrapLabel(text=title, bold=True, font_size=theme.FONT_SMALL))
        panel.add_widget(widget)
        return widget

    def build_form(self) -> None:
        quest = self.quest
        col = self.column
        col.clear_widgets()
        col.add_widget(SectionHeader("Edit your quest" if quest else "Write a new quest"))
        panel = ScrollPanel(spacing=dp(6), seed="editor")
        col.add_widget(panel)

        self.title_input = self._field(panel, "Title", ThemedInput(text=quest.title if quest else "",
                                                                   hint_text="e.g. Find a hidden waterfall"))
        self.description_input = self._field(panel, "Description", ThemedInput(
            text=quest.description if quest else "", multiline=True, height=dp(96),
            hint_text="What should the adventurer do?"))

        categories = sorted(self.game.library.category_names)
        self.category = self._field(panel, "Category", ThemedSpinner(
            text=quest.category if quest else categories[0], values=categories + [NEW_CATEGORY]))
        self.new_category = ThemedInput(hint_text="Name your new category")
        self.category.bind(text=self._category_changed)

        grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        def spinner(title, choices, current):
            box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(62), spacing=dp(2))
            box.add_widget(WrapLabel(text=title, bold=True, font_size=theme.FONT_SMALL))
            current_text = next(k for k, v in choices.items() if v == current)
            sp = ThemedSpinner(text=current_text, values=list(choices))
            box.add_widget(sp)
            grid.add_widget(box)
            return sp

        self.difficulty = spinner("Difficulty", DIFFICULTY_CHOICES, quest.difficulty if quest else 2)
        self.cost = spinner("Cost", COST_CHOICES, quest.cost if quest else 0)
        self.access = spinner("Accessibility", ACCESS_CHOICES, quest.accessibility if quest else 0)
        self.environment = spinner("Environment", ENVIRONMENT_LABELS, quest.environment if quest else "either")
        panel.add_widget(grid)

        self.duration = self._field(panel, "Duration (minutes)", ThemedInput(
            text=str(quest.duration if quest else 30), input_filter="int"))

        panel.add_widget(WrapLabel(text="Suitable weather (none selected = any weather)", bold=True,
                                   font_size=theme.FONT_SMALL))
        weather_grid = GridLayout(cols=4, spacing=dp(6), size_hint_y=None)
        weather_grid.bind(minimum_height=weather_grid.setter("height"))
        self.weather_toggles = []
        chosen = set(quest.weather) if quest else set()
        for condition in WEATHER_CONDITIONS:
            toggle = WeatherToggle(condition, state="down" if condition in chosen else "normal")
            self.weather_toggles.append(toggle)
            weather_grid.add_widget(toggle)
        panel.add_widget(weather_grid)

        self.tags = self._field(panel, "Tags (comma separated)", ThemedInput(
            text=", ".join(quest.tags) if quest else "", hint_text="e.g. walking, water, photography"))

        self.xp_label = WrapLabel(text="", color=theme.GOLD_DARK, bold=True)
        panel.add_widget(self.xp_label)
        self.difficulty.bind(text=self._update_xp)
        self.duration.bind(text=self._update_xp)
        self._update_xp()

        self.error = WrapLabel(text="", color=theme.EMBER_DARK, bold=True)
        panel.add_widget(self.error)

        save = QuestButton(text="SAVE QUEST", variant="primary", height=dp(48))
        save.bind(on_release=lambda *_: self.save())
        panel.add_widget(save)
        cancel = QuestButton(text="Cancel", variant="ghost")
        cancel.bind(on_release=lambda *_: self.app.go("library"))
        buttons = [cancel]
        if quest:
            delete = QuestButton(text="Delete", variant="ghost")
            delete.bind(on_release=lambda *_: self.confirm_delete())
            buttons.append(delete)
        panel.add_widget(button_row(buttons))

    def _category_changed(self, spinner, text):
        parent = spinner.parent
        if text == NEW_CATEGORY and self.new_category.parent is None:
            parent.add_widget(self.new_category, index=parent.children.index(spinner))
        elif text != NEW_CATEGORY and self.new_category.parent is not None:
            parent.remove_widget(self.new_category)

    def _update_xp(self, *_):
        try:
            duration = int(self.duration.text or 0)
        except ValueError:
            duration = 0
        xp = quest_xp(DIFFICULTY_CHOICES[self.difficulty.text], max(1, duration))
        self.xp_label.text = f"Reward: +{xp} XP"

    def collect(self) -> dict:
        category = self.category.text
        if category == NEW_CATEGORY:
            category = self.new_category.text.strip()
        weather = [t.condition for t in self.weather_toggles if t.state == "down"] or ["any"]
        return {
            "title": self.title_input.text.strip(),
            "description": self.description_input.text.strip(),
            "category": category,
            "difficulty": DIFFICULTY_CHOICES[self.difficulty.text],
            "cost": COST_CHOICES[self.cost.text],
            "accessibility": ACCESS_CHOICES[self.access.text],
            "duration": self.duration.text or "0",
            "environment": ENVIRONMENT_LABELS[self.environment.text],
            "weather": weather,
            "tags": self.tags.text,
        }

    def save(self) -> None:
        data = self.collect()
        if not data["title"] or not data["description"] or not data["category"]:
            self.error.text = "A quest needs a title, a description and a category."
            return
        try:
            self.game.save_custom_quest(data, quest_id=self.quest.id if self.quest else None)
        except QuestValidationError as exc:
            self.error.text = f"That doesn't look right: {exc}"
            return
        self.app.toast("Quest inscribed in the library!" if not self.quest else "Quest updated.")
        self.quest = None
        self.app.go("library")

    def confirm_delete(self) -> None:
        quest = self.quest

        def delete():
            self.game.delete_custom_quest(quest.id)
            self.quest = None
            self.app.toast("Quest struck from the library.")
            self.app.go("library")

        ConfirmDialog("Delete this quest?", f"“{quest.title}” will be removed.", "Delete", delete,
                      danger=True).open()
