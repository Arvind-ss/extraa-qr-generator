"""Where the application is told how to reach the shared profile store.

This screen exists because the alternative was asking support staff to set
environment variables before double-clicking an application. Without it a
packaged build silently falls back to the profiles baked into the bundle and
looks like it is working.
"""

import tkinter as tk
from tkinter import ttk

from qrgen import config as app_config
from qrgen.store import ProfileStore
from qrgen.store.hasura import TABLE, HasuraStore, StoreError
from ui import theme as t
from ui import widgets as w
from ui.app import Screen


class SettingsScreen(Screen):
    step = 0

    def build(self):
        self.settings = app_config.load()
        column = tk.Frame(self, background=t.BG)
        column.place(relx=0.5, rely=0, anchor="n", relheight=1, width=720)
        body = tk.Frame(column, background=t.BG)
        body.pack(fill="both", expand=True, pady=t.XL)

        tk.Label(body, text="Settings", font=t.FONTS.heading, foreground=t.TEXT,
                 background=t.BG, anchor="w").pack(fill="x", pady=(0, t.MD))
        tk.Label(body,
                 text="Where profiles are shared from. Leave empty to use the "
                      "profiles built into this application.",
                 font=t.FONTS.caption, foreground=t.TEXT_2, background=t.BG,
                 anchor="w", justify="left",
                 wraplength=680).pack(fill="x", pady=(0, t.XL))

        self.fields = {}
        self.fields["api_url"] = self._field(
            body, "Profile API address", self.settings.get("api_url"))
        self.fields["token"] = self._field(
            body, "Access token", self.settings.get("token"), secret=True)

        w.hairline(body).pack(fill="x", pady=t.XL)
        tk.Label(body, text=t.micro("Administrators only"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.MD))
        self.fields["admin_secret"] = self._field(
            body, "Admin secret — needed only to edit profiles",
            self.settings.get("admin_secret"), secret=True)

        row = tk.Frame(body, background=t.BG)
        row.pack(fill="x", pady=(t.XL, 0))
        ttk.Button(row, text="Test connection", style="Secondary.TButton",
                   command=self.test).pack(side="left")
        self.result = tk.Label(row, text="", font=t.FONTS.body,
                               foreground=t.TEXT_2, background=t.BG,
                               anchor="w", justify="left", wraplength=460)
        self.result.pack(side="left", padx=t.MD)

        self.note = tk.Label(
            body,
            text=f"Saved to {app_config.config_path()}, readable only by you.\n"
                 f"Table: {TABLE}. A value set by an environment variable wins "
                 f"and is not written here.",
            font=t.FONTS.caption, foreground=t.TEXT_3, background=t.BG,
            anchor="w", justify="left")
        self.note.pack(fill="x", side="bottom")

    def _field(self, parent, label, value, secret=False):
        field = w.Field(parent, label, background=t.BG, mono=True,
                        show="•" if secret else None)
        field.configure(background=t.BG)
        field.pack(fill="x", pady=(0, t.MD))
        field.set(value or "")
        return field

    def _current(self):
        return {key: field.get().strip() for key, field in self.fields.items()}

    def test(self):
        """Ask the store, as a support user would and then as an admin."""
        values = self._current()
        if not values["api_url"]:
            self.result.configure(
                text="No address set — the built-in profiles will be used.",
                foreground=t.TEXT_2)
            return

        self.result.configure(text="Checking…", foreground=t.TEXT_2)

        def work():
            remote = HasuraStore(values["api_url"], token=values["token"] or None)
            found = remote.list()
            writable = None
            if values["admin_secret"]:
                admin = HasuraStore(values["api_url"],
                                    admin_secret=values["admin_secret"])
                admin.list()
                writable = True
            return len(found), writable

        def done(outcome):
            count, writable = outcome
            text = f"✓ Connected — {count} profile(s) available"
            if writable:
                text += ", and the admin secret works"
            self.result.configure(text=text, foreground=t.SUCCESS)

        def failed(exc):
            self.result.configure(text=f"✗ {exc}", foreground=t.ERROR)

        self.app.run_async(work, done, failed)

    def actions(self):
        return [("Back", "tertiary", self.back, True),
                ("Save", "primary", self.save, True)]

    def back(self):
        from ui.screens.home import DashboardScreen
        self.app.show(DashboardScreen)

    def save(self):
        try:
            app_config.save(self._current())
        except OSError as exc:
            self.result.configure(text=f"✗ could not save: {exc}",
                                  foreground=t.ERROR)
            return
        # Rebuild the store so the new address is used straight away.
        self.app.store = ProfileStore(user=self.app.user)
        self.back()
