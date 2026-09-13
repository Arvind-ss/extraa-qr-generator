"""The way in.

Two screens live here. :class:`WelcomeScreen` is what v1 shows: no accounts, no
passwords, one button. :class:`LoginScreen` is the real thing, kept intact and
still tested, waiting on the login service being ready for v2.

Set ``EXTRAA_QR_REQUIRE_LOGIN=1`` to switch to it. Nothing else changes -- the
role machinery, the providers, and the token plumbing are all still in place.
"""

import os

import tkinter as tk
from tkinter import ttk

from qrgen import auth
from ui import theme as t
from ui import widgets as w
from ui.app import APP_NAME, Screen


REQUIRE_LOGIN = bool(os.environ.get("EXTRAA_QR_REQUIRE_LOGIN"))

# Who is using the application when nobody signs in. Admin so that nothing is
# hidden; it grants no real authority, because writing a profile still needs
# credentials the app does not carry.
LOCAL_USER = auth.User(email="local", name="Support", role=auth.ADMIN)


class WelcomeScreen(Screen):
    """No login in v1: state what the tool is, then get out of the way."""

    chrome = False

    def build(self):
        band = t.GradientBand(self, height=int(self.app.HEIGHT * 0.45))
        band.place(relx=0, rely=0, relwidth=1, relheight=0.45)

        panel = w.Panel(self, padding=t.HUGE)
        panel.place(relx=0.5, rely=0.5, anchor="center", width=440)

        body = panel.inner
        tk.Label(body, text=APP_NAME, font=t.FONTS.display, foreground=t.TEXT,
                 background=t.SURFACE_1, anchor="w").pack(fill="x")
        tk.Label(body, text="Generate batches of QR cards from a CSV file.",
                 font=t.FONTS.body, foreground=t.TEXT_2,
                 background=t.SURFACE_1, anchor="w", justify="left",
                 wraplength=340).pack(fill="x", pady=(t.SM, t.XL))

        for line in ("Choose a profile and upload a CSV",
                     "Check a sample card before anything is generated",
                     "Download every card as a single ZIP"):
            row = tk.Frame(body, background=t.SURFACE_1)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="—", font=t.FONTS.body, foreground=t.TEXT_3,
                     background=t.SURFACE_1).pack(side="left", padx=(0, t.SM))
            tk.Label(row, text=line, font=t.FONTS.body, foreground=t.TEXT_2,
                     background=t.SURFACE_1, anchor="w").pack(side="left")

        button = ttk.Button(body, text="Get started", style="Primary.TButton",
                            command=self.start)
        button.pack(fill="x", pady=(t.XL, 0))
        button.focus_set()
        self.bind_all("<Return>", lambda _: self.start())

    def start(self):
        self.unbind_all("<Return>")
        self.app.sign_in(LOCAL_USER)


class LoginScreen(Screen):
    chrome = False

    def build(self):
        self.provider = auth.default_provider()
        # The gradient is strongest here: it is the only screen with no content
        # above the fold to carry the eye.
        band = t.GradientBand(self, height=int(self.app.HEIGHT * 0.45))
        band.place(relx=0, rely=0, relwidth=1, relheight=0.45)

        panel = w.Panel(self, padding=t.HUGE)
        panel.place(relx=0.5, rely=0.5, anchor="center", width=380)

        body = panel.inner
        tk.Label(body, text=APP_NAME, font=t.FONTS.display,
                 foreground=t.TEXT, background=t.SURFACE_1,
                 anchor="w").pack(fill="x")
        tk.Label(body, text="Internal QR generation tool", font=t.FONTS.caption,
                 foreground=t.TEXT_2, background=t.SURFACE_1,
                 anchor="w").pack(fill="x", pady=(t.XS, t.XL))

        self.email = w.Field(body, self.provider.username_label)
        self.email.pack(fill="x", pady=(0, t.MD))
        self.password = w.Field(body, "Password", show="•")
        self.password.pack(fill="x")

        self.error = tk.Label(body, text="", font=t.FONTS.caption,
                              foreground=t.ERROR, background=t.SURFACE_1,
                              anchor="w")

        ttk.Button(body, text="Sign in", style="Primary.TButton",
                   command=self.submit).pack(fill="x", pady=(t.XL, 0))

        self.email.entry.focus_set()
        for field in (self.email, self.password):
            field.entry.bind("<Return>", lambda _: self.submit())

    def submit(self):
        self.error.pack_forget()
        self.email.clear_error()
        self.password.clear_error()
        try:
            user = self.provider.authenticate(
                self.email.get(), self.password.get())
        except auth.AuthError as exc:
            # Both fields marked, one message: never reveal which half was wrong.
            self.email.entry.configure(style="Invalid.TEntry")
            self.password.entry.configure(style="Invalid.TEntry")
            self.error.configure(text=f"✗ {str(exc).capitalize()}")
            self.error.pack(fill="x", pady=(t.MD, 0))
            return
        self.app.sign_in(user)
