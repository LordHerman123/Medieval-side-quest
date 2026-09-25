"""The campfire scene, drawn procedurally with Kivy canvas instructions.

The scene is described in a virtual 200 x 100 coordinate space (ground line at
y=38) and scaled to the widget. What appears depends on the unlocked
progression items (``loadout``: slot -> item id), the time of day and the
weather, so the camp visibly grows as the traveler levels up.
"""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Dict, Iterable, Optional, Sequence, Tuple

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Mesh, Rectangle
from kivy.properties import DictProperty, NumericProperty, StringProperty
from kivy.uix.stencilview import StencilView

from ui.theme import hex_color

VW, VH = 200.0, 100.0
HORIZON = 38.0
FIRE_X, FIRE_Y = 104.0, 9.0

SKIES = {
    "day": ("#5B8FC7", "#C4DCEA"),
    "dawn": ("#4A5C8C", "#F2B880"),
    "dusk": ("#393D70", "#E8875A"),
    "night": ("#0A1130", "#28324F"),
}
LIGHT = {"day": 1.0, "dawn": 0.8, "dusk": 0.72, "night": 0.5}

BODY_COLORS = {
    "tunic_simple": ("#8B6A43", "#6F5233"),
    "leather_jerkin": ("#6E4B2A", "#4A301A"),
    "chainmail": ("#9DA3A9", "#6F757B"),
    "plate_armour": ("#CBD1D6", "#8F979E"),
}


def time_phase(hour: float, sunrise: float = 6.5, sunset: float = 19.5) -> str:
    if abs(hour - sunrise) <= 0.75:
        return "dawn"
    if abs(hour - sunset) <= 0.75:
        return "dusk"
    if sunrise < hour < sunset:
        return "day"
    return "night"


def _parse_hour(value: Optional[str], default: float) -> float:
    if not value:
        return default
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.hour + parsed.minute / 60
    except ValueError:
        return default


class CampScene(StencilView):
    """Clipped to its bounds so scenery never spills over neighbouring widgets."""

    hour = NumericProperty(12.0)
    weather = StringProperty("")  # clear/cloudy/rain/snow/storm/fog/wind or ""
    level = NumericProperty(1)
    loadout = DictProperty({})
    sunrise = NumericProperty(6.5)
    sunset = NumericProperty(19.5)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._static = InstructionGroup()
        self._animated = InstructionGroup()
        self.canvas.add(self._static)
        self.canvas.add(self._animated)
        self._t = 0.0
        self._event = None
        self._precip = []
        self.bind(pos=self.redraw, size=self.redraw, hour=self.redraw, weather=self.redraw, loadout=self.redraw)

    # --- public API -------------------------------------------------------------
    def configure(self, loadout: Dict[str, str], level: int, weather=None, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        if weather is not None:
            self.sunrise = _parse_hour(weather.sunrise, 6.5)
            self.sunset = _parse_hour(weather.sunset, 19.5)
            self.weather = weather.condition
        else:
            self.weather = ""
        self.level = level
        self.hour = now.hour + now.minute / 60
        self.loadout = dict(loadout)

    def start(self) -> None:
        if self._event is None:
            self._event = Clock.schedule_interval(self._tick, 1 / 12)

    def stop(self) -> None:
        if self._event is not None:
            self._event.cancel()
            self._event = None

    @property
    def phase(self) -> str:
        return time_phase(self.hour, self.sunrise, self.sunset)

    # --- coordinate helpers ---------------------------------------------------------
    def _geometry(self) -> Tuple[float, float, float]:
        # Slightly crop the scene edges so the camp stays large on narrow screens.
        s = min(self.width / 185.0, self.height / 85.0) if self.width and self.height else 1.0
        ox = self.center_x - (VW / 2) * s
        oy = self.y
        return s, ox, oy

    def P(self, x: float, y: float) -> Tuple[float, float]:
        return self._ox + x * self._s, self._oy + y * self._s

    def pts(self, coords: Sequence[float]) -> list:
        out = []
        for i in range(0, len(coords), 2):
            out.extend(self.P(coords[i], coords[i + 1]))
        return out

    def shade(self, color: str, alpha: float = 1.0, light: Optional[float] = None) -> Color:
        r, g, b, _ = hex_color(color)
        k = LIGHT[self.phase] if light is None else light
        if self.weather in ("rain", "storm", "fog") and light is None:
            k *= 0.85
        return Color(r * k, g * k, b * k, alpha)

    # --- primitive drawing ---------------------------------------------------------
    def rect(self, g, color, x, y, w, h, alpha=1.0, light=None):
        g.add(self.shade(color, alpha, light))
        g.add(Rectangle(pos=self.P(x, y), size=(w * self._s, h * self._s)))

    def oval(self, g, color, cx, cy, rx, ry, alpha=1.0, light=None):
        g.add(self.shade(color, alpha, light))
        g.add(Ellipse(pos=self.P(cx - rx, cy - ry), size=(2 * rx * self._s, 2 * ry * self._s)))

    def poly(self, g, color, coords, alpha=1.0, light=None):
        g.add(self.shade(color, alpha, light))
        points = self.pts(coords)
        vertices = []
        for i in range(0, len(points), 2):
            vertices.extend([points[i], points[i + 1], 0, 0])
        g.add(Mesh(vertices=vertices, indices=list(range(len(points) // 2)), mode="triangle_fan"))

    def line(self, g, color, coords, width=1.0, alpha=1.0, light=None):
        g.add(self.shade(color, alpha, light))
        g.add(Line(points=self.pts(coords), width=max(1.0, width * self._s), cap="round", joint="round"))

    # --- scene ----------------------------------------------------------------------
    def redraw(self, *_):
        self._s, self._ox, self._oy = self._geometry()
        g = self._static
        g.clear()
        has = self.loadout.get
        self._draw_sky(g)
        self._draw_landscape(g)
        if has("keep"):
            self._draw_keep(g)
        self._draw_ground(g)
        if has("palisade"):
            self._draw_palisade(g)
        if has("tower"):
            self._draw_watchtower(g)
        shelter = has("shelter")
        if shelter:
            {"lean_to": self._draw_lean_to, "tent": self._draw_tent, "pavilion": self._draw_pavilion}.get(
                shelter, self._draw_tent)(g)
        if has("banner"):
            self._draw_banner(g)
        if has("merchant"):
            self._draw_merchant(g)
        if has("mount"):
            self._draw_horse(g)
        if has("lantern"):
            self._draw_lantern_post(g)
        self._draw_fire_base(g)
        if has("seat"):
            self._draw_log(g)
        self._draw_gear(g)
        self._draw_traveler(g)
        if has("companion"):
            self._draw_dog(g)
        if has("bard"):
            self._draw_bard(g)
        if has("squire"):
            self._draw_squire(g)
        if has("falcon"):
            self._draw_falcon(g)
        self._seed_precipitation()
        self._draw_animated()

    def _tick(self, dt):
        self._t += dt
        self._draw_animated()

    # sky & land --------------------------------------------------------------------
    def _draw_sky(self, g):
        top, bottom = SKIES[self.phase]
        if self.weather in ("rain", "storm"):
            top, bottom = ("#3D4450", "#7A8490") if self.phase == "day" else ("#161A22", "#2E3440")
        elif self.weather in ("cloudy", "fog", "snow") and self.phase == "day":
            top, bottom = "#7D90A6", "#C9D1D8"
        tr, tg, tb, _ = hex_color(top)
        br, bg_, bb, _ = hex_color(bottom)
        bands = 32
        horizon_px = self.P(0, HORIZON)[1]
        span = max(1.0, self.top - horizon_px)
        for i in range(bands):
            f = i / (bands - 1)
            g.add(Color(br + (tr - br) * f, bg_ + (tg - bg_) * f, bb + (tb - bb) * f, 1))
            y0 = horizon_px + span * i / bands
            g.add(Rectangle(pos=(self.x, y0), size=(self.width, span / bands + 1)))

        rng = random.Random(7)
        if self.phase == "night" and self.weather not in ("rain", "storm", "fog", "cloudy", "snow"):
            for _ in range(70):
                sx = self.x + rng.random() * self.width
                sy = horizon_px + (0.15 + 0.85 * rng.random()) * span
                size = rng.choice((1.2, 1.6, 2.2))
                g.add(Color(1, 1, 0.92, 0.5 + 0.5 * rng.random()))
                g.add(Ellipse(pos=(sx, sy), size=(size, size)))
            self.oval(g, "#F4F0DC", 30, 82, 5, 5, light=1.0)
            self.oval(g, SKIES["night"][0], 32.5, 83.5, 4.4, 4.4, light=1.0)
        elif self.phase != "night" and self.weather in ("", "clear", "wind"):
            sun_y = 84 if self.phase == "day" else 46
            self.oval(g, "#FFE9A8", 158, sun_y, 9, 9, alpha=0.25, light=1.0)
            self.oval(g, "#FFE08A" if self.phase == "day" else "#FFB06A", 158, sun_y, 5.5, 5.5, light=1.0)

        if self.weather in ("cloudy", "rain", "storm", "snow", "fog", "wind"):
            cloud = "#E7EBEF" if self.weather in ("cloudy", "wind", "fog") else "#8F97A3"
            for cx, cy, w in ((40, 80, 1.0), (120, 88, 1.3), (175, 74, 0.9), (-10, 70, 0.9), (220, 84, 1.1)):
                for dx, dy, r in ((0, 0, 7), (7, 2, 8), (15, 0, 6), (7, -2, 6)):
                    self.oval(g, cloud, cx + dx * w, cy + dy * w, r * w * 1.1, r * w * 0.8, alpha=0.9)

    def _virtual_left_right(self) -> Tuple[float, float]:
        left = (self.x - self._ox) / self._s
        right = (self.right - self._ox) / self._s
        return left - 5, right + 5

    def _draw_landscape(self, g):
        left, right = self._virtual_left_right()
        # Far hills
        coords = [left, HORIZON]
        x = left
        while x <= right:
            coords += [x, HORIZON + 10 + 6 * math.sin(x / 23.0) + 3 * math.sin(x / 9.0)]
            x += 4
        coords += [right, HORIZON]
        self.poly(g, "#4E6B7A" if self.phase == "day" else "#3A4A5E", [(left + right) / 2, HORIZON] + coords)
        # Nearer hills
        coords = []
        x = left
        while x <= right:
            coords += [x, HORIZON + 4 + 4 * math.sin(x / 17.0 + 1.3)]
            x += 4
        self.poly(g, "#3F6A3A", [(left + right) / 2, HORIZON] + [left, HORIZON] + coords + [right, HORIZON])
        # Tree lines on both sides
        rng = random.Random(11)
        trees = [(x, rng.uniform(0.8, 1.3)) for x in list(range(int(left), 38, 7)) + list(range(166, int(right) + 8, 7))]
        for tx, scale in trees:
            self._pine(g, tx, HORIZON - 3, scale)

    def _pine(self, g, x, y, scale=1.0, color="#23452A"):
        self.rect(g, "#4A3322", x - 0.8 * scale, y, 1.6 * scale, 4 * scale)
        for i, (w, h) in enumerate(((7, 9), (5.6, 8), (4, 7))):
            base = y + 3 * scale + i * 4.5 * scale
            self.poly(g, color, [x, base + h * scale, x - w * scale, base, x + w * scale, base])

    def _draw_keep(self, g):
        base = HORIZON + 12
        self.rect(g, "#6B6F76", 150, base, 16, 20)
        self.rect(g, "#5A5E65", 146, base, 5, 26)
        self.rect(g, "#5A5E65", 165, base, 5, 26)
        for bx in (146, 148.5, 165, 167.5):
            self.rect(g, "#5A5E65", bx, base + 26, 1.6, 2)
        for bx in range(150, 166, 3):
            self.rect(g, "#6B6F76", bx, base + 20, 1.6, 2)
        self.rect(g, "#2A2A30", 156.5, base, 3, 6)
        self.line(g, "#3B2A1A", [158, base + 22, 158, base + 32], 0.5)
        self.poly(g, "#B03A2E", [158, base + 32, 158, base + 28.5, 163, base + 30.3])

    def _draw_ground(self, g):
        left, right = self._virtual_left_right()
        ground = "#5A7A3A"
        if self.weather == "snow":
            ground = "#DCE3E8"
        g.add(self.shade(ground))
        g.add(Rectangle(pos=(self.x, self.y), size=(self.width, self.P(0, HORIZON)[1] - self.y)))
        clearing = "#8A7550" if self.weather != "snow" else "#C7CDD2"
        self.oval(g, clearing, FIRE_X - 4, 14, 82, 16)
        # a few grass tufts
        rng = random.Random(5)
        for _ in range(26):
            gx = rng.uniform(left, right)
            gy = rng.uniform(1, HORIZON - 4)
            if abs(gx - FIRE_X) < 70 and gy < 26:
                continue
            self.line(g, "#3F5E2A" if self.weather != "snow" else "#9AA7AE", [gx, gy, gx - 1, gy + 2.5], 0.35)
            self.line(g, "#3F5E2A" if self.weather != "snow" else "#9AA7AE", [gx, gy, gx + 1, gy + 2.8], 0.35)

    # camp structures ------------------------------------------------------------------
    def _draw_palisade(self, g):
        for i in range(-2, 40):
            x = 8 + i * 5
            if 96 < x < 110:
                continue  # gate
            h = 12 + (i % 3)
            self.rect(g, "#6B4A2E", x, HORIZON - 7, 3.6, h)
            self.poly(g, "#5A3D25", [x + 1.8, HORIZON - 7 + h + 3, x, HORIZON - 7 + h, x + 3.6, HORIZON - 7 + h])
        self.line(g, "#4A3322", [-20, HORIZON - 2, 220, HORIZON - 2], 0.5)

    def _draw_watchtower(self, g):
        x0, y0 = 176, 24
        for lx in (x0, x0 + 12):
            self.line(g, "#5A3D25", [lx, y0, lx + (3 if lx == x0 else -3), y0 + 34], 0.9)
        self.line(g, "#5A3D25", [x0, y0 + 8, x0 + 12, y0 + 20], 0.5)
        self.line(g, "#5A3D25", [x0 + 12, y0 + 8, x0, y0 + 20], 0.5)
        self.rect(g, "#7A5534", x0 - 2, y0 + 33, 16, 4)
        for px in range(0, 16, 3):
            self.rect(g, "#6B4A2E", x0 - 2 + px, y0 + 37, 1.2, 4)
        self.poly(g, "#8E3A1C", [x0 + 6, y0 + 50, x0 - 4, y0 + 41, x0 + 16, y0 + 41])

    def _draw_lean_to(self, g):
        self.poly(g, "#6E7F52", [30, 10, 52, 30, 60, 10])
        self.line(g, "#5A3D25", [28, 9, 53, 32], 0.8)
        self.line(g, "#5A3D25", [60, 9, 51, 31], 0.6)
        self.poly(g, "#58693F", [44, 10, 52, 26, 60, 10])

    def _draw_tent(self, g):
        self.poly(g, "#CDBB91", [44, 36, 26, 8, 62, 8])
        self.poly(g, "#B8A67C", [44, 36, 52, 8, 62, 8])
        self.poly(g, "#3A2A1A", [44, 24, 39, 8, 49, 8])
        self.line(g, "#5A3D25", [44, 36, 44, 39], 0.6)
        self.line(g, "#7A6A4A", [26, 8, 20, 4], 0.3)
        self.line(g, "#7A6A4A", [62, 8, 68, 4], 0.3)

    def _draw_pavilion(self, g):
        self.rect(g, "#EDE3CC", 22, 8, 44, 20)
        for i in range(0, 44, 8):
            self.rect(g, "#A8322A", 22 + i, 8, 4, 20)
        self.poly(g, "#A8322A", [44, 44, 18, 28, 70, 28])
        self.poly(g, "#EDE3CC", [44, 44, 31, 28, 38, 28])
        self.poly(g, "#EDE3CC", [44, 44, 50, 28, 57, 28])
        for i in range(0, 48, 6):
            self.poly(g, "#D4A937", [19 + i, 28, 22 + i, 28, 20.5 + i, 25.5])
        self.poly(g, "#3A2A1A", [44, 22, 38, 8, 50, 8])
        self.line(g, "#5A3D25", [44, 44, 44, 52], 0.5)
        self.poly(g, "#D4A937", [44, 52, 44, 48, 50, 50])

    def _draw_banner(self, g):
        self.line(g, "#4A3322", [72, 6, 72, 48], 0.7)
        self.oval(g, "#D4A937", 72, 48.5, 1, 1)
        self.poly(g, "#2F4F8F", [72.5, 46, 72.5, 34, 77, 31, 81.5, 34, 81.5, 46])
        self.poly(g, "#D4A937", [77, 43, 74.5, 38.5, 77, 34, 79.5, 38.5])

    def _draw_merchant(self, g):
        x = 143
        self.rect(g, "#7A5534", x, 8, 22, 9)
        self.rect(g, "#5A3D25", x, 8, 1.4, 20)
        self.rect(g, "#5A3D25", x + 20.6, 8, 1.4, 20)
        for i in range(6):
            self.poly(g, "#D4A937" if i % 2 else "#2F6F5F",
                      [x - 2 + i * 4.3, 28, x + 2.3 + i * 4.3, 28, x + 2.3 + i * 4.3, 24, x - 2 + i * 4.3, 24])
        for i, c in enumerate(("#C8552B", "#D4A937", "#8E5BA8", "#4F8A3C")):
            self.oval(g, c, x + 4 + i * 4.5, 18.5, 1.6, 1.4)
        self._figure(g, x + 11, 8.5, "#2F6F5F", "#D9B38C", hat="#6B4A2E", scale=0.85, sitting=False, behind=True)

    def _draw_horse(self, g):
        x, y = 176, 6
        coat, dark = "#7A4E2D", "#4A2E1A"
        for lx in (x - 7, x - 4, x + 5, x + 8):
            self.line(g, dark, [lx, y + 8, lx, y], 0.8)
        self.oval(g, coat, x, y + 11, 11, 5)
        self.poly(g, coat, [x + 7, y + 13, x + 12, y + 20, x + 15, y + 18.5, x + 11, y + 10])
        self.oval(g, coat, x + 15, y + 19, 3.4, 2.1)
        self.line(g, dark, [x + 12, y + 20.5, x + 9, y + 14], 0.8)
        self.line(g, dark, [x - 10.5, y + 12, x - 13, y + 4], 0.7)
        self.rect(g, "#8E3A1C", x - 3, y + 14.5, 6, 2)

    def _draw_lantern_post(self, g):
        self.line(g, "#4A3322", [129, 6, 129, 30], 0.7)
        self.line(g, "#4A3322", [129, 30, 134, 30], 0.5)
        self.line(g, "#4A3322", [133.5, 30, 133.5, 28], 0.3)
        self.rect(g, "#2E2A26", 132, 23.5, 3, 4.5)

    def _draw_log(self, g):
        self.rect(g, "#6B4A2E", 68, 5, 18, 5)
        self.oval(g, "#8B6A43", 86, 7.5, 1.4, 2.5)
        self.line(g, "#4A3322", [70, 7.5, 84, 7.5], 0.25)

    def _draw_fire_base(self, g):
        fire = self.loadout.get("fire", "campfire_small")
        if fire in ("campfire_medium", "campfire_large"):
            radius = 8 if fire == "campfire_medium" else 10.5
            for i in range(12):
                a = 2 * math.pi * i / 12
                self.oval(g, "#7D7A74" if i % 2 else "#696660", FIRE_X + math.cos(a) * radius,
                          FIRE_Y - 2 + math.sin(a) * radius * 0.35, 2.2, 1.5)
        self.line(g, "#4A3322", [FIRE_X - 6, FIRE_Y - 3, FIRE_X + 6, FIRE_Y + 1], 1.1)
        self.line(g, "#5A3D25", [FIRE_X + 6, FIRE_Y - 3, FIRE_X - 6, FIRE_Y + 1], 1.1)
        if self.loadout.get("pot"):
            self.line(g, "#2E2A26", [FIRE_X - 7, FIRE_Y - 3, FIRE_X, FIRE_Y + 17], 0.4)
            self.line(g, "#2E2A26", [FIRE_X + 7, FIRE_Y - 3, FIRE_X, FIRE_Y + 17], 0.4)
            self.line(g, "#2E2A26", [FIRE_X, FIRE_Y + 17, FIRE_X, FIRE_Y + 12.5], 0.25)
            self.oval(g, "#2E2A26", FIRE_X, FIRE_Y + 10, 3.6, 2.8)
            self.rect(g, "#1E1B18", FIRE_X - 3.6, FIRE_Y + 11.8, 7.2, 0.8)

    def _draw_gear(self, g):
        has = self.loadout.get
        if has("back"):
            self.rect(g, "#7A5534", 58, 4, 7, 8)
            self.rect(g, "#5A3D25", 58, 10, 7, 2.5)
            self.oval(g, "#8B6A43", 61.5, 12.8, 3.4, 1.2)
            self.line(g, "#4A3322", [60, 4, 60, 11], 0.25)
        weapon = has("weapon")
        if weapon == "walking_staff":
            self.line(g, "#6B4A2E", [55, 3, 62, 30], 0.6)
        elif weapon == "sword":
            self.line(g, "#C9CED3", [66, 4, 66, 20], 0.55, light=None)
            self.line(g, "#6B4A2E", [63.5, 20, 68.5, 20], 0.5)
            self.line(g, "#4A3322", [66, 20, 66, 23.5], 0.5)
            self.oval(g, "#D4A937", 66, 24, 0.9, 0.9)
        offhand = has("offhand")
        if offhand == "wooden_shield":
            self.oval(g, "#6B4A2E", 90, 7.5, 4.2, 5)
            self.oval(g, "#8B6A43", 90, 7.5, 3.4, 4.2)
            self.oval(g, "#9DA3A9", 90, 7.5, 1.1, 1.1)
        elif offhand == "heater_shield":
            self.poly(g, "#2F4F8F", [90, 2, 85, 8, 85, 13, 95, 13, 95, 8])
            self.poly(g, "#D4A937", [90, 11.5, 88.2, 8, 90, 4.5, 91.8, 8])

    def _figure(self, g, x, y, body, skin, hat=None, scale=1.0, sitting=True, behind=False):
        """A small generic NPC."""
        s = scale
        if not sitting:
            self.line(g, "#3A2A1A", [x - 1.2 * s, y, x - 1.2 * s, y + 6 * s], 0.7 * s)
            self.line(g, "#3A2A1A", [x + 1.2 * s, y, x + 1.2 * s, y + 6 * s], 0.7 * s)
            y += 6 * s
        self.poly(g, body, [x, y + 9 * s, x - 3.2 * s, y, x + 3.2 * s, y])
        self.oval(g, skin, x, y + 10.8 * s, 2 * s, 2 * s)
        if hat:
            self.poly(g, hat, [x - 2.6 * s, y + 11.5 * s, x + 2.6 * s, y + 11.5 * s, x + 0.5 * s, y + 15 * s])

    def _draw_dog(self, g):
        x, y = 118, 3
        fur, dark, light = "#4A2F1C", "#2A1A10", "#D8C3A0"
        self.oval(g, "#000000", x - 1, y + 0.2, 7, 1.1, alpha=0.25)
        self.oval(g, fur, x, y + 2.2, 5.5, 2.3)
        self.oval(g, fur, x - 5, y + 3.8, 2.3, 2.1)
        self.oval(g, light, x - 3.6, y + 2.4, 1.6, 1.3)
        self.poly(g, dark, [x - 6.4, y + 5.2, x - 5.3, y + 7.4, x - 4.2, y + 5.2])
        self.oval(g, light, x - 7.1, y + 3.2, 1.2, 0.9)
        self.oval(g, "#1A1210", x - 8, y + 3.4, 0.45, 0.4)
        self.line(g, fur, [x + 5, y + 2.5, x + 8.5, y + 4.5], 0.6)

    def _draw_bard(self, g):
        x, y = 124, 8
        self._figure(g, x, y, "#7B4B94", "#E0B894", hat="#2F6F5F", scale=0.95)
        self.oval(g, "#B5651D", x - 2.6, y + 4.2, 2.2, 1.7)
        self.line(g, "#6B4A2E", [x - 1, y + 5, x + 3.5, y + 9], 0.35)
        self.line(g, "#E0B894", [x - 3, y + 7, x - 1, y + 4.2], 0.4)

    def _draw_squire(self, g):
        self._figure(g, 137.5, 4, "#2F4F8F", "#E0B894", hat=None, scale=0.8, sitting=False)
        self.line(g, "#9DA3A9", [140.5, 6, 140.5, 16], 0.35)

    def _draw_falcon(self, g):
        self.line(g, "#2A2320", [132, 76, 136, 78, 138, 76.5, 140, 78, 144, 76], 0.45, light=1.0)

    # the traveler ------------------------------------------------------------------
    def _draw_traveler(self, g):
        has = self.loadout.get
        seat = 10.5 if has("seat") else 5.5
        x = 77.5
        body_id = has("body", "tunic_simple")
        body, body_dark = BODY_COLORS.get(body_id, BODY_COLORS["tunic_simple"])
        skin, hair = "#E0B894", "#4A3322"
        cloak = has("cloak")
        if cloak:
            self.poly(g, "#3E5E3A", [x - 1, seat + 15, x - 5.5, seat - 3, x + 2.5, seat - 1, x + 3, seat + 14])
        # legs: thigh forward, shin down
        self.line(g, "#4A3A2A", [x, seat + 1, x + 7, seat + 2, x + 8, seat - 5.5], 1.5)
        self.line(g, "#3A2A1A", [x + 7.2, seat - 5.8, x + 9.8, seat - 5.8], 1.1)
        # torso
        self.poly(g, body, [x - 3.4, seat, x + 3.4, seat, x + 3.2, seat + 13, x - 3.2, seat + 13])
        if body_id == "leather_jerkin":
            self.line(g, body_dark, [x - 3, seat + 12, x + 3, seat + 2], 0.45)
        elif body_id in ("chainmail", "plate_armour"):
            for row in range(1, 6):
                self.line(g, body_dark, [x - 3, seat + row * 2.2, x + 3, seat + row * 2.2], 0.2)
            if body_id == "plate_armour":
                self.oval(g, "#E6EAED", x - 3.2, seat + 12.6, 2.1, 1.5)
                self.oval(g, "#E6EAED", x + 3.2, seat + 12.6, 2.1, 1.5)
        self.line(g, "#3A2A1A", [x - 3.4, seat + 3.5, x + 3.4, seat + 3.5], 0.5)
        if has("weapon") == "dagger":
            self.line(g, "#C9CED3", [x + 2.6, seat + 3.2, x + 4, seat - 0.8], 0.35)
        # arm reaching toward the fire
        self.line(g, body_dark, [x + 1, seat + 11.5, x + 5.5, seat + 7.5, x + 9.5, seat + 7.8], 1.0)
        self.oval(g, skin, x + 10, seat + 7.8, 1.1, 1.1)
        # head
        head_y = seat + 16.5
        self.oval(g, skin, x + 0.4, head_y, 3.1, 3.3)
        helmet = has("head")
        if helmet:
            self.poly(g, "#A9AFB5", [x - 3.2, head_y + 0.6, x + 3.8, head_y + 0.6, x + 3.3, head_y + 3.3,
                                     x + 0.3, head_y + 4.6, x - 2.7, head_y + 3.3])
            self.line(g, "#8F979E", [x + 3.3, head_y + 0.6, x + 3.3, head_y - 2.5], 0.35)
            self.line(g, "#C8552B", [x + 0.3, head_y + 4.6, x - 2.5, head_y + 7.5, x - 5, head_y + 6.5], 0.8)
        elif cloak:
            self.poly(g, "#3E5E3A", [x - 3.8, head_y - 2, x - 3.4, head_y + 3, x + 0.3, head_y + 4.8,
                                     x + 3.2, head_y + 2.8, x + 1, head_y + 3.2, x - 1.6, head_y + 1])
        else:
            self.poly(g, hair, [x - 3, head_y + 0.5, x - 2, head_y + 3.4, x + 1.5, head_y + 3.6, x + 3.3, head_y + 1.8,
                                x + 1, head_y + 2.2])
        self.oval(g, "#2A2320", x + 2.2, head_y + 0.4, 0.45, 0.45)

    # animated layer ------------------------------------------------------------------
    def _seed_precipitation(self):
        rng = random.Random(3)
        count = {"rain": 70, "storm": 110, "snow": 55}.get(self.weather, 0)
        self._precip = [(rng.random(), rng.random(), rng.uniform(0.7, 1.3)) for _ in range(count)]

    def _fire_scale(self) -> float:
        return {"campfire_small": 1.0, "campfire_medium": 1.35, "campfire_large": 1.8}.get(
            self.loadout.get("fire", "campfire_small"), 1.0)

    def _flame(self, g, color, cx, base, w, h, sway, alpha=1.0):
        tip = (cx + sway, base + h)
        coords = [cx, base + h * 0.3,
                  cx - w, base, cx - w * 0.9, base + h * 0.35, cx - w * 0.45, base + h * 0.7,
                  tip[0], tip[1],
                  cx + w * 0.45, base + h * 0.7, cx + w * 0.9, base + h * 0.35, cx + w, base]
        self.poly(g, color, coords, alpha=alpha, light=1.0)

    def _draw_animated(self):
        if not hasattr(self, "_s"):
            return
        g = self._animated
        g.clear()
        t = self._t
        k = self._fire_scale()
        night = self.phase in ("night", "dusk")
        flicker = 0.85 + 0.15 * math.sin(t * 9.1) * math.sin(t * 4.3 + 1)

        # Warm glow around the fire, stronger at night.
        glow_alpha = (0.07 if night else 0.035) * flicker
        for i in range(6, 0, -1):
            self.oval(g, "#FF9A3C", FIRE_X, FIRE_Y + 4 * k, 7 * k * i * 0.9, 4.5 * k * i * 0.7,
                      alpha=glow_alpha, light=1.0)

        base = FIRE_Y - 1.5
        for i, (dx, w, h, phase) in enumerate(((-2.8, 2.6, 9, 0.0), (2.8, 2.6, 8, 1.7), (0, 3.6, 13, 0.9))):
            sway = 1.3 * math.sin(t * (5 + i) + phase)
            hh = h * k * (0.88 + 0.14 * math.sin(t * (7.3 + i) + phase * 2))
            self._flame(g, "#D9422B", FIRE_X + dx * k, base, w * k, hh, sway * k)
            self._flame(g, "#F28C28", FIRE_X + dx * k, base, w * k * 0.68, hh * 0.72, sway * k * 0.8)
            self._flame(g, "#FFD35C", FIRE_X + dx * k, base, w * k * 0.35, hh * 0.45, sway * k * 0.5)
        # Sparks
        for i in range(5):
            life = (t * 0.7 + i / 5.0) % 1.0
            sx = FIRE_X + math.sin(i * 12.9 + t) * 4 * k
            sy = base + 8 * k + life * 22 * k
            self.oval(g, "#FFC061", sx, sy, 0.45, 0.45, alpha=1 - life, light=1.0)

        if self.loadout.get("lantern"):
            self.oval(g, "#FFD35C", 133.5, 25.7, 4.5, 4.5, alpha=0.18 * flicker, light=1.0)
            self.oval(g, "#FFE08A", 133.5, 25.7, 1.2, 1.7, light=1.0)

        if self._precip:
            left = self.x
            span_w = self.width
            span_h = self.height
            if self.weather == "snow":
                g.add(Color(1, 1, 1, 0.85))
                for fx, fy, sp in self._precip:
                    px = left + ((fx * span_w + math.sin(t * sp + fy * 9) * 8) % span_w)
                    py = self.y + ((fy * span_h - t * 18 * sp) % span_h)
                    size = 2.2 * sp
                    g.add(Ellipse(pos=(px, py), size=(size, size)))
            else:
                g.add(Color(0.75, 0.82, 0.92, 0.55))
                for fx, fy, sp in self._precip:
                    px = left + fx * span_w
                    py = self.y + ((fy * span_h - t * 260 * sp) % span_h)
                    g.add(Line(points=[px, py, px - 2, py - 9 * sp], width=1))
        if self.weather == "fog":
            g.add(Color(0.85, 0.87, 0.9, 0.28))
            g.add(Rectangle(pos=self.pos, size=(self.width, self.height * 0.55)))


def loadout_ids(items: Iterable) -> Dict[str, str]:
    """Convert a Progression loadout (slot -> Item) into slot -> item id."""
    if isinstance(items, dict):
        return {slot: item.id for slot, item in items.items()}
    return {item.slot: item.id for item in items}
