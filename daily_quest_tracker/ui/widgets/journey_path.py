"""Small visualisations: the winding journey trail and horizontal stat bars."""

from __future__ import annotations

import math
from typing import List, Tuple

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.widget import Widget

from ui import theme


class JourneyPath(Widget):
    """A winding trail with one marker per completed quest (oldest on the left).

    ``stops`` is a list of RGBA colours (one per quest, usually the category colour).
    Every fifth stop is drawn as a larger milestone.
    """

    stops = ListProperty([])

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(110))
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw, stops=self._draw)

    def _point(self, f: float) -> Tuple[float, float]:
        margin = dp(22)
        x = self.x + margin + f * (self.width - 2 * margin)
        y = self.center_y + math.sin(f * math.pi * 3) * self.height * 0.28
        return x, y

    def _draw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*theme.BG_RAISED)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[theme.RADIUS])
            points: List[float] = []
            for i in range(61):
                points.extend(self._point(i / 60))
            Color(*theme.hex_color("#8A7550"))
            Line(points=points, width=dp(3.2), cap="round", joint="round")
            Color(*theme.hex_color("#6B5536"))
            Line(points=points, width=dp(1), dash_length=dp(4), dash_offset=dp(4))

            count = len(self.stops)
            if count == 0:
                return
            for index, color in enumerate(self.stops):
                f = (index + 1) / (count + 1) if count > 1 else 0.5
                x, y = self._point(f)
                milestone = (index + 1) % 5 == 0
                r = dp(7) if milestone else dp(5)
                Color(*theme.BG)
                Ellipse(pos=(x - r - dp(1.5), y - r - dp(1.5)), size=(2 * r + dp(3), 2 * r + dp(3)))
                Color(*color)
                Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
                if milestone:
                    Color(*theme.GOLD)
                    Line(circle=(x, y, r + dp(2)), width=dp(1.2))
            # The traveler's current position: a little flag at the newest stop.
            x, y = self._point(count / (count + 1) if count > 1 else 0.5)
            Color(*theme.hex_color("#4A3322"))
            Line(points=[x, y + dp(6), x, y + dp(24)], width=dp(1.2))
            Color(*theme.EMBER)
            Line(points=[x, y + dp(24), x + dp(10), y + dp(20), x, y + dp(16)], width=dp(1.2), close=True)


class StatBar(Widget):
    """A horizontal bar representing ``value`` out of ``maximum``."""

    value = NumericProperty(0)
    maximum = NumericProperty(1)
    bar_color = ListProperty(theme.GOLD)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(10))
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw, value=self._draw, maximum=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0, 0, 0, 0.3)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])
            if self.maximum and self.value:
                Color(*self.bar_color)
                width = max(self.height, self.width * self.value / self.maximum)
                RoundedRectangle(pos=self.pos, size=(width, self.height), radius=[self.height / 2])
