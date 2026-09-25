"""Quest cards for the Today board: a prominent priority card and compact side-quest cards."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from kivy.graphics import Color, Mesh, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from core.models import (
    PICK_MANUAL,
    PICK_NOVEL,
    PICK_WILDCARD,
    STATUS_ABANDONED,
    STATUS_ACCEPTED,
    STATUS_COMPLETED,
    STATUS_OFFERED,
    STATUS_SKIPPED,
    DailyQuest,
    Quest,
)
from ui import theme
from ui.widgets.common import Chip, Panel, QuestButton, WrapLabel, button_row, format_duration

PICK_HINTS = {
    PICK_NOVEL: "A new path",
    PICK_WILDCARD: "Wildcard",
    PICK_MANUAL: "Your choice",
}

STATUS_TEXT = {
    STATUS_COMPLETED: "Quest complete",
    STATUS_SKIPPED: "Left for another day",
    STATUS_ABANDONED: "Set aside",
}


def quest_meta_line(quest: Quest) -> str:
    return f"{quest.category}  ·  {quest.difficulty_label}  ·  {quest.cost_label}"


def quest_detail_line(quest: Quest) -> str:
    return f"{format_duration(quest.duration)}  ·  {quest.environment.capitalize()}  ·  {quest.accessibility_label}"


class FlameIcon(Widget):
    """A tiny drawn flame used on the priority banner (no emoji font needed)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(16), dp(20)))
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw)

    def _flame(self, color, scale):
        w, h = self.width * scale, self.height * scale
        cx, by = self.center_x, self.y + (self.height - h) * 0.15
        pts = [cx, by + h * 0.3, cx - w / 2, by + h * 0.25, cx - w * 0.3, by + h * 0.65, cx, by + h,
               cx + w * 0.15, by + h * 0.6, cx + w * 0.5, by + h * 0.3, cx + w * 0.3, by]
        pts = pts + [cx - w * 0.3, by]
        verts = []
        for i in range(0, len(pts), 2):
            verts += [pts[i], pts[i + 1], 0, 0]
        self.canvas.add(Color(*color))
        self.canvas.add(Mesh(vertices=verts, indices=list(range(len(pts) // 2)), mode="triangle_fan"))

    def _draw(self, *_):
        self.canvas.clear()
        self._flame(theme.hex_color("#FFB347"), 1.0)
        self._flame(theme.hex_color("#FFE08A"), 0.55)


class PriorityBanner(BoxLayout):
    def __init__(self, text: str, **kwargs):
        super().__init__(size_hint_y=None, height=dp(34), padding=(dp(10), dp(6)), spacing=dp(8), **kwargs)
        self.add_widget(FlameIcon())
        self.add_widget(Label(text=text, bold=True, color=theme.TEXT, font_size=theme.FONT_SIZE,
                              halign="left", valign="middle", text_size=(None, None)))
        self.children[0].bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.EMBER_DARK)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(7)])


class QuestCard(Panel):
    """Displays one daily quest and the actions available for its status.

    ``actions`` maps action names (accept, complete, skip, replace, abandon,
    details) to callbacks taking the quest id.
    """

    def __init__(self, entry: DailyQuest, actions: Dict[str, Callable[[str], None]],
                 category_color=None, priority: bool = False, **kwargs):
        kwargs.setdefault("spacing", dp(7))
        super().__init__(**kwargs)
        self.entry = entry
        self.actions = actions
        quest = entry.quest
        done = not entry.is_open
        if priority:
            self.double_border = True
            self.border_color = theme.GOLD_DARK
            self.border_width = dp(2)
            self.add_widget(PriorityBanner("TODAY'S PRIORITY QUEST"))
        if done:
            self.bg_color = theme.PARCHMENT_DARK

        header = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
        header.add_widget(Chip(text=quest.category, chip_color=category_color or theme.LEATHER))
        hint = PICK_HINTS.get(entry.pick_type)
        if hint:
            header.add_widget(Chip(text=hint, chip_color=theme.hex_color("#3A3026")))
        header.add_widget(Widget())
        header.add_widget(Label(text=f"+{quest.xp} XP", bold=True, color=theme.GOLD_DARK,
                                font_size=theme.FONT_SIZE, size_hint_x=None, width=dp(70), halign="right",
                                text_size=(dp(70), None)))
        self.add_widget(header)

        self.add_widget(WrapLabel(text=quest.title, bold=True,
                                  font_size=theme.FONT_TITLE if priority else theme.FONT_LARGE))
        if priority or not done:
            self.add_widget(WrapLabel(text=quest.description, color=theme.INK_SOFT))
        self.add_widget(WrapLabel(text=quest_meta_line(quest), font_size=theme.FONT_SMALL, bold=True))
        self.add_widget(WrapLabel(text=quest_detail_line(quest), font_size=theme.FONT_SMALL, color=theme.INK_SOFT))

        buttons = self._buttons(priority)
        if buttons:
            self.add_widget(buttons)

    def _act(self, name: str) -> Callable[[], None]:
        def run(*_):
            callback = self.actions.get(name)
            if callback:
                callback(self.entry.quest_id)
        return run

    def _button(self, text: str, action: str, variant: str, **kwargs) -> QuestButton:
        button = QuestButton(text=text, variant=variant, **kwargs)
        button.bind(on_release=self._act(action))
        return button

    def _buttons(self, priority: bool) -> Optional[Widget]:
        status = self.entry.status
        tall = dp(50) if priority else dp(42)
        if status == STATUS_OFFERED:
            main = self._button("ACCEPT QUEST", "accept", "primary", height=tall)
            others = button_row([self._button("Another quest", "replace", "ghost", font_size=theme.FONT_SMALL),
                                 self._button("Not today", "skip", "ghost", font_size=theme.FONT_SMALL)],
                                height=dp(38))
            box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), height=tall + dp(38) + dp(6))
            box.add_widget(main)
            box.add_widget(others)
            return box
        if status == STATUS_ACCEPTED:
            main = self._button("COMPLETE QUEST", "complete", "moss", height=tall)
            aside = self._button("Set aside", "abandon", "ghost", font_size=theme.FONT_SMALL, height=dp(38))
            box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), height=tall + dp(38) + dp(6))
            box.add_widget(main)
            box.add_widget(aside)
            return box
        text = STATUS_TEXT.get(status, status.capitalize())
        return WrapLabel(text=text, italic=True, bold=status == STATUS_COMPLETED,
                         color=theme.MOSS if status == STATUS_COMPLETED else theme.INK_SOFT, halign="center")
