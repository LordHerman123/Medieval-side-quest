"""Parchment scrolls: quests are written on paper unrolled between two wooden rolls.

Everything is drawn with plain canvas primitives (Mesh, Ellipse, Rectangle,
RoundedRectangle, Line), which work identically on desktop OpenGL and
Android's OpenGL ES, so no image assets are needed.

``ScrollPanel`` is a drop-in replacement for :class:`~ui.widgets.common.Panel`:
children are laid out on the paper between the rolls. Setting ``reveal``
below 1 hides the lower part of the scroll behind the bottom roll, and
:meth:`ScrollPanel.unroll` animates it open.
"""

from __future__ import annotations

import math
import random
import zlib

from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty

from ui import theme
from ui.widgets.common import Panel

ROLL_LIGHT = theme.hex_color("#EFDDB5")
ROLL_MID = theme.hex_color("#D2B783")
ROLL_DARK = theme.hex_color("#9C7F4E")
ROLL_EDGE = theme.hex_color("#7A6038")
WOOD = theme.hex_color("#5A3D25")
WOOD_LIGHT = theme.hex_color("#7A5534")
STAIN = theme.hex_color("#A8864F")
SEAL = theme.hex_color("#A3261E")
SEAL_DARK = theme.hex_color("#7A1812")
SEAL_LIGHT = theme.hex_color("#C8453A")


def _fan(points):
    """A filled polygon (star-shaped around its first point) as a triangle-fan Mesh."""
    vertices = []
    for i in range(0, len(points), 2):
        vertices.extend([points[i], points[i + 1], 0, 0])
    return Mesh(vertices=vertices, indices=list(range(len(points) // 2)), mode="triangle_fan")


def draw_roll(x: float, cy: float, width: float, height: float, knob_color, knob: float) -> None:
    """A horizontal rolled-up end of the scroll with wooden knobs. Call inside a canvas context."""
    body_x = x + knob
    body_w = width - 2 * knob
    r = height / 2
    # Knobs (the ends of the wooden rod)
    Color(*knob_color)
    Ellipse(pos=(x, cy - r * 0.62), size=(knob * 1.8, r * 1.24))
    Ellipse(pos=(x + width - knob * 1.8, cy - r * 0.62), size=(knob * 1.8, r * 1.24))
    Color(1, 1, 1, 0.18)
    Ellipse(pos=(x + knob * 0.35, cy), size=(knob * 0.7, r * 0.45))
    Ellipse(pos=(x + width - knob * 1.35, cy), size=(knob * 0.7, r * 0.45))
    # Soft shadow under the roll
    Color(0, 0, 0, 0.22)
    RoundedRectangle(pos=(body_x, cy - r - dp(2.5)), size=(body_w, height), radius=[r])
    # Cylinder body: base colour, then a dark underside and a light highlight band
    Color(*ROLL_MID)
    RoundedRectangle(pos=(body_x, cy - r), size=(body_w, height), radius=[r])
    Color(*ROLL_DARK)
    RoundedRectangle(pos=(body_x + r * 0.3, cy - r), size=(body_w - r * 0.6, height * 0.3), radius=[r * 0.3])
    Color(*ROLL_LIGHT)
    RoundedRectangle(pos=(body_x + r * 0.6, cy + r * 0.12), size=(body_w - r * 1.2, height * 0.2),
                     radius=[r * 0.2])
    # The curled paper visible at each end: a spiral of rings
    for ex in (body_x + r * 0.55, body_x + body_w - r * 0.55):
        Color(*ROLL_EDGE)
        Ellipse(pos=(ex - r * 0.5, cy - r), size=(r, height))
        Color(*ROLL_MID)
        Ellipse(pos=(ex - r * 0.36, cy - r * 0.72), size=(r * 0.72, r * 1.44))
        Color(*ROLL_EDGE)
        Line(ellipse=(ex - r * 0.22, cy - r * 0.44, r * 0.44, r * 0.88), width=dp(0.8))
        Ellipse(pos=(ex - r * 0.08, cy - r * 0.16), size=(r * 0.16, r * 0.32))


def draw_seal(cx: float, cy: float, radius: float) -> None:
    """A red wax seal with a stamped flame."""
    points = [cx, cy]
    for i in range(25):
        a = 2 * math.pi * i / 24
        rr = radius * (1.0 if i % 2 == 0 else 0.86)
        points.extend([cx + math.cos(a) * rr, cy + math.sin(a) * rr])
    Color(0, 0, 0, 0.3)
    Ellipse(pos=(cx - radius + dp(1.5), cy - radius - dp(2)), size=(radius * 2, radius * 2))
    Color(*SEAL)
    _fan(points)
    Color(*SEAL_DARK)
    Line(circle=(cx, cy, radius * 0.66), width=dp(1.1))
    Color(*SEAL_LIGHT)
    h = radius * 0.9
    _fan([cx, cy - h * 0.25,
          cx - h * 0.3, cy - h * 0.35, cx - h * 0.28, cy, cx - h * 0.08, cy + h * 0.2,
          cx, cy + h * 0.45, cx + h * 0.1, cy + h * 0.15, cx + h * 0.28, cy + h * 0.02,
          cx + h * 0.3, cy - h * 0.35])
    Color(1, 1, 1, 0.2)
    Ellipse(pos=(cx - radius * 0.55, cy + radius * 0.2), size=(radius * 0.4, radius * 0.3))


class ScrollPanel(Panel):
    """A vertical parchment scroll with rolls at the top and bottom."""

    roll_height = NumericProperty(dp(20))
    knob_color = ListProperty(WOOD)
    sealed = BooleanProperty(False)
    reveal = NumericProperty(1.0)
    cover_color = ListProperty(theme.BG)
    seed = StringProperty("")

    def __init__(self, **kwargs):
        roll = kwargs.get("roll_height", dp(20))
        side = dp(24)
        kwargs.setdefault("padding", (side, roll + dp(10), side, roll + dp(12)))
        super().__init__(**kwargs)
        self.bind(reveal=self._draw, sealed=self._draw, roll_height=self._draw, knob_color=self._draw)

    @property
    def _inset(self) -> float:
        return dp(11)

    def _draw(self, *_):
        if not hasattr(self, "roll_height"):
            return  # Panel.__init__ draws before our properties are ready
        self.canvas.before.clear()
        self.canvas.after.clear()
        R = self.roll_height
        knob = dp(7)
        inset = self._inset
        # Use x/y/width/height directly: the top/right/center aliases still hold the previous
        # geometry while a size event is being dispatched.
        top = self.y + self.height
        top_cy = top - R / 2
        full_bottom_cy = self.y + R / 2
        bottom_cy = top_cy - (top_cy - full_bottom_cy) * max(0.0, min(1.0, self.reveal))
        paper_top = top_cy
        paper_bottom = full_bottom_cy
        left, right = self.x + inset, self.x + self.width - inset
        rng = random.Random(zlib.crc32((self.seed or "scroll").encode("utf-8")))
        phase = rng.random() * 6

        with self.canvas.before:
            # Paper with gently wavy side edges
            step = dp(14)
            steps = max(2, int((paper_top - paper_bottom) / step))
            left_edge, right_edge = [], []
            for i in range(steps + 1):
                y = paper_top - (paper_top - paper_bottom) * i / steps
                left_edge.append((left + math.sin(y / dp(23) + phase) * dp(1.6), y))
                right_edge.append((right + math.sin(y / dp(19) + phase * 1.7) * dp(1.6), y))
            outline = left_edge + list(reversed(right_edge))
            Color(0, 0, 0, 0.3)
            RoundedRectangle(pos=(left + dp(2), paper_bottom - dp(3)), size=(right - left, paper_top - paper_bottom),
                             radius=[dp(3)])
            Color(*self.bg_color)
            fan = [(left + right) / 2, (paper_top + paper_bottom) / 2]
            for px, py in outline + outline[:1]:
                fan.extend([px, py])
            _fan(fan)
            # Aged edges
            Color(*ROLL_EDGE[:3], 0.35)
            Line(points=[c for p in left_edge for c in p], width=dp(1.2))
            Line(points=[c for p in right_edge for c in p], width=dp(1.2))
            Color(*STAIN[:3], 0.09)
            Line(points=[c for p in left_edge for c in (p[0] + dp(4), p[1])], width=dp(3))
            Line(points=[c for p in right_edge for c in (p[0] - dp(4), p[1])], width=dp(3))
            # A few faint stains
            for _ in range(3):
                sw = dp(rng.uniform(30, 70))
                sh = sw * rng.uniform(0.5, 0.9)
                sx = rng.uniform(left + dp(10), max(left + dp(11), right - sw - dp(10)))
                sy = rng.uniform(paper_bottom + dp(10), max(paper_bottom + dp(11), paper_top - sh - dp(10)))
                Color(*STAIN[:3], rng.uniform(0.04, 0.08))
                Ellipse(pos=(sx, sy), size=(sw, sh))
            # Shading where the paper curls towards the rolls
            for i in range(6):
                a = 0.16 * (1 - i / 6)
                Color(0.35, 0.25, 0.1, a)
                Rectangle(pos=(left, paper_top - R / 2 - dp(3) * (i + 1)), size=(right - left, dp(3)))
                Rectangle(pos=(left, paper_bottom + R / 2 + dp(3) * i), size=(right - left, dp(3)))
            # Top roll
            draw_roll(self.x, top_cy, self.width, R, self.knob_color, knob)

        with self.canvas.after:
            if self.reveal < 1.0:
                # Hide the still-rolled part of the scroll (and its content).
                Color(*self.cover_color)
                Rectangle(pos=(self.x - dp(2), self.y - dp(6)), size=(self.width + dp(4), bottom_cy - self.y + dp(6)))
            draw_roll(self.x, bottom_cy, self.width, R, self.knob_color, knob)
            if self.sealed and self.reveal > 0.35:
                draw_seal(self.x + self.width - dp(40), top - R - dp(10), dp(15))

    def unroll(self, duration: float = 0.6, delay: float = 0.0) -> None:
        """Animate the scroll opening from its top roll downwards."""
        Animation.cancel_all(self, "reveal")
        self.reveal = 0.0
        anim = Animation(reveal=1.0, duration=duration, t="out_cubic")
        if delay:
            anim = Animation(duration=delay) + anim
        anim.start(self)
