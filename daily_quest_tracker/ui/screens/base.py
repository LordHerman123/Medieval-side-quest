from __future__ import annotations

from kivy.graphics import Color, Rectangle
from kivy.uix.screenmanager import Screen

from ui import theme
from ui.widgets.common import scrolling_column


class BaseScreen(Screen):
    """A screen with a dark background and a scrolling, centred content column."""

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        with self.canvas.before:
            Color(*theme.BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg, "pos", self.pos),
                  size=lambda *_: setattr(self._bg, "size", self.size))

    def make_scroll(self):
        self.scroll, self.column = scrolling_column()
        self.add_widget(self.scroll)
        return self.column

    @property
    def game(self):
        return self.app.game

    def on_enter(self, *args):
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the screen from the current game state."""
