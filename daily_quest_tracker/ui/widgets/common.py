"""Reusable themed widgets: parchment panels, buttons, wrapped labels, chips, XP bar."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from ui import theme


class WrapLabel(Label):
    """A label that wraps to its width and grows to fit its text."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "top")
        kwargs.setdefault("color", theme.INK)
        kwargs.setdefault("font_size", theme.FONT_SIZE)
        super().__init__(**kwargs)
        self.bind(width=self._update_text_size, texture_size=self._update_height)
        self._update_text_size()

    def _update_text_size(self, *_):
        self.text_size = (self.width, None)

    def _update_height(self, *_):
        self.height = self.texture_size[1]


class Panel(BoxLayout):
    """A vertical card that sizes itself to its content and draws a framed background."""

    bg_color = ListProperty(theme.PARCHMENT)
    border_color = ListProperty(theme.BORDER)
    border_width = NumericProperty(dp(1.4))
    double_border = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", theme.PADDING)
        kwargs.setdefault("spacing", dp(6))
        super().__init__(**kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.bind(pos=self._draw, size=self._draw, bg_color=self._draw, border_color=self._draw,
                  double_border=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 0.35)
            RoundedRectangle(pos=(self.x + dp(2), self.y - dp(3)), size=self.size, radius=[theme.RADIUS])
            Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[theme.RADIUS])
            Color(*self.border_color)
            Line(rounded_rectangle=(self.x, self.y, self.width, self.height, theme.RADIUS), width=self.border_width)
            if self.double_border:
                inset = dp(4)
                Line(rounded_rectangle=(self.x + inset, self.y + inset, self.width - 2 * inset,
                                        self.height - 2 * inset, theme.RADIUS - dp(2)), width=dp(0.8))


class QuestButton(Button):
    """Flat rounded button with a few themed variants."""

    variant = StringProperty("primary")

    VARIANTS = {
        "primary": (theme.EMBER, theme.EMBER_DARK, theme.TEXT),
        "gold": (theme.GOLD, theme.GOLD_DARK, theme.INK),
        "leather": (theme.LEATHER, theme.hex_color("#4E3520"), theme.TEXT),
        "moss": (theme.MOSS, theme.hex_color("#36552A"), theme.TEXT),
        "ghost": (theme.hex_color("#000000", 0.0), theme.hex_color("#000000", 0.12), theme.INK_SOFT),
        "dark": (theme.BG_RAISED, theme.BG, theme.TEXT),
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(42))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("font_size", theme.FONT_SIZE)
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_color = (0, 0, 0, 0)
        self.bind(pos=self._draw, size=self._draw, state=self._draw, variant=self._draw, disabled=self._draw)
        self.bind(size=lambda *_: setattr(self, "text_size", (self.width - dp(8), None)))
        self._draw()

    def _draw(self, *_):
        normal, pressed, text = self.VARIANTS.get(self.variant, self.VARIANTS["primary"])
        self.color = text
        self.canvas.before.clear()
        with self.canvas.before:
            fill = pressed if self.state == "down" else normal
            Color(fill[0], fill[1], fill[2], fill[3] * (0.45 if self.disabled else 1))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            if self.variant == "ghost":
                Color(*theme.INK_SOFT[:3], 0.6)
                Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(8)), width=dp(1))
            elif self.variant != "dark":
                Color(1, 1, 1, 0.12)
                Line(rounded_rectangle=(self.x + dp(1.5), self.y + dp(1.5), self.width - dp(3),
                                        self.height - dp(3), dp(7)), width=dp(0.8))


def button_row(buttons: Sequence[Widget], height: float = dp(42)) -> BoxLayout:
    row = BoxLayout(size_hint_y=None, height=height, spacing=dp(8))
    for b in buttons:
        row.add_widget(b)
    return row


class Chip(Label):
    """A small coloured tag, e.g. a category."""

    chip_color = ListProperty(theme.LEATHER)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("font_size", theme.FONT_SMALL)
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", theme.TEXT)
        kwargs.setdefault("padding", (dp(9), dp(3)))
        super().__init__(**kwargs)
        self.bind(texture_size=self._fit, pos=self._draw, size=self._draw, chip_color=self._draw)
        self._fit()

    def _fit(self, *_):
        self.size = self.texture_size

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.chip_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])


class XpBar(Widget):
    value = NumericProperty(0.0)  # 0..1
    fill_color = ListProperty(theme.GOLD)
    track_color = ListProperty(theme.hex_color("#000000", 0.35))

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(10))
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw, value=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        radius = self.height / 2
        with self.canvas:
            Color(*self.track_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
            if self.value > 0:
                Color(*self.fill_color)
                width = max(self.height, self.width * min(1.0, self.value))
                RoundedRectangle(pos=self.pos, size=(width, self.height), radius=[radius])
                Color(1, 1, 1, 0.25)
                RoundedRectangle(pos=(self.x + dp(2), self.y + self.height * 0.55),
                                 size=(max(0, width - dp(4)), self.height * 0.25), radius=[radius / 2])


class LevelBadge(Label):
    """A gold shield-like disc showing the level number."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(44), dp(44)))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("font_size", theme.FONT_LARGE)
        kwargs.setdefault("color", theme.INK)
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.GOLD_DARK)
            Ellipse(pos=self.pos, size=self.size)
            Color(*theme.GOLD)
            inset = dp(3)
            Ellipse(pos=(self.x + inset, self.y + inset), size=(self.width - 2 * inset, self.height - 2 * inset))


class SectionHeader(BoxLayout):
    """An ornamented section title for dark backgrounds: ── TITLE ──"""

    def __init__(self, text: str, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(30))
        super().__init__(**kwargs)
        self.label = Label(text=text.upper(), bold=True, font_size=theme.FONT_SMALL, color=theme.GOLD,
                           size_hint_x=None)
        self.label.bind(texture_size=lambda *_: setattr(self.label, "width", self.label.texture_size[0] + dp(16)))
        self.add_widget(Widget())
        self.add_widget(self.label)
        self.add_widget(Widget())
        self.bind(pos=self._draw, size=self._draw)
        self.label.bind(size=self._draw, pos=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        mid = self.y + self.height / 2
        with self.canvas.before:
            Color(*theme.GOLD_DARK)
            Line(points=[self.x + dp(4), mid, self.label.x, mid], width=dp(1))
            Line(points=[self.label.right, mid, self.right - dp(4), mid], width=dp(1))


class Column(BoxLayout):
    """Vertical content column, centred with a maximum width so desktop layouts stay readable."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", theme.SPACING)
        super().__init__(**kwargs)
        self.bind(minimum_height=self.setter("height"), width=self._repad)
        self._repad()

    def _repad(self, *_):
        side = max(theme.PADDING, (self.width - theme.MAX_CONTENT_WIDTH) / 2)
        self.padding = (side, theme.PADDING, side, dp(24))


def scrolling_column() -> tuple:
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), bar_color=theme.GOLD_DARK,
                        bar_inactive_color=theme.hex_color("#9C7A22", 0.3))
    column = Column()
    scroll.add_widget(column)
    return scroll, column


class DarkBackground(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*theme.BG)
            Rectangle(pos=self.pos, size=self.size)


class ThemedSpinnerOption(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_color = theme.hex_color("#3A3026")
        self.color = theme.TEXT
        self.font_size = theme.FONT_SMALL
        self.height = dp(40)


class ThemedSpinner(Spinner):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(38))
        kwargs.setdefault("font_size", theme.FONT_SMALL)
        kwargs.setdefault("option_cls", ThemedSpinnerOption)
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = theme.LEATHER
        self.color = theme.TEXT
        self.bind(size=lambda *_: setattr(self, "text_size", (self.width - dp(10), None)))
        self.halign = "center"
        self.shorten = True


class ThemedInput(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(42))
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_size", theme.FONT_SIZE)
        kwargs.setdefault("write_tab", False)
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_active = ""
        self.background_color = theme.hex_color("#F6EEDC")
        self.foreground_color = theme.INK
        self.cursor_color = theme.EMBER
        self.hint_text_color = theme.hex_color("#8C7A60")
        self.padding = (dp(10), dp(11), dp(10), dp(8))


class OnOffToggle(QuestButton):
    """A themed on/off switch (Kivy's default Switch doesn't match the look)."""

    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(74), dp(34)))
        kwargs.setdefault("font_size", theme.FONT_SMALL)
        super().__init__(**kwargs)
        self.bind(active=self._sync, on_release=lambda *_: setattr(self, "active", not self.active))
        self._sync()

    def _sync(self, *_):
        self.text = "On" if self.active else "Off"
        self.variant = "moss" if self.active else "leather"


class EmptyState(WrapLabel):
    def __init__(self, text: str, **kwargs):
        kwargs.setdefault("color", theme.TEXT_MUTED)
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("italic", True)
        super().__init__(text=text, **kwargs)


class Toast(AnchorLayout):
    """A brief message floating near the bottom of the screen."""

    def __init__(self, **kwargs):
        super().__init__(anchor_x="center", anchor_y="bottom", padding=(dp(16), dp(80)), **kwargs)
        self.label = Label(size_hint=(None, None), color=theme.INK, bold=True, font_size=theme.FONT_SIZE,
                           padding=(dp(16), dp(10)), halign="center", opacity=0)
        self.label.bind(texture_size=self._fit, pos=self._draw, size=self._draw)
        self.add_widget(self.label)

    def _fit(self, *_):
        self.label.size = self.label.texture_size

    def _draw(self, *_):
        self.label.canvas.before.clear()
        with self.label.canvas.before:
            Color(*theme.GOLD)
            RoundedRectangle(pos=self.label.pos, size=self.label.size, radius=[dp(12)])

    def show(self, text: str, duration: float = 2.4) -> None:
        self.label.text_size = (min(dp(340), self.width - dp(48)), None)
        self.label.text = text
        Animation.cancel_all(self.label)
        self.label.opacity = 0
        (Animation(opacity=1, duration=0.2) + Animation(duration=duration)
         + Animation(opacity=0, duration=0.4)).start(self.label)


def on_press(button: Button, callback: Callable[[], None]) -> Button:
    button.bind(on_release=lambda *_: callback())
    return button


def label(text: str, *, color=None, size=None, bold: bool = False, halign: str = "left",
          wrap: bool = True, italic: bool = False, markup: bool = False) -> Label:
    kwargs = dict(text=text, color=color or theme.INK, font_size=size or theme.FONT_SIZE, bold=bold,
                  halign=halign, italic=italic, markup=markup)
    if wrap:
        return WrapLabel(**kwargs)
    return Label(size_hint_y=None, height=dp(24), **kwargs)


def spacer(height: float = dp(4)) -> Widget:
    return Widget(size_hint_y=None, height=height)


def format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"about {minutes} min"
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"about {hours} hour{'s' if hours > 1 else ''}"
    return f"about {hours} h {rest} min"


def format_temperature(celsius: float, unit: Optional[str]) -> str:
    if unit == "F":
        return f"{celsius * 9 / 5 + 32:.0f}°F"
    return f"{celsius:.0f}°C"
