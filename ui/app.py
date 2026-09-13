"""Application shell: window, persistent chrome, and screen routing.

The UI holds no business logic. Every screen calls into :mod:`qrgen` and renders
what comes back; nothing here knows how a QR code is drawn or what a profile
means. Generation runs on a worker thread so the window stays responsive, and
progress arrives through a queue that Tk polls.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk

from qrgen import auth, engine
from qrgen.store import ProfileStore
from ui import theme as t
from ui import widgets as w

APP_NAME = "QR Generator"


class Job:
    """What the wizard has gathered so far. Reset when a new batch starts."""

    def __init__(self):
        self.profile = None
        self.input_path = None
        self.row_count = 0
        self.report = None
        self.report_for = None  # profile id the report belongs to
        self.samples = []
        self.style = None       # printed text settings for this batch
        self.result = None
        self.cancel = None


class Screen(ttk.Frame):
    """One screen. Subclasses build content and declare their action buttons."""

    step = 0            # 1..4 highlights the rail; 0 hides it
    chrome = True       # title strip + rail + action bar
    title = ""

    def __init__(self, app):
        super().__init__(app.content, style="TFrame")
        self.app = app

    def build(self):
        raise NotImplementedError

    def actions(self):
        """[(text, "primary"|"secondary"|"tertiary", command, enabled)]"""
        return []

    def on_leave(self):
        pass


class App(tk.Tk):
    WIDTH, HEIGHT = 1080, 720

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(960, 660)
        t.apply(self)

        self.user = None
        self.store = None
        self.job = Job()
        self.events = queue.Queue()
        self._screen = None

        self._build_chrome()
        engine.sweep_stale()

        self.show(self._entry_screen())

    @staticmethod
    def _entry_screen():
        """Welcome in v1, the real login once EXTRAA_QR_REQUIRE_LOGIN is set."""
        from ui.screens import auth as auth_screens
        return (auth_screens.LoginScreen if auth_screens.REQUIRE_LOGIN
                else auth_screens.WelcomeScreen)

    # --- chrome -------------------------------------------------------------

    def _build_chrome(self):
        # Everything in the header sits ON the gradient canvas rather than in
        # frames stacked over it -- an opaque frame across the band hides the
        # gradient completely, which is exactly what the first version did.
        self.band = t.GradientBand(self)
        self.band.pack(fill="x", side="top")
        self.band.pack_propagate(False)

        # Text drawn as a canvas item has no background of its own, so the
        # gradient shows through behind it.
        self._title_y = t.TITLE_HEIGHT // 2
        self.band.create_text(t.XL, self._title_y, anchor="w", tags="apptitle",
                              text=APP_NAME, font=t.FONTS.heading,
                              fill=t.TEXT)

        # Real widgets are opaque, so they are filled with the gradient's own
        # colour at their y position and the seam disappears.
        self.identity = tk.Frame(self.band, background=t.band_at(self._title_y))
        self.band.create_window(0, self._title_y, window=self.identity,
                                anchor="e", tags="identity")

        self._rail_y = t.TITLE_HEIGHT + t.RAIL_HEIGHT // 2
        self.rail_row = tk.Frame(self.band, background=t.band_at(self._rail_y))
        self.band.create_window(0, self._rail_y, window=self.rail_row,
                                anchor="center", tags="rail")
        self.rail = w.StepRail(self.rail_row, background=t.band_at(self._rail_y))
        self.rail.pack()

        self.band.bind("<Configure>", self._resize_strip, add="+")

        # Action bar pinned to the bottom, then content fills what is left.
        self.action_bar = tk.Frame(self, background=t.BG, height=t.ACTION_HEIGHT)
        self.action_bar.pack(side="bottom", fill="x")
        self.action_bar.pack_propagate(False)
        w.hairline(self.action_bar).pack(side="top", fill="x")

        self.status = w.StatusDot(self.action_bar)
        self.status.pack(side="left", padx=(t.XL, 0))
        # The only thing that re-reads the profile API. Shown on screens that
        # can redraw themselves; everything else works from what it fetched.
        self.refresh_button = ttk.Button(
            self.action_bar, text="Refresh", style="Tertiary.TButton",
            command=self.refresh_profiles)
        self.buttons = tk.Frame(self.action_bar, background=t.BG)
        self.buttons.pack(side="right", padx=t.XL)

        self.content = tk.Frame(self, background=t.BG)
        self.content.pack(fill="both", expand=True)

    def _resize_strip(self, event):
        self.band.coords("identity", event.width - t.XL, self._title_y)
        self.band.coords("rail", event.width // 2, self._rail_y)

    def _render_identity(self):
        for child in self.identity.winfo_children():
            child.destroy()
        from ui.screens import auth as auth_screens
        # Nobody signed in, so there is nobody to show and nowhere to sign out
        # to. The strip comes back with the login screen in v2.
        if not self.user or not auth_screens.REQUIRE_LOGIN:
            return
        tint = t.band_at(self._title_y)
        self.identity.configure(background=tint)
        ttk.Button(self.identity, text="Sign out",
                   style="HeaderTertiary.TButton",
                   command=self.sign_out).pack(side="right", padx=(t.MD, 0))
        w.Tag(self.identity, t.micro(self.user.role), fg=t.TEXT_2,
              bg=t.SURFACE_2).pack(side="right")
        tk.Label(self.identity, text=self.user.email, font=t.FONTS.caption,
                 foreground=t.TEXT_2, background=tint).pack(
            side="right", padx=(0, t.MD))

    def refresh_status(self):
        if not self.store:
            self.status.set("Profiles not loaded", t.TEXT_3)
            self.refresh_button.pack_forget()
            return
        colour = {"live": t.SUCCESS, "cached": t.ATTENTION,
                  "builtin": t.ATTENTION}.get(self.store.source, t.TEXT_3)
        self.status.set(self.store.status, colour)
        if hasattr(self._screen, "reload"):
            self.refresh_button.pack(side="left", padx=(t.SM, 0))
        else:
            self.refresh_button.pack_forget()

    def refresh_profiles(self):
        """Ask the store again, then let the screen redraw with what came back."""
        self.refresh_button.configure(state="disabled", text="Refreshing…")
        screen = self._screen

        def work():
            self.store.refresh()
            return self.store.source

        def done(_):
            self.refresh_button.configure(state="normal", text="Refresh")
            if screen is self._screen and screen.winfo_exists():
                screen.reload()
            self.refresh_status()

        def failed(exc):
            self.refresh_button.configure(state="normal", text="Refresh")
            self.status.set(f"Refresh failed: {exc}", t.ERROR)

        self.run_async(work, done, failed)

    # --- routing ------------------------------------------------------------

    def show(self, screen_class, **kwargs):
        if self._screen is not None:
            self._screen.on_leave()
            self._screen.destroy()

        self._screen = screen_class(self, **kwargs) if kwargs \
            else screen_class(self)
        chrome = self._screen.chrome and self.user is not None

        if chrome:
            self.band.configure(height=t.BAND_HEIGHT)
            self.band.pack(fill="x", side="top", before=self.content)
            self.band.itemconfigure("rail", state="normal")
            self.rail.set_current(self._screen.step)
            self.action_bar.pack(side="bottom", fill="x")
            self._render_identity()
        else:
            self.band.pack_forget()
            self.action_bar.pack_forget()

        if chrome and not self._screen.step:
            self.band.itemconfigure("rail", state="hidden")
            self.band.configure(height=t.TITLE_HEIGHT)

        self._screen.pack(fill="both", expand=True)
        self._screen.build()
        self._render_actions()
        self.refresh_status()

    def _render_actions(self):
        for child in self.buttons.winfo_children():
            child.destroy()
        for text, kind, command, enabled in self._screen.actions():
            style = {"primary": "Primary.TButton",
                     "secondary": "Secondary.TButton",
                     "tertiary": "Tertiary.TButton"}[kind]
            button = ttk.Button(self.buttons, text=text, style=style,
                                command=command,
                                state="normal" if enabled else "disabled")
            button.pack(side="left", padx=(t.MD, 0))
            # Never let Return fire the commit button by accident.
            button.configure(takefocus=kind != "primary")

    def rebuild_actions(self):
        self._render_actions()

    # --- session ------------------------------------------------------------

    def sign_in(self, user):
        self.user = user
        self.store = ProfileStore(user=user)
        self.job = Job()
        from ui.screens.home import DashboardScreen
        self.show(DashboardScreen)

    def sign_out(self):
        self.user = None
        self.store = None
        self.job = Job()
        self.show(self._entry_screen())

    # --- background work ----------------------------------------------------

    def run_async(self, work, on_done, on_error=None):
        """Run ``work`` off the UI thread and deliver the result back on it.

        Tk is not thread-safe: no widget may be touched from the worker. The
        result comes back through a queue that the main loop polls, so both
        callbacks run on the UI thread.
        """
        results = queue.Queue()
        # Whoever asked for this work. If the user has moved on by the time it
        # finishes, the result is stale and its callback would write into
        # destroyed widgets -- so it is dropped.
        owner = self._screen

        def runner():
            try:
                results.put(("ok", work()))
            except Exception as exc:  # delivered to on_error, never swallowed
                results.put(("error", exc))

        threading.Thread(target=runner, daemon=True).start()

        def poll():
            try:
                kind, payload = results.get_nowait()
            except queue.Empty:
                if owner is self._screen:
                    self.after(60, poll)
                return
            if owner is not self._screen or not owner.winfo_exists():
                return
            if kind == "ok":
                on_done(payload)
            elif on_error is not None:
                on_error(payload)
            else:
                raise payload

        self.after(60, poll)

    def restart_wizard(self):
        self.job = Job()
        from ui.screens.generate import GenerateScreen
        self.show(GenerateScreen)


def main():
    App().mainloop()
