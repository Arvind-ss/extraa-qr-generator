"""Dashboard."""

import tkinter as tk

from ui import theme as t
from ui import widgets as w
from ui.app import Screen


class Tile(w.Panel):
    def __init__(self, parent, title, caption, command, enabled=True):
        super().__init__(parent, padding=t.XL)
        self.command = command if enabled else None
        self.enabled = enabled
        colour = t.TEXT if enabled else t.TEXT_3

        tk.Label(self.inner, text=title, font=t.FONTS.heading, foreground=colour,
                 background=t.SURFACE_1, anchor="w").pack(fill="x")
        tk.Label(self.inner, text=caption, font=t.FONTS.caption,
                 foreground=t.TEXT_2 if enabled else t.TEXT_3,
                 background=t.SURFACE_1, anchor="w", justify="left",
                 wraplength=300).pack(fill="x", pady=(t.SM, 0))
        tk.Label(self.inner, text="›" if enabled else "", font=t.FONTS.heading,
                 foreground=t.TEXT_2, background=t.SURFACE_1,
                 anchor="e").pack(side="bottom", fill="x")

        if enabled:
            for widget in self._descendants():
                widget.bind("<Button-1>", lambda _: self.command())
                widget.configure(cursor="pointinghand")
            self.bind("<Enter>", self._enter)
            self.bind("<Leave>", self._leave)

    def _descendants(self):
        found = [self, self.body, self.inner]
        found.extend(self.inner.winfo_children())
        return found

    def _fill(self, colour, border):
        self.set_border(border)
        for widget in self._descendants():
            if widget is not self:
                widget.configure(background=colour)

    def _enter(self, _):
        self._fill(t.SURFACE_2, t.BORDER_STRONG)

    def _leave(self, _):
        self._fill(t.SURFACE_1, t.BORDER)


class DashboardScreen(Screen):
    step = 0

    def build(self):
        holder = tk.Frame(self, background=t.BG)
        holder.place(relx=0.5, rely=0.42, anchor="center")

        generate = Tile(holder, "Generate QR codes",
                        "Upload a CSV and produce a batch of cards",
                        self.app.restart_wizard)
        generate.pack(side="left", padx=(0, t.XL))
        generate.configure(width=360, height=180)
        generate.pack_propagate(False)

        allowed = self.app.user.can("profile.edit")
        profiles = Tile(holder, "Profile management",
                        "Create and edit generation profiles"
                        if allowed else "Admin access required",
                        self.open_profiles, enabled=allowed)
        profiles.pack(side="left")
        profiles.configure(width=360, height=180)
        profiles.pack_propagate(False)

    def open_profiles(self):
        from ui.screens.profiles import ProfileListScreen
        self.app.show(ProfileListScreen)
