"""Modal dialogs: quest rewards, confirmations and quest details."""

from __future__ import annotations

from typing import Callable, List, Optional

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView

from core.game import CompletionResult
from core.models import Quest
from ui import theme
from ui.widgets.common import Chip, Panel, QuestButton, WrapLabel, button_row, spacer
from ui.widgets.quest_card import quest_detail_line, quest_meta_line


class Dialog(ModalView):
    """A parchment dialog that sizes to its content and scrolls if it gets too tall."""

    def __init__(self, **kwargs):
        kwargs.setdefault("auto_dismiss", True)
        super().__init__(size_hint=(None, None), background="", background_color=(0, 0, 0, 0),
                         overlay_color=(0, 0, 0, 0.65), **kwargs)
        self.panel = Panel(double_border=True, border_color=theme.GOLD_DARK, spacing=dp(8),
                           padding=(dp(18), dp(16)))
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.scroll.add_widget(self.panel)
        self.add_widget(self.scroll)
        self.panel.bind(height=self._resize)
        Window.bind(size=self._resize)
        self.bind(on_dismiss=lambda *_: Window.unbind(size=self._resize))
        self._resize()

    def _resize(self, *_):
        self.width = min(Window.width * 0.94, dp(520))
        self.height = min(self.panel.height, Window.height * 0.88)

    def add(self, widget):
        self.panel.add_widget(widget)
        return widget


class RewardDialog(Dialog):
    def __init__(self, result: CompletionResult, title_for_level: Callable[[int], str], **kwargs):
        super().__init__(**kwargs)
        award = result.award
        self.add(WrapLabel(text="QUEST COMPLETE", bold=True, color=theme.GOLD_DARK, halign="center",
                           font_size=theme.FONT_LARGE))
        self.add(WrapLabel(text=result.quest.title, halign="center", italic=True))
        self.add(WrapLabel(text=f"+{award.total} XP", bold=True, halign="center", font_size=theme.FONT_TITLE * 1.3,
                           color=theme.EMBER_DARK))
        if award.wildcard_bonus:
            self.add(WrapLabel(text=f"Includes +{award.wildcard_bonus} for braving a wildcard", halign="center",
                               font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        if award.discovery_bonus:
            self.add(WrapLabel(text=f"Includes +{award.discovery_bonus} for your first {result.quest.category} quest",
                               halign="center", font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        if result.leveled_up:
            self.add(spacer(dp(6)))
            self.add(WrapLabel(text=f"LEVEL {result.new_level}", bold=True, halign="center",
                               font_size=theme.FONT_TITLE, color=theme.GOLD_DARK))
            new_title = title_for_level(result.new_level)
            if new_title != title_for_level(result.old_level):
                self.add(WrapLabel(text=f"You are now known as {new_title}.", halign="center"))
            else:
                self.add(WrapLabel(text="Your legend grows.", halign="center"))
            if result.new_items:
                self.add(WrapLabel(text="New at your camp:", bold=True, halign="center", font_size=theme.FONT_SMALL))
                for item in result.new_items:
                    self.add(WrapLabel(text=f"{item.name} — {item.description}", halign="center",
                                       font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        self.add(spacer(dp(4)))
        button = QuestButton(text="Onward!", variant="gold")
        button.bind(on_release=lambda *_: self.dismiss())
        self.add(button)


class ConfirmDialog(Dialog):
    def __init__(self, title: str, message: str, confirm_text: str, on_confirm: Callable[[], None],
                 danger: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.add(WrapLabel(text=title, bold=True, font_size=theme.FONT_LARGE))
        self.add(WrapLabel(text=message, color=theme.INK_SOFT))
        cancel = QuestButton(text="Cancel", variant="ghost")
        cancel.bind(on_release=lambda *_: self.dismiss())
        ok = QuestButton(text=confirm_text, variant="primary" if danger else "moss")

        def confirm(*_):
            self.dismiss()
            on_confirm()

        ok.bind(on_release=confirm)
        self.add(button_row([cancel, ok]))


class QuestDetailDialog(Dialog):
    def __init__(self, quest: Quest, category_color, on_take: Optional[Callable[[Quest], None]] = None,
                 on_edit: Optional[Callable[[Quest], None]] = None,
                 on_delete: Optional[Callable[[Quest], None]] = None, **kwargs):
        super().__init__(**kwargs)
        chips = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
        chips.add_widget(Chip(text=quest.category, chip_color=category_color))
        if quest.custom:
            chips.add_widget(Chip(text="Your quest", chip_color=theme.hex_color("#3A3026")))
        chips.add_widget(BoxLayout())
        self.add(chips)
        self.add(WrapLabel(text=quest.title, bold=True, font_size=theme.FONT_TITLE))
        self.add(WrapLabel(text=quest.description, color=theme.INK_SOFT))
        self.add(WrapLabel(text=quest_meta_line(quest), bold=True, font_size=theme.FONT_SMALL))
        self.add(WrapLabel(text=quest_detail_line(quest), font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        weather = "Any weather" if "any" in quest.weather else "Best in: " + ", ".join(quest.weather)
        self.add(WrapLabel(text=weather, font_size=theme.FONT_SMALL, color=theme.INK_SOFT))
        if quest.tags:
            self.add(WrapLabel(text="Themes: " + ", ".join(quest.tags), font_size=theme.FONT_SMALL,
                               color=theme.INK_SOFT))
        self.add(WrapLabel(text=f"Reward: +{quest.xp} XP", bold=True, color=theme.GOLD_DARK))
        self.add(spacer(dp(4)))

        def wrap(callback):
            def run(*_):
                self.dismiss()
                callback(quest)
            return run

        buttons: List[QuestButton] = []
        if on_take:
            take = QuestButton(text="TAKE ON THIS QUEST", variant="primary", height=dp(48))
            take.bind(on_release=wrap(on_take))
            self.add(take)
        if on_edit:
            edit = QuestButton(text="Edit", variant="leather")
            edit.bind(on_release=wrap(on_edit))
            buttons.append(edit)
        if on_delete:
            delete = QuestButton(text="Delete", variant="ghost")
            delete.bind(on_release=wrap(on_delete))
            buttons.append(delete)
        close = QuestButton(text="Close", variant="ghost")
        close.bind(on_release=lambda *_: self.dismiss())
        buttons.append(close)
        self.add(button_row(buttons))
