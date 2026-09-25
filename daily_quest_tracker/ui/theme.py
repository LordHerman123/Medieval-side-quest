"""Colours, fonts and sizes for the medieval look."""

from __future__ import annotations

import os

from kivy.core.text import DEFAULT_FONT, LabelBase
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
FONT_DIR = os.path.join(ASSETS, "fonts")


def hex_color(value: str, alpha: float = 1.0):
    r, g, b, _ = get_color_from_hex(value)
    return [r, g, b, alpha]


BG = hex_color("#1C1814")
BG_RAISED = hex_color("#27211B")
PARCHMENT = hex_color("#EADCBF")
PARCHMENT_DARK = hex_color("#D5C198")
INK = hex_color("#3A2A1A")
INK_SOFT = hex_color("#6A5540")
GOLD = hex_color("#D4A937")
GOLD_DARK = hex_color("#9C7A22")
EMBER = hex_color("#C8552B")
EMBER_DARK = hex_color("#8E3A1C")
LEATHER = hex_color("#6B4A2E")
MOSS = hex_color("#4F7A3A")
TEXT = hex_color("#F1E5CC")
TEXT_MUTED = hex_color("#AE9E80")
BORDER = hex_color("#6E5838")

FONT_SIZE = sp(15)
FONT_SMALL = sp(12.5)
FONT_LARGE = sp(19)
FONT_TITLE = sp(22)

PADDING = dp(12)
SPACING = dp(10)
MAX_CONTENT_WIDTH = dp(720)
RADIUS = dp(10)


def register_fonts() -> None:
    """Use a bundled serif face everywhere; fall back to Kivy's default if it's missing."""
    regular = os.path.join(FONT_DIR, "DejaVuSerif.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuSerif-Bold.ttf")
    if os.path.exists(regular) and os.path.exists(bold):
        LabelBase.register(DEFAULT_FONT, fn_regular=regular, fn_bold=bold, fn_italic=regular, fn_bolditalic=bold)
