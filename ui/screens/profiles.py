"""Profile management and the profile editor. Admin only.

The screens hide controls a support user may not use, but that is a courtesy —
:mod:`qrgen.store` refuses the write regardless of what the UI shows.
"""

import tkinter as tk
from tkinter import ttk

from qrgen import auth, profiles as profile_model
from qrgen.store.hasura import StoreError
from ui import theme as t
from ui import widgets as w
from ui.app import Screen


class ProfileListScreen(Screen):
    step = 0

    def build(self):
        column = tk.Frame(self, background=t.BG)
        column.place(relx=0.5, rely=0, anchor="n", relheight=1, width=940)
        body = tk.Frame(column, background=t.BG)
        body.pack(fill="both", expand=True, pady=t.XL)

        header = tk.Frame(body, background=t.BG)
        header.pack(fill="x", pady=(0, t.MD))
        tk.Label(header, text="Profiles", font=t.FONTS.heading,
                 foreground=t.TEXT, background=t.BG).pack(side="left")

        self.search = ttk.Entry(header, font=t.FONTS.body, width=24)
        self.search.pack(side="right", padx=(t.MD, 0), ipady=2)
        self.search.bind("<KeyRelease>", lambda _: self.render())
        if self.app.store.writable:
            ttk.Button(header, text="New profile", style="Primary.TButton",
                       command=self.create).pack(side="right")

        self.table = w.Table(body, ("Profile", "Renderer", "Version", "Status",
                                    "Updated"),
                             (260, 130, 90, 110, 300), height=10)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<<TreeviewSelect>>",
                             lambda _: self.app.rebuild_actions())
        self.table.tree.tag_configure("active", foreground=t.SUCCESS)
        self.table.tree.tag_configure("inactive", foreground=t.TEXT_3)

        self.empty = tk.Label(body, text="No profiles yet", font=t.FONTS.body,
                              foreground=t.TEXT_2, background=t.BG)
        self.render()

    def reload(self):
        self.render()

    def render(self):
        term = self.search.get().strip().lower() if hasattr(self, "search") else ""
        self.profiles = [p for p in self.app.store.list(include_inactive=True)
                         if term in p.name.lower()]
        self.app.refresh_status()
        self.table.clear()
        for profile in self.profiles:
            self.table.add(
                (profile.name, profile.renderer, f"v{profile.version}",
                 "Active" if profile.active else "Inactive", "—"),
                tags=("active" if profile.active else "inactive",))
        if not self.profiles:
            self.empty.pack(pady=t.XXL)
        else:
            self.empty.pack_forget()

    @property
    def selected(self):
        chosen = self.table.selection
        if not chosen:
            return None
        for profile in self.profiles:
            if profile.name == chosen[0]:
                return profile
        return None

    def actions(self):
        has = self.selected is not None
        writable = self.app.store.writable
        # No Delete anywhere: a batch generated last year must stay explicable.
        return [("Back", "tertiary", self.back, True),
                ("Preview", "secondary", self.preview, has),
                ("Deactivate", "secondary", self.deactivate,
                 has and writable and self.selected.active),
                ("Edit", "secondary", self.edit, has and writable)]

    def back(self):
        from ui.screens.home import DashboardScreen
        self.app.show(DashboardScreen)

    def create(self):
        self.app.show(ProfileEditorScreen, profile=None)

    def edit(self):
        self.app.show(ProfileEditorScreen, profile=self.selected)

    def preview(self):
        self.app.show(ProfileEditorScreen, profile=self.selected, readonly=True)

    def deactivate(self):
        profile = self.selected
        try:
            self.app.store.deactivate(profile.id, self.app.user)
        except (StoreError, auth.PermissionDenied) as exc:
            self.empty.configure(text=f"✗ {exc}", foreground=t.ERROR)
            self.empty.pack(pady=t.MD)
            return
        self.render()


class ProfileEditorScreen(Screen):
    step = 0

    def __init__(self, app, profile=None, readonly=False):
        super().__init__(app)
        self.profile = profile
        # Read-only when explicitly asked, or whenever the role cannot edit.
        self.readonly = readonly or not app.user.can("profile.edit")

    def build(self):
        column = tk.Frame(self, background=t.BG)
        column.place(relx=0.5, rely=0, anchor="n", relheight=1, width=940)
        body = tk.Frame(column, background=t.BG)
        body.pack(fill="both", expand=True, pady=t.XL)

        tk.Label(body, text="Edit profile" if self.profile else "New profile",
                 font=t.FONTS.heading, foreground=t.TEXT, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.XL))

        split = tk.Frame(body, background=t.BG)
        split.pack(fill="both", expand=True)

        form = tk.Frame(split, background=t.BG)
        form.pack(side="left", fill="both", expand=True, padx=(0, t.XXL))

        tk.Label(form, text=t.micro("Identity"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.MD))

        self.fields = {}
        self.fields["name"] = self._field(form, "Profile name")
        self.fields["required_columns"] = self._field(
            form, "Required input columns (comma separated)", mono=True)

        w.hairline(form).pack(fill="x", pady=t.XXL)

        tk.Label(form, text=t.micro("Templates"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.MD))

        for key, label in (("qr_content", "QR content template"),
                           ("top_text", "Top text template"),
                           ("bottom_text", "Bottom text template"),
                           ("filename", "Filename template")):
            self.fields[key] = self._field(form, label, mono=True)

        self.helper = w.Panel(split, padding=t.LG)
        self.helper.pack(side="left", anchor="n")
        self.helper.configure(width=240)
        self._render_helper()

        self.message = tk.Label(body, text="", font=t.FONTS.caption,
                                foreground=t.ERROR, background=t.BG, anchor="w")
        self.message.pack(fill="x", pady=(t.MD, 0))

        self._load()
        if self.readonly:
            for field in self.fields.values():
                field.readonly()
            tk.Label(body, text="Read-only · admin access required to edit",
                     font=t.FONTS.caption, foreground=t.TEXT_3,
                     background=t.BG, anchor="w").pack(fill="x")

    def _field(self, parent, label, mono=False):
        field = w.Field(parent, label, background=t.BG, mono=mono)
        field.configure(background=t.BG)
        field.pack(fill="x", pady=(0, t.MD))
        return field

    def _render_helper(self):
        inner = self.helper.inner
        tk.Label(inner, text=t.micro("Available variables"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.SURFACE_1,
                 anchor="w").pack(fill="x", pady=(0, t.MD))
        columns = self._columns() or ["name", "qr_code"]
        for column in columns:
            w.Tag(inner, "{%s}" % column, fg=t.ACCENT, bg=t.TINT_ACCENT,
                  font=t.FONTS.mono_small).pack(anchor="w", pady=2)
        tk.Label(inner,
                 text="Only these variables are allowed.\n"
                      "Templates cannot contain code.",
                 font=t.FONTS.caption, foreground=t.TEXT_2,
                 background=t.SURFACE_1, anchor="w", justify="left",
                 wraplength=200).pack(fill="x", pady=(t.MD, 0))

    def _columns(self):
        raw = self.fields["required_columns"].get() if self.fields else ""
        return [c.strip() for c in raw.split(",") if c.strip()]

    def _load(self):
        profile = self.profile
        if profile is None:
            self.fields["required_columns"].set("name, qr_code")
            self.fields["filename"].set("{qr_code}.png")
            return
        self.fields["name"].set(profile.name)
        self.fields["required_columns"].set(", ".join(profile.required_columns))
        self.fields["qr_content"].set(profile.qr_content)
        self.fields["top_text"].set(profile.top_text or "")
        self.fields["bottom_text"].set(profile.bottom_text)
        self.fields["filename"].set(profile.filename)

    def actions(self):
        if self.readonly:
            return [("Back", "secondary", self.back, True)]
        return [("Cancel", "secondary", self.back, True),
                ("Save profile", "primary", self.save, True)]

    def back(self):
        self.app.show(ProfileListScreen)

    def save(self):
        for field in self.fields.values():
            field.clear_error()
        self.message.configure(text="")

        name = self.fields["name"].get().strip()
        record = {
            "id": self.profile.id if self.profile else _slug(name),
            "name": name,
            "renderer": self.profile.renderer if self.profile else "standard",
            "required_columns": self._columns(),
            "qr_content": self.fields["qr_content"].get().strip(),
            "top_text": self.fields["top_text"].get().strip() or None,
            "bottom_text": self.fields["bottom_text"].get().strip(),
            "filename": self.fields["filename"].get().strip(),
            "output_format": self.profile.output_format if self.profile
            else "jpeg",
            "unique_columns": list(self.profile.unique_columns) if self.profile
            else [],
            "validation": dict(self.profile.validation) if self.profile else {},
            "active": self.profile.active if self.profile else True,
        }

        # Validated here only to place the error next to the right field; the
        # store validates again, and so does the database.
        try:
            profile_model.Profile.from_dict(record)
        except profile_model.ProfileError as exc:
            self._blame(str(exc))
            return

        try:
            self.app.store.save(record, self.app.user)
        except (StoreError, auth.PermissionDenied) as exc:
            self.message.configure(text=f"✗ {exc}")
            return
        self.app.show(ProfileListScreen)

    def _blame(self, message):
        """Attach an error to the field it is about, when we can tell."""
        for key in ("filename", "qr_content", "top_text", "bottom_text",
                    "required_columns", "name"):
            if key in message:
                self.fields[key].invalid(message)
                return
        self.message.configure(text=f"✗ {message}")


def _slug(name):
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower()) \
        .strip("_") or "profile"
