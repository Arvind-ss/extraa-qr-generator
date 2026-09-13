"""Theme tokens and ttk styling.

Colours come from ``assets/theme.json`` -- a shadcn/Tailwind token file -- so
the palette can be changed without touching Python. Edit that file and restart.

Built on ttk's ``clam`` theme, not the native ``aqua``/``vista`` ones: clam
accepts colour on every widget and renders identically on macOS and Windows,
which the native themes do not.

Three things in that token file cannot be honoured, because Tk cannot draw them:
``radius`` (0.5rem), the whole ``shadows`` scale, and any alpha. Corners stay
square, nothing casts a shadow, and every tint is pre-blended to a solid hex.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from qrgen import paths

# "light" | "dark" | "mono" | "monoDark" -- all four live in theme.json.
# EXTRAA_QR_THEME overrides this without editing the file, which is also how
# the contrast tests reach every palette.
MODE = os.environ.get("EXTRAA_QR_THEME") or "monoDark"




def _channels(colour):
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def blend(start, end, position):
    a, b = _channels(start), _channels(end)
    return "#%02x%02x%02x" % tuple(
        round(a[i] + (b[i] - a[i]) * position) for i in range(3))


def _load():
    with open(paths.resource("assets", "theme.json"), encoding="utf-8") as fh:
        return json.load(fh)


_THEME = _load()


def _luminance(colour):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _channels(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def readable(colour, background, text, minimum=4.5):
    """Push a colour toward the text colour until it is legible.

    Semantic colours are usually picked against a dark background. On a light
    one the same mint green sits at 1.77:1 against near-white -- present, and
    invisible -- and it is the line that says whether a batch is safe to run.
    Hue is preserved; only lightness moves, and only as far as it must.
    """
    if contrast(colour, background) >= minimum:
        return colour
    for step in range(2, 101, 2):
        candidate = blend(colour, text, step / 100)
        if contrast(candidate, background) >= minimum:
            return candidate
    return text


def palette(mode):
    """Every colour token for one mode, as a plain dict.

    A pure function on purpose: the contrast tests need four palettes in one
    process, and the obvious alternative -- reassigning MODE and reloading the
    module -- silently resets everything else in here, including the font
    registry the running window depends on.
    """
    try:
        c = _THEME[mode]
    except KeyError:
        raise SystemExit(
            f"unknown theme {mode!r}; assets/theme.json defines: "
            f"{', '.join(k for k, v in _THEME.items() if isinstance(v, dict) and 'background' in v)}")

    p = {
        "BG": c["background"],
        "SURFACE_1": c["card"],
        "SURFACE_2": c["muted"],
        "SURFACE_3": c["accent"],
        "BORDER": c["border"],
        "TEXT": c["foreground"],
        "TEXT_2": c["mutedForeground"],
        "ACCENT": c["primary"],
        "ON_ACCENT": c["primaryForeground"],
        "GRADIENT_TOP": c["secondary"],
    }
    text, bg, accent = p["TEXT"], p["BG"], p["ACCENT"]

    # A brighter hairline for focus and selection. The file has `ring`, but
    # that is the accent itself, too loud for a table row edge.
    p["BORDER_STRONG"] = blend(p["BORDER"], accent, 0.35)
    # Disabled and hint text: muted foreground faded toward the background.
    p["TEXT_3"] = blend(p["TEXT_2"], bg, 0.30)

    # Gradient ends and button states: the accent softened toward the
    # background. Toward the background rather than toward the text, because in
    # a monochrome palette the accent *is* the text -- blending the two would
    # leave a flat progress bar and an invisible hover. And never a chart
    # colour: those are categorical, and chart5 is pink in dark mode.
    p["ACCENT_DEEP"] = blend(accent, bg, 0.40)
    p["ACCENT_HOVER"] = blend(accent, bg, 0.18)
    p["ACCENT_PRESSED"] = blend(accent, bg, 0.32)

    # Semantic colours come from the token file so a monochrome palette can
    # make them all one colour, then each is pushed until it is legible against
    # this mode's background. Nothing signals state by colour alone -- every one
    # is paired with a glyph -- which is what makes monochrome viable at all.
    p["ERROR"] = readable(c["destructive"], bg, text)
    p["SUCCESS"] = readable(c.get("success", "#34D399"), bg, text)
    p["ATTENTION"] = readable(c.get("warning", "#FCB712"), bg, text)

    # Pre-blended at 18% against the card colour, after the adjustment above so
    # strip fills match the text on them. Tk has no alpha compositing.
    for name, source in (("TINT_ACCENT", accent), ("TINT_SUCCESS", p["SUCCESS"]),
                         ("TINT_ERROR", p["ERROR"]),
                         ("TINT_ATTENTION", p["ATTENTION"])):
        p[name] = blend(p["SURFACE_1"], source, 0.18)

    # Never tinted by the palette, never white, never black. The card is
    # white-edged and destined for print: a tinted surround casts colour onto
    # the white, a white one hides the card's boundary, a black one exaggerates
    # its contrast. Chosen by how light the background actually is, so any new
    # palette gets the right one.
    p["PREVIEW_WELL"] = "#8a8a8a" if _luminance(bg) > 0.5 else "#2e2e2e"
    return p


_P = palette(MODE)

BG = _P["BG"]
SURFACE_1 = _P["SURFACE_1"]
SURFACE_2 = _P["SURFACE_2"]
SURFACE_3 = _P["SURFACE_3"]
BORDER = _P["BORDER"]
BORDER_STRONG = _P["BORDER_STRONG"]
TEXT = _P["TEXT"]
TEXT_2 = _P["TEXT_2"]
TEXT_3 = _P["TEXT_3"]
ACCENT = _P["ACCENT"]
ON_ACCENT = _P["ON_ACCENT"]
ACCENT_DEEP = _P["ACCENT_DEEP"]
ACCENT_HOVER = _P["ACCENT_HOVER"]
ACCENT_PRESSED = _P["ACCENT_PRESSED"]
GRADIENT_TOP = _P["GRADIENT_TOP"]
ERROR = _P["ERROR"]
SUCCESS = _P["SUCCESS"]
ATTENTION = _P["ATTENTION"]
TINT_ACCENT = _P["TINT_ACCENT"]
TINT_SUCCESS = _P["TINT_SUCCESS"]
TINT_ERROR = _P["TINT_ERROR"]
TINT_ATTENTION = _P["TINT_ATTENTION"]
PREVIEW_WELL = _P["PREVIEW_WELL"]

# --- spacing ----------------------------------------------------------------

XS, SM, MD, LG, XL, XXL = 4, 8, 12, 16, 24, 32
HUGE = 48

BAND_HEIGHT = 104
TITLE_HEIGHT = 48
RAIL_HEIGHT = 56
ACTION_HEIGHT = 68
CONTENT_WIDTH = 820


# --- type -------------------------------------------------------------------

class Fonts:
    """Resolved after a root window exists, since Tk owns the font registry."""

    def __init__(self):
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        mono = self._mono_family()
        self.display = (family, 26, "bold")
        self.heading = (family, 18, "bold")
        self.body = (family, 14)
        self.body_bold = (family, 14, "bold")
        self.label = (family, 12)
        self.caption = (family, 12)
        self.micro = (family, 11, "bold")
        self.mono = (mono, 13)
        # The two values a person actually reads off the Review screen.
        self.mono_lg = (mono, 17)
        self.mono_big = (mono, 20)
        self.mono_small = (mono, 12)
        self.glyph = (family, 40)

    @staticmethod
    def _mono_family():
        available = set(tkfont.families())
        for candidate in ("SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono",
                          "Courier New"):
            if candidate in available:
                return candidate
        return tkfont.nametofont("TkFixedFont").actual("family")


FONTS = None


def micro(text):
    """Section headers are spaced-out uppercase. Tk has no letter-spacing."""
    return " ".join(text.upper())


def apply(root):
    """Install the theme. Call once, immediately after creating the root."""
    global FONTS
    FONTS = Fonts()

    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=BG)

    style.configure(".", background=BG, foreground=TEXT, borderwidth=0,
                    focuscolor=BG, font=FONTS.body)

    # --- frames
    style.configure("TFrame", background=BG)
    for name, colour in (("Surface1", SURFACE_1), ("Surface2", SURFACE_2),
                         ("Surface3", SURFACE_3), ("Base", BG),
                         ("Border", BORDER), ("Accent", ACCENT),
                         ("Well", PREVIEW_WELL), ("Success", SUCCESS),
                         ("Attention", ATTENTION), ("Error", ERROR),
                         ("TintAccent", TINT_ACCENT),
                         ("TintSuccess", TINT_SUCCESS),
                         ("TintError", TINT_ERROR),
                         ("TintAttention", TINT_ATTENTION)):
        style.configure(f"{name}.TFrame", background=colour)

    # --- labels. Named by role, then by surface, since Tk labels do not
    # inherit their parent's background.
    def label(name, font, colour, background=BG):
        style.configure(f"{name}.TLabel", background=background,
                        foreground=colour, font=font)

    for suffix, background in (("", BG), (".S1", SURFACE_1), (".S2", SURFACE_2),
                               (".S3", SURFACE_3)):
        label(f"Display{suffix}", FONTS.display, TEXT, background)
        label(f"Heading{suffix}", FONTS.heading, TEXT, background)
        label(f"Body{suffix}", FONTS.body, TEXT, background)
        label(f"BodyBold{suffix}", FONTS.body_bold, TEXT, background)
        label(f"Label{suffix}", FONTS.label, TEXT_2, background)
        label(f"Caption{suffix}", FONTS.caption, TEXT_2, background)
        label(f"Micro{suffix}", FONTS.micro, TEXT_3, background)
        label(f"Muted{suffix}", FONTS.body, TEXT_3, background)
        label(f"Mono{suffix}", FONTS.mono, TEXT, background)
        label(f"MonoLarge{suffix}", FONTS.mono_lg, TEXT, background)
        label(f"MonoBig{suffix}", FONTS.mono_big, TEXT, background)
        label(f"MonoMuted{suffix}", FONTS.mono, TEXT_2, background)
        label(f"Success{suffix}", FONTS.body, SUCCESS, background)
        label(f"Error{suffix}", FONTS.body, ERROR, background)
        label(f"Attention{suffix}", FONTS.body, ATTENTION, background)
        label(f"MonoError{suffix}", FONTS.mono_big, ERROR, background)
        label(f"MonoSuccess{suffix}", FONTS.mono_big, SUCCESS, background)

    label("Glyph", FONTS.glyph, SUCCESS)
    label("TagAccent", FONTS.mono_small, ACCENT, TINT_ACCENT)
    label("TagSuccess", FONTS.micro, SUCCESS, TINT_SUCCESS)
    label("TagMuted", FONTS.micro, TEXT_3, SURFACE_2)
    label("AttentionStrip", FONTS.body, ATTENTION, TINT_ATTENTION)

    # --- buttons. Exactly one Primary per screen.
    def button(name, background, foreground, hover, pressed, border=None):
        style.configure(f"{name}.TButton", background=background,
                        foreground=foreground, font=FONTS.body_bold,
                        relief="flat", borderwidth=1 if border else 0,
                        bordercolor=border or background,
                        lightcolor=border or background,
                        darkcolor=border or background,
                        padding=(20, 9), anchor="center")
        style.map(f"{name}.TButton",
                  background=[("disabled", SURFACE_1), ("pressed", pressed),
                              ("active", hover)],
                  foreground=[("disabled", TEXT_3)],
                  bordercolor=[("focus", ACCENT), ("disabled", BORDER)],
                  lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

    button("Primary", ACCENT, ON_ACCENT, ACCENT_HOVER, ACCENT_PRESSED)
    button("Secondary", SURFACE_2, TEXT, SURFACE_3, SURFACE_3, border=BORDER)
    button("Tertiary", BG, TEXT_2, BG, BG)
    style.configure("Tertiary.TButton", font=FONTS.body, padding=(8, 6))
    style.map("Tertiary.TButton", foreground=[("active", TEXT),
                                              ("disabled", TEXT_3)])
    # Same as Secondary but sits on a panel rather than the window background.
    button("SecondaryS1", SURFACE_2, TEXT, SURFACE_3, SURFACE_3, border=BORDER)

    button("Step", SURFACE_2, TEXT, SURFACE_3, SURFACE_3, border=BORDER)
    style.configure("Step.TButton", font=FONTS.body_bold, padding=(2, 2))

    # Sign out lives on the gradient band, so it is filled with the gradient's
    # own colour at that height instead of the window background.
    header = band_at(TITLE_HEIGHT // 2)
    button("HeaderTertiary", header, TEXT_2, header, header)
    style.configure("HeaderTertiary.TButton", font=FONTS.body, padding=(8, 6))
    style.map("HeaderTertiary.TButton", foreground=[("active", TEXT)])

    # --- inputs
    for name, background in (("TEntry", SURFACE_2), ("S1.TEntry", SURFACE_2)):
        style.configure(name, fieldbackground=background, background=background,
                        foreground=TEXT, insertcolor=ACCENT, borderwidth=1,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=(10, 8), relief="flat")
        style.map(name, bordercolor=[("focus", ACCENT), ("invalid", ERROR)],
                  lightcolor=[("focus", ACCENT), ("invalid", ERROR)],
                  darkcolor=[("focus", ACCENT), ("invalid", ERROR)])

    style.configure("Invalid.TEntry", fieldbackground=SURFACE_2,
                    foreground=TEXT, insertcolor=ACCENT, borderwidth=1,
                    bordercolor=ERROR, lightcolor=ERROR, darkcolor=ERROR,
                    padding=(10, 8), relief="flat")

    style.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE_2,
                    foreground=TEXT, arrowcolor=TEXT_2, borderwidth=1,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    padding=(10, 8), relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE_2)],
              bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)], arrowcolor=[("active", TEXT)])
    # The dropdown list is a classic Tk listbox and is not reachable by style.
    root.option_add("*TCombobox*Listbox.background", SURFACE_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # --- tables
    style.configure("Treeview", background=SURFACE_1, fieldbackground=SURFACE_1,
                    foreground=TEXT, borderwidth=0, rowheight=38,
                    font=FONTS.body)
    style.map("Treeview", background=[("selected", SURFACE_3)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=SURFACE_2, foreground=TEXT_3,
                    font=FONTS.micro, relief="flat", borderwidth=0,
                    padding=(10, 8))
    style.map("Treeview.Heading", background=[("active", SURFACE_2)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure("Vertical.TScrollbar", background=SURFACE_2,
                    troughcolor=BG, bordercolor=BG, arrowcolor=TEXT_3,
                    relief="flat", borderwidth=0)
    style.map("Vertical.TScrollbar", background=[("active", SURFACE_3)])

    style.configure("TSeparator", background=BORDER)
    style.configure("TCheckbutton", background=BG, foreground=TEXT,
                    indicatorcolor=SURFACE_2, font=FONTS.body)
    return style


# --- gradients --------------------------------------------------------------
# The only two in the application, both drawn on a canvas because ttk has no
# gradient of its own.

def band_at(y, height=None):
    """Colour of the header gradient at a given y.

    Any real widget placed on the band is opaque, so it has to be filled with
    the gradient's own colour at its position or it shows as a flat patch.
    """
    height = height or BAND_HEIGHT
    return blend(GRADIENT_TOP, BG, min(1.0, max(0.0, y / max(1, height - 1))))


class GradientBand(tk.Canvas):
    """Vertical gradient behind the title strip and step rail."""

    def __init__(self, parent, top=GRADIENT_TOP, bottom=BG, height=BAND_HEIGHT):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         background=bottom)
        self.top, self.bottom = top, bottom
        self.bind("<Configure>", lambda _: self._draw())

    def _draw(self):
        self.delete("gradient")
        width, height = self.winfo_width(), self.winfo_height()
        for y in range(height):
            self.create_line(0, y, width, y, tags="gradient",
                             fill=blend(self.top, self.bottom,
                                        y / max(1, height - 1)))
        self.tag_lower("gradient")


class GradientBar(tk.Canvas):
    """Progress fill, left to right, accent-deep into accent."""

    def __init__(self, parent, height=8, background=BG):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         background=background)
        self.fraction = 0.0
        self.bind("<Configure>", lambda _: self._draw())

    def set(self, fraction):
        self.fraction = max(0.0, min(1.0, fraction))
        self._draw()

    def _draw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        self.create_rectangle(0, 0, width, height, fill=SURFACE_2, width=0)
        filled = int(width * self.fraction)
        for x in range(filled):
            self.create_line(x, 0, x, height,
                             fill=blend(ACCENT_DEEP, ACCENT,
                                        x / max(1, width - 1)))
