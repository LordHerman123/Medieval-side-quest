"""Statistics: interesting facts about the journey, never a productivity scorecard."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.common import Panel, SectionHeader, WrapLabel
from ui.widgets.journey_path import StatBar


def stat_tile(value: str, caption: str) -> Panel:
    tile = Panel(bg_color=theme.BG_RAISED, border_color=theme.BORDER, spacing=dp(2), padding=(dp(8), dp(10)))
    tile.add_widget(WrapLabel(text=value, bold=True, color=theme.GOLD, font_size=theme.FONT_TITLE, halign="center"))
    tile.add_widget(WrapLabel(text=caption, color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center"))
    return tile


class StatisticsScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()

    def refresh(self) -> None:
        game = self.game
        stats = game.statistics()
        col = self.column
        col.clear_widgets()

        col.add_widget(SectionHeader("The Chronicle"))
        grid = GridLayout(cols=2 if col.width < dp(560) else 3, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        hours = stats.total_minutes / 60
        tiles = [
            (str(stats.total_completed), "quests completed"),
            (str(stats.total_xp), "experience gathered"),
            (f"{stats.level}", f"level · {stats.title}"),
            (f"{stats.categories_explored}/{stats.categories_total}", "kinds of adventure explored"),
            (str(stats.new_activities), "different activities tried"),
            (str(stats.wildcards_completed), "wildcards conquered"),
            (str(stats.days_adventured), "days with an adventure"),
            (f"{hours:.1f}", "hours spent adventuring"),
            (str(stats.epic_quests), "adventurous or epic deeds"),
            (str(stats.custom_quests), "quests of your own making"),
        ]
        for value, caption in tiles:
            grid.add_widget(stat_tile(value, caption))
        col.add_widget(grid)

        if stats.top_categories:
            col.add_widget(SectionHeader("Most Travelled Paths"))
            panel = Panel(spacing=dp(6))
            top = stats.top_categories[0][1]
            for name, count in stats.top_categories:
                row = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(8))
                row.add_widget(Label(text=name, color=theme.INK, bold=True, size_hint_x=0.38, halign="left",
                                     font_size=theme.FONT_SMALL, text_size=(None, None)))
                row.children[0].bind(size=lambda w, *_: setattr(w, "text_size", w.size))
                bar_holder = BoxLayout(padding=(0, dp(6)))
                bar_holder.add_widget(StatBar(value=count, maximum=top,
                                              bar_color=theme.hex_color(game.library.category(name).color)))
                row.add_widget(bar_holder)
                row.add_widget(Label(text=str(count), color=theme.INK_SOFT, size_hint_x=None, width=dp(30),
                                     font_size=theme.FONT_SMALL))
                panel.add_widget(row)
            col.add_widget(panel)

        if stats.top_tags:
            col.add_widget(SectionHeader("Favourite Themes"))
            col.add_widget(WrapLabel(text="  ·  ".join(t for t, _ in stats.top_tags), color=theme.TEXT,
                                     halign="center"))

        if stats.recent_discoveries:
            col.add_widget(SectionHeader("Recent Discoveries"))
            panel = Panel(spacing=dp(4))
            for d in stats.recent_discoveries:
                panel.add_widget(WrapLabel(text=f"First {d.category} quest", bold=True, font_size=theme.FONT_SMALL))
                panel.add_widget(WrapLabel(text=f"{d.title}  ·  {d.date}", color=theme.INK_SOFT,
                                           font_size=theme.FONT_SMALL))
            col.add_widget(panel)

        if stats.longest_quest:
            col.add_widget(SectionHeader("Longest Quest"))
            q = stats.longest_quest
            col.add_widget(WrapLabel(text=f"{q.title}\n{q.duration} minutes  ·  {q.date}", color=theme.TEXT,
                                     halign="center"))

        if stats.paths_for_another_day:
            col.add_widget(WrapLabel(
                text=f"{stats.paths_for_another_day} paths left for another day. Choosing is part of the adventure.",
                color=theme.TEXT_MUTED, font_size=theme.FONT_SMALL, halign="center", italic=True))

        if not stats.total_completed:
            col.add_widget(WrapLabel(text="The chronicle is still blank. Your first completed quest will start it.",
                                     color=theme.TEXT_MUTED, halign="center", italic=True))
