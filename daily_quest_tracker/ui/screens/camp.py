"""Character & Camp: the full scene, the traveler's title and everything unlocked so far."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from ui import theme
from ui.screens.base import BaseScreen
from ui.widgets.camp_scene import CampScene, loadout_ids
from ui.widgets.common import Chip, Panel, XpBar, SectionHeader, WrapLabel

KIND_LABELS = {
    "camp": "Camp", "clothing": "Clothing", "equipment": "Gear", "weapon": "Weapon", "armour": "Armour",
    "shield": "Shield", "animal": "Animal", "npc": "Visitor", "companion": "Companion",
    "structure": "Structure", "decoration": "Decoration",
}


class CampScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.make_scroll()
        self.scene = CampScene(size_hint_y=None, height=dp(260))
        self.column.bind(width=self._size_scene)

    def _size_scene(self, *_):
        self.scene.height = max(dp(200), min(dp(420), self.column.width * 0.6))

    def on_enter(self, *args):
        self.refresh()
        self.scene.start()

    def on_leave(self, *args):
        self.scene.stop()

    def refresh(self) -> None:
        game = self.game
        col = self.column
        col.clear_widgets()
        info = game.level_info()
        self.scene.configure(loadout_ids(game.loadout()), info.level, game.weather, now=game.now())
        col.add_widget(self.scene)

        card = Panel()
        card.add_widget(WrapLabel(text=game.title(), bold=True, font_size=theme.FONT_TITLE, halign="center"))
        card.add_widget(WrapLabel(text=f"Level {info.level}  ·  {info.xp} XP gathered", halign="center",
                                  color=theme.INK_SOFT))
        bar = XpBar(value=info.progress, track_color=theme.hex_color("#000000", 0.15))
        card.add_widget(bar)
        card.add_widget(WrapLabel(text=f"{info.next_level_xp - info.xp} XP until level {info.level + 1}",
                                  halign="center", font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        col.add_widget(card)

        col.add_widget(SectionHeader("Equipment & Camp"))
        loadout = {item.id for item in game.loadout().values()}
        for item in reversed(game.progression.unlocked_items(info.level)):
            retired = item.id not in loadout
            row = Panel(bg_color=theme.PARCHMENT_DARK if retired else theme.PARCHMENT, spacing=dp(3),
                        padding=(dp(12), dp(8)))
            head = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
            head.add_widget(Chip(text=KIND_LABELS.get(item.kind, item.kind.capitalize())))
            head.add_widget(Label(text=item.name + ("  (retired)" if retired else ""), bold=True, color=theme.INK,
                                  halign="left", valign="middle", font_size=theme.FONT_SIZE,
                                  text_size=(None, None)))
            head.children[0].bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            head.add_widget(Label(text=f"Lv {item.level}", color=theme.INK_SOFT, size_hint_x=None, width=dp(44),
                                  font_size=theme.FONT_SMALL))
            row.add_widget(head)
            row.add_widget(WrapLabel(text=item.description, color=theme.INK_SOFT, font_size=theme.FONT_SMALL))
            col.add_widget(row)

        upcoming = game.progression.next_unlocks(info.level, 4)
        if upcoming:
            col.add_widget(SectionHeader("On the Road Ahead"))
            for item in upcoming:
                col.add_widget(WrapLabel(text=f"Level {item.level}:  {item.name}", color=theme.TEXT_MUTED,
                                         halign="center"))
        else:
            col.add_widget(WrapLabel(text="Every treasure of the road is yours. The adventure continues.",
                                     color=theme.GOLD, halign="center", italic=True))
