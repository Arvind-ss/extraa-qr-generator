"""Reusable pieces built from the theme.

Everything here is square, flat and opaque, because that is all Tk renders.
Depth comes from surface lightness stepping up and from 1px hairlines.
"""

import tkinter as tk
from tkinter import ttk

from ui import theme as t


def hairline(parent, colour=t.BORDER, vertical=False):
    """A 1px rule. Tk has no border-bottom, so a rule is a thin frame."""
    line = tk.Frame(parent, background=colour,
                    width=1 if vertical else 0, height=0 if vertical else 1)
    return line


class Panel(tk.Frame):
    """A bordered surface. The border is a 1px outer frame around an inner fill."""

    def __init__(self, parent, fill=t.SURFACE_1, border=t.BORDER, padding=t.LG):
        super().__init__(parent, background=border, bd=0, highlightthickness=0)
        self.fill = fill
        self.body = tk.Frame(self, background=fill, bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=1, pady=1)
        self.inner = tk.Frame(self.body, background=fill)
        self.inner.pack(fill="both", expand=True, padx=padding, pady=padding)

    def set_border(self, colour):
        self.configure(background=colour)


class Tag(tk.Label):
    """Square, solid-filled label. Never a pill -- Tk has no border radius."""

    def __init__(self, parent, text, fg=t.TEXT_3, bg=t.SURFACE_2, font=None):
        super().__init__(parent, text=text, foreground=fg, background=bg,
                         font=font or t.FONTS.micro, padx=t.SM, pady=3, bd=0)


class StatusDot(tk.Frame):
    """A 6px square plus a caption. Square because everything is square."""

    def __init__(self, parent, background=t.BG):
        super().__init__(parent, background=background)
        self._bg = background
        self.dot = tk.Frame(self, width=6, height=6, background=t.TEXT_3)
        self.dot.pack(side="left", pady=(5, 0))
        self.dot.pack_propagate(False)
        self.caption = tk.Label(self, text="", font=t.FONTS.caption,
                                foreground=t.TEXT_2, background=background)
        self.caption.pack(side="left", padx=(t.SM, 0))

    def set(self, text, colour=t.TEXT_3):
        self.dot.configure(background=colour)
        self.caption.configure(text=text)


class Field(tk.Frame):
    """Label above an entry, with room for an inline error beneath it."""

    def __init__(self, parent, label, show=None, background=t.SURFACE_1,
                 width=None, mono=False):
        super().__init__(parent, background=background)
        tk.Label(self, text=label, font=t.FONTS.label, foreground=t.TEXT_2,
                 background=background, anchor="w").pack(fill="x",
                                                         pady=(0, t.XS + 2))
        # Deliberately no textvariable: every StringVar is a Tcl object whose
        # __del__ makes Tcl calls, and a screen churn leaves hundreds of them
        # for the collector to walk mid-event-loop. The entry holds its own text.
        self.entry = ttk.Entry(self, show=show,
                               font=t.FONTS.mono if mono else t.FONTS.body,
                               width=width or 20)
        self.entry.pack(fill="x", ipady=3)
        self.message = tk.Label(self, text="", font=t.FONTS.caption,
                                foreground=t.ERROR, background=background,
                                anchor="w")

    def get(self):
        return self.entry.get()

    def set(self, value):
        state = str(self.entry.cget("state"))
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, value or "")
        self.entry.configure(state=state)

    def invalid(self, message=None):
        self.entry.configure(style="Invalid.TEntry")
        if message:
            self.message.configure(text=f"✗ {message}")
            self.message.pack(fill="x", pady=(t.XS, 0))

    def clear_error(self):
        self.entry.configure(style="TEntry")
        self.message.pack_forget()

    def readonly(self, yes=True):
        self.entry.configure(state="readonly" if yes else "normal")


class DefinitionList(tk.Frame):
    """Label above value, stacked. The Review screen's left column."""

    def __init__(self, parent, background=t.BG, gap=t.XL):
        super().__init__(parent, background=background)
        self._bg = background
        self._gap = gap
        self._rows = 0

    def add(self, label, value, mono=False, wrap=None, colour=t.TEXT,
            large=False):
        pad = (0 if not self._rows else self._gap, 0)
        holder = tk.Frame(self, background=self._bg)
        holder.pack(fill="x", pady=pad, anchor="w")
        tk.Label(holder, text=label, font=t.FONTS.label, foreground=t.TEXT_2,
                 background=self._bg, anchor="w").pack(fill="x")
        value_label = tk.Label(
            holder, text=value, background=self._bg, foreground=colour,
            font=((t.FONTS.mono_lg if large else t.FONTS.mono) if mono
                  else t.FONTS.body),
            anchor="w", justify="left", wraplength=wrap or 0)
        value_label.pack(fill="x", pady=(t.XS, 0))
        self._rows += 1
        return value_label


class KeyValueGrid(tk.Frame):
    """Two-column definition list used inside panels."""

    def __init__(self, parent, background=t.SURFACE_1, key_width=18):
        super().__init__(parent, background=background)
        self._bg = background
        self._key_width = key_width
        self.columnconfigure(1, weight=1)
        self._row = 0

    def add(self, key, value, mono=True, colour=t.TEXT, value_font=None):
        tk.Label(self, text=key, font=t.FONTS.label, foreground=t.TEXT_2,
                 background=self._bg, anchor="w", width=self._key_width).grid(
            row=self._row, column=0, sticky="w", pady=t.XS)
        label = tk.Label(self, text=value, background=self._bg, foreground=colour,
                         font=value_font or (t.FONTS.mono if mono else t.FONTS.body),
                         anchor="w", justify="left")
        label.grid(row=self._row, column=1, sticky="w", pady=t.XS, padx=(t.MD, 0))
        self._row += 1
        return label


class StatGrid(Panel):
    """Four cells divided by hairlines. The progress screen's readout."""

    def __init__(self, parent):
        super().__init__(parent, padding=0)
        self.cells = {}
        grid = tk.Frame(self.inner, background=t.SURFACE_1)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(2, weight=1)
        self._grid = grid

    def build(self, cells):
        """cells: list of four (key, label) pairs, laid out 2x2."""
        for index, (key, label) in enumerate(cells):
            row, column = divmod(index, 2)
            holder = tk.Frame(self._grid, background=t.SURFACE_1)
            holder.grid(row=row * 2, column=column * 2, sticky="nsew",
                        padx=t.XL, pady=t.LG)
            tk.Label(holder, text=t.micro(label), font=t.FONTS.micro,
                     foreground=t.TEXT_3, background=t.SURFACE_1,
                     anchor="w").pack(fill="x")
            value = tk.Label(holder, text="—", font=t.FONTS.mono_big,
                             foreground=t.TEXT, background=t.SURFACE_1,
                             anchor="w")
            value.pack(fill="x", pady=(t.SM, 0))
            self.cells[key] = value
        # Dividers between the columns and between the rows.
        divider = tk.Frame(self._grid, background=t.BORDER, width=1)
        divider.grid(row=0, column=1, rowspan=3, sticky="ns")
        rule = tk.Frame(self._grid, background=t.BORDER, height=1)
        rule.grid(row=1, column=0, columnspan=3, sticky="ew")

    def set(self, key, value, colour=t.TEXT):
        self.cells[key].configure(text=value, foreground=colour)


class AttentionStrip(tk.Frame):
    """Tinted strip with a solid left edge. Used for the large-ZIP warning."""

    def __init__(self, parent, text, tint=t.TINT_ATTENTION, edge=t.ATTENTION,
                 fg=t.ATTENTION):
        super().__init__(parent, background=tint)
        tk.Frame(self, background=edge, width=3).pack(side="left", fill="y")
        tk.Label(self, text=text, font=t.FONTS.body, foreground=fg,
                 background=tint, anchor="w", justify="left",
                 wraplength=700).pack(side="left", fill="x", expand=True,
                                      padx=t.MD, pady=t.MD)


class Table(tk.Frame):
    """Treeview in a bordered panel, with a scrollbar that appears when needed."""

    def __init__(self, parent, columns, widths, height=8, anchors=None,
                 monospace=()):
        super().__init__(parent, background=t.BORDER)
        body = tk.Frame(self, background=t.SURFACE_1)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        self.tree = ttk.Treeview(body, columns=columns, show="headings",
                                 height=height, selectmode="browse")
        for name, width in zip(columns, widths):
            anchor = (anchors or {}).get(name, "w")
            self.tree.heading(name, text=t.micro(name), anchor=anchor)
            self.tree.column(name, width=width, anchor=anchor,
                             stretch=(name == columns[-1]))
        self.tree.tag_configure("mono", font=t.FONTS.mono)
        self.tree.tag_configure("odd", background=t.SURFACE_1)
        self.tree.tag_configure("even", background=t.blend(t.SURFACE_1, t.BG, 0.4))

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._rows = 0
        self._mono = monospace

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._rows = 0

    def add(self, values, tags=()):
        stripe = "even" if self._rows % 2 else "odd"
        self.tree.insert("", "end", values=values,
                         tags=(stripe, "mono" if self._mono else "", *tags))
        self._rows += 1

    @property
    def selection(self):
        chosen = self.tree.selection()
        return self.tree.item(chosen[0], "values") if chosen else None


class StepRail(tk.Frame):
    """Numbered steps. Its job is to make the Review gate visibly unskippable."""

    STEPS = ("Profile", "Upload", "Review", "Generate")

    def __init__(self, parent, background=t.BG):
        super().__init__(parent, background=background)
        self._bg = background
        self._tiles = []
        self._labels = []
        holder = tk.Frame(self, background=background)
        holder.pack(expand=True)
        for index, name in enumerate(self.STEPS):
            if index:
                tk.Frame(holder, background=t.BORDER, width=48, height=1).pack(
                    side="left", padx=t.MD)
            cell = tk.Frame(holder, background=background)
            cell.pack(side="left")
            tile = tk.Label(cell, text=str(index + 1), width=2, height=1,
                            font=t.FONTS.micro, background=t.SURFACE_2,
                            foreground=t.TEXT_3)
            tile.pack(side="left")
            label = tk.Label(cell, text=name, font=t.FONTS.body,
                             background=background, foreground=t.TEXT_3)
            label.pack(side="left", padx=(t.SM, 0))
            self._tiles.append(tile)
            self._labels.append(label)

    def set_current(self, step):
        """``step`` is 1-based; 0 hides the rail's emphasis entirely."""
        for index, (tile, label) in enumerate(zip(self._tiles, self._labels),
                                              start=1):
            if index < step:
                tile.configure(text="✓", background=t.TINT_SUCCESS,
                               foreground=t.SUCCESS)
                label.configure(foreground=t.TEXT_2)
            elif index == step:
                tile.configure(text=str(index), background=t.ACCENT,
                               foreground=t.ON_ACCENT)
                label.configure(foreground=t.TEXT)
            else:
                tile.configure(text=str(index), background=t.SURFACE_2,
                               foreground=t.TEXT_3)
                label.configure(foreground=t.TEXT_3)


class DropZone(tk.Frame):
    """Dashed-border file chooser. Tk cannot dash a frame, so it is a canvas."""

    def __init__(self, parent, on_choose, height=110):
        super().__init__(parent, background=t.BG, height=height)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, background=t.SURFACE_1, bd=0,
                                highlightthickness=0, height=height)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self._draw())
        self._on_choose = on_choose

        self.overlay = tk.Frame(self.canvas, background=t.SURFACE_1)
        tk.Label(self.overlay, text="Drop a CSV here", font=t.FONTS.body,
                 foreground=t.TEXT_2, background=t.SURFACE_1).pack()
        ttk.Button(self.overlay, text="or choose a file",
                   style="Tertiary.TButton",
                   command=on_choose).pack(pady=(t.XS, 0))
        self.canvas.create_window(0, 0, window=self.overlay, tags="overlay")

    def _draw(self):
        self.canvas.delete("frame")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.create_rectangle(1, 1, width - 1, height - 1, dash=(4, 4),
                                     outline=t.BORDER, tags="frame")
        self.canvas.coords("overlay", width // 2, height // 2)


class Stepper(tk.Frame):
    """A labelled value with minus and plus buttons.

    Used to tune the printed text before committing to a batch. Deliberately
    not a slider: the values are small integers and a support user wants to
    land on one exactly, not hunt for it.
    """

    def __init__(self, parent, label, value, on_change, step=1, low=None,
                 high=None, fmt=str, background=t.BG):
        super().__init__(parent, background=background)
        self.value = value
        self.step, self.low, self.high = step, low, high
        self.fmt, self.on_change = fmt, on_change

        tk.Label(self, text=label, font=t.FONTS.label, foreground=t.TEXT_2,
                 background=background, width=12, anchor="w").pack(side="left")
        self.minus = ttk.Button(self, text="−", width=2, style="Step.TButton",
                                command=lambda: self.bump(-step))
        self.minus.pack(side="left")
        self.readout = tk.Label(self, text=fmt(value), font=t.FONTS.mono,
                                foreground=t.TEXT, background=background,
                                width=8)
        self.readout.pack(side="left", padx=t.XS)
        self.plus = ttk.Button(self, text="+", width=2, style="Step.TButton",
                               command=lambda: self.bump(step))
        self.plus.pack(side="left")

    def bump(self, delta):
        new = self.value + delta
        if self.low is not None and new < self.low:
            return
        if self.high is not None and new > self.high:
            return
        self.value = new
        self.readout.configure(text=self.fmt(new))
        self._limits()
        self.on_change(new)

    def set(self, value):
        self.value = value
        self.readout.configure(text=self.fmt(value))
        self._limits()

    def _limits(self):
        self.minus.configure(
            state="disabled" if self.low is not None and
            self.value - self.step < self.low else "normal")
        self.plus.configure(
            state="disabled" if self.high is not None and
            self.value + self.step > self.high else "normal")
