"""Journey: a visual trail and the chronicle of completed quests."""

from __future__ import annotations

from datetime import date

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from core.models import DIFFICULTY_LABELS, PICK_NOVEL, PICK_WILDCARD
from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.common import Chip, EmptyState, SectionHeader, WrapLabel
from ui.widgets.scroll import ScrollPanel
from ui.widgets.journey_path import JourneyPath

TRAIL_LENGTH = 25
HISTORY_LIMIT = 300


def nice_date(iso: str) -> str:
    try:
        return f"{date.fromisoformat(iso):%A %d %B %Y}"
    except ValueError:
        return iso


class JourneyScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()

    def refresh(self) -> None:
        game = self.game
        col = self.column
        col.clear_widgets()
        history = game.journey(HISTORY_LIMIT)

        col.add_widget(SectionHeader("Your Trail"))
        recent = list(reversed(history[:TRAIL_LENGTH]))
        col.add_widget(JourneyPath(stops=[theme.hex_color(game.library.category(c.category).color) for c in recent]))
        if not history:
            col.add_widget(EmptyState("Your journey begins with a single quest. Complete one and it will be "
                                      "chronicled here."))
            return
        col.add_widget(WrapLabel(text=f"{len(history)} quests chronicled. Every fifth step is a milestone.",
                                 color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center"))

        current_date = None
        for completion in history:
            if completion.date != current_date:
                current_date = completion.date
                col.add_widget(SectionHeader(nice_date(current_date)))
            card = ScrollPanel(spacing=dp(4), roll_height=dp(14), seed=f"{completion.id}",
                               padding=(dp(24), dp(22), dp(24), dp(24)))
            head = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
            head.add_widget(Chip(text=completion.category,
                                 chip_color=theme.hex_color(game.library.category(completion.category).color)))
            if completion.pick_type == PICK_WILDCARD:
                head.add_widget(Chip(text="Wildcard", chip_color=theme.hex_color("#3A3026")))
            elif completion.pick_type == PICK_NOVEL:
                head.add_widget(Chip(text="New path", chip_color=theme.hex_color("#3A3026")))
            head.add_widget(BoxLayout())
            head.add_widget(Label(text=f"+{completion.xp} XP", bold=True, color=theme.GOLD_DARK, size_hint_x=None,
                                  width=dp(70), font_size=theme.FONT_SMALL))
            card.add_widget(head)
            card.add_widget(WrapLabel(text=completion.title, bold=True))
            card.add_widget(WrapLabel(
                text=f"{DIFFICULTY_LABELS.get(completion.difficulty, '')}  ·  {completion.duration} min",
                color=theme.INK_SOFT, font_size=theme.FONT_SMALL))
            col.add_widget(card)
