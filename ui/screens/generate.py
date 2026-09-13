"""The generation wizard: choose, validate, review, generate, finish."""

import io
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from datetime import date
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from qrgen import engine, rows as rows_io
from ui import theme as t
from ui import widgets as w
from ui.app import Screen

MAX_ERRORS_SHOWN = 200      # a Treeview with thousands of rows freezes Tk
LARGE_ZIP_BYTES = 1_000_000_000


def reveal(path):
    """Show a file in the OS file manager. The app never opens it itself."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif os.name == "nt":
        subprocess.run(["explorer", "/select,", os.path.normpath(path)],
                       check=False)
    else:
        subprocess.run(["xdg-open", os.path.dirname(path)], check=False)


def open_file(path):
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    elif os.name == "nt":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.run(["xdg-open", path], check=False)


class GenerateScreen(Screen):
    """Steps 1 and 2: pick a profile, choose a file, see it validated."""

    step = 1

    def build(self):
        self.profiles = self.app.store.list()
        self.app.refresh_status()

        column = tk.Frame(self, background=t.BG, width=t.CONTENT_WIDTH)
        column.place(relx=0.5, rely=0, anchor="n", relheight=1,
                     width=t.CONTENT_WIDTH)
        body = tk.Frame(column, background=t.BG)
        body.pack(fill="both", expand=True, pady=t.XL)

        # --- profile
        tk.Label(body, text=t.micro("Profile"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x")

        names = [p.name for p in self.profiles]
        self.picker = ttk.Combobox(body, values=names, state="readonly",
                                   font=t.FONTS.body)
        self.picker.pack(fill="x", pady=(t.SM, t.MD), ipady=4)
        self.picker.bind("<<ComboboxSelected>>", lambda _: self.on_profile())

        self.summary = w.Panel(body, padding=t.MD)
        self.summary.pack(fill="x")
        self.summary_grid = w.KeyValueGrid(self.summary.inner)
        self.summary_grid.pack(fill="x")

        self._build_style_controls(body)
        w.hairline(body).pack(fill="x", pady=t.XL)

        # --- file
        tk.Label(body, text=t.micro("Input file"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.SM))

        self.file_holder = tk.Frame(body, background=t.BG)
        self.file_holder.pack(fill="x")
        self.drop = w.DropZone(self.file_holder, self.choose_file)
        self.drop.pack(fill="x")

        # --- validation
        self.validation = tk.Frame(body, background=t.BG)
        self.validation.pack(fill="both", expand=True, pady=(t.XL, 0))
        self.error_table = None

        if self.profiles:
            self.picker.set(self.app.job.profile.name if self.app.job.profile
                            else self.profiles[0].name)
            self.on_profile()
        else:
            self.summary_grid.add("No profiles available", "", mono=False,
                                  colour=t.TEXT_3)

        # Coming back from Review: restore the file and the verdict it already
        # has, rather than making someone pick the file again -- and rather
        # than re-reading 50,000 rows to reach the same answer.
        job = self.app.job
        if job.input_path:
            self.show_file(job.input_path)
            if job.report is not None:
                self.on_validated((job.report, os.path.getsize(job.input_path)))

    def _build_style_controls(self, parent):
        """Printed text size and spacing, set before the sample is rendered.

        One horizontal row on purpose: this screen already carries three
        sections and the window is only 720px tall.
        """
        job = self.app.job
        if not job.style:
            job.style = dict(job.profile.style) if job.profile else None

        holder = tk.Frame(parent, background=t.BG)
        holder.pack(fill="x", pady=(t.LG, 0))
        tk.Label(holder, text=t.micro("Printed text"), font=t.FONTS.micro,
                 foreground=t.TEXT_3, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.SM))

        row = tk.Frame(holder, background=t.BG)
        row.pack(fill="x")
        style = job.style or {"name_size": 48, "name_tracking": 5}

        self.size_step = w.Stepper(
            row, "Size", style["name_size"], self._set_size, step=2, low=12,
            high=160, fmt=lambda v: f"{v}/{engine.code_size_for(v)}")
        self.size_step.pack(side="left")

        self.track_step = w.Stepper(
            row, "Spacing", style["name_tracking"], self._set_tracking,
            step=1, low=-10, high=40, fmt=lambda v: f"{v} px")
        self.track_step.pack(side="left", padx=(t.XL, 0))

        ttk.Button(row, text="Reset", style="Tertiary.TButton",
                   command=self._reset_style).pack(side="left", padx=(t.MD, 0))

        self.style_note = tk.Label(holder, text="", font=t.FONTS.caption,
                                   foreground=t.TEXT_2, background=t.BG,
                                   anchor="w")
        self.style_note.pack(fill="x", pady=(t.XS, 0))
        self._style_note()

    def _set_size(self, value):
        self.app.job.style["name_size"] = value
        self.app.job.style["code_size"] = engine.code_size_for(value)
        self._style_note()

    def _set_tracking(self, value):
        self.app.job.style["name_tracking"] = value
        self._style_note()

    def _reset_style(self):
        self.app.job.style = dict(self.app.job.profile.style)
        self.size_step.set(self.app.job.style["name_size"])
        self.track_step.set(self.app.job.style["name_tracking"])
        self._style_note()

    def _style_note(self):
        job = self.app.job
        if not (job.style and job.profile):
            return
        changed = job.style != job.profile.style
        self.style_note.configure(
            text="Differs from the profile — applies to this batch only"
            if changed else "Matching the profile",
            foreground=t.ATTENTION if changed else t.TEXT_2)

    # --- profile ------------------------------------------------------------

    def on_profile(self):
        for child in self.summary_grid.winfo_children():
            child.destroy()
        self.summary_grid._row = 0
        profile = self.selected_profile
        self.app.job.profile = profile
        if profile is None:
            return
        self.summary_grid.add("Required columns",
                              ", ".join(profile.required_columns))
        self.summary_grid.add("QR content", profile.qr_content)
        self.summary_grid.add("Top text", profile.top_text or "—")
        self.summary_grid.add("Bottom text", profile.bottom_text)
        self.summary_grid.add("Filename", profile.filename)
        if self.app.job.style is None:
            self.app.job.style = dict(profile.style)
            if hasattr(self, "size_step"):
                self.size_step.set(profile.name_size)
                self.track_step.set(profile.name_tracking)
            self._style_note()
        # Only re-validate when the answer could have changed. Switching
        # profiles changes the rules; coming back from Review does not.
        job = self.app.job
        if job.input_path and job.report_for != profile.id:
            self.validate()

    @property
    def selected_profile(self):
        for profile in self.profiles:
            if profile.name == self.picker.get():
                return profile
        return None

    # --- file ---------------------------------------------------------------

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Choose a CSV or JSON file",
            filetypes=[("Data files", "*.csv *.json"), ("All files", "*.*")])
        if path:
            self.app.job.input_path = path
            self.show_file(path)
            self.validate()

    def show_file(self, path):
        for child in self.file_holder.winfo_children():
            child.destroy()
        panel = w.Panel(self.file_holder, padding=t.MD)
        panel.pack(fill="x")
        tk.Label(panel.inner, text=os.path.basename(path), font=t.FONTS.mono,
                 foreground=t.TEXT, background=t.SURFACE_1,
                 anchor="w").pack(side="left")
        ttk.Button(panel.inner, text="Replace", style="Tertiary.TButton",
                   command=self.choose_file).pack(side="right")
        self.file_caption = tk.Label(panel.inner, text="reading…",
                                     font=t.FONTS.caption, foreground=t.TEXT_2,
                                     background=t.SURFACE_1)
        self.file_caption.pack(side="right", padx=t.MD)

    # --- validation ---------------------------------------------------------

    def validate(self):
        profile, path = self.app.job.profile, self.app.job.input_path
        if not (profile and path):
            return
        self.render_validation(None)

        def work():
            report = engine.validate_input(profile, path)
            return report, os.path.getsize(path)

        self.app.run_async(work, self.on_validated, self.on_validation_error)

    def on_validated(self, payload):
        report, size = payload
        self.app.job.report = report
        self.app.job.report_for = (self.app.job.profile.id
                                   if self.app.job.profile else None)
        self.app.job.row_count = report.total
        self.file_caption.configure(
            text=f"{report.total:,} rows · {size / 1024:,.0f} KB")
        self.render_validation(report)
        self.app.rebuild_actions()

    def on_validation_error(self, exc):
        self.app.job.report = None
        self.app.job.report_for = None
        self.file_caption.configure(text="unreadable")
        self.render_validation(exc)
        self.app.rebuild_actions()

    def render_validation(self, report):
        for child in self.validation.winfo_children():
            child.destroy()
        self.error_table = None

        if report is None:
            tk.Label(self.validation, text="Validating…", font=t.FONTS.body,
                     foreground=t.TEXT_2, background=t.BG,
                     anchor="w").pack(fill="x")
            return

        if isinstance(report, Exception):
            tk.Label(self.validation, text=f"✗ {report}", font=t.FONTS.body,
                     foreground=t.ERROR, background=t.BG, anchor="w",
                     justify="left", wraplength=t.CONTENT_WIDTH).pack(fill="x")
            return

        if report.ok:
            tk.Label(self.validation, text=f"✓ {report.summary}",
                     font=t.FONTS.body, foreground=t.SUCCESS, background=t.BG,
                     anchor="w").pack(fill="x")
            return

        tk.Label(self.validation, text=f"✗ {report.summary}", font=t.FONTS.body,
                 foreground=t.ERROR, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.MD))

        if report.missing_columns:
            return

        self.error_table = w.Table(self.validation, ("Row", "QR code", "Error"),
                                   (70, 130, 560), height=6, monospace=True)
        self.error_table.pack(fill="both", expand=True)
        shown = report.errors[:MAX_ERRORS_SHOWN]
        for error in shown:
            self.error_table.add((error.row_number, error.qr_code, error.error))

        footer = tk.Frame(self.validation, background=t.BG)
        footer.pack(fill="x", pady=(t.SM, 0))
        tk.Label(footer,
                 text=f"Showing {len(shown):,} of {len(report.errors):,} errors",
                 font=t.FONTS.caption, foreground=t.TEXT_2,
                 background=t.BG).pack(side="left")
        ttk.Button(footer, text="Copy all", style="Tertiary.TButton",
                   command=lambda: self.copy_errors(report)).pack(side="right")

    def copy_errors(self, report):
        lines = ["row_number,qr_code,error"]
        lines += [f"{e.row_number},{e.qr_code},{e.error}" for e in report.errors]
        self.app.clipboard_clear()
        self.app.clipboard_append("\n".join(lines))

    # --- actions ------------------------------------------------------------

    def actions(self):
        report = self.app.job.report
        ready = bool(report is not None and not isinstance(report, Exception)
                     and report.ok and self.app.job.profile)
        return [("Back", "tertiary", self.back, True),
                ("Generate sample", "primary", self.make_sample, ready)]

    def back(self):
        from ui.screens.home import DashboardScreen
        self.app.show(DashboardScreen)

    def reload(self):
        """Redraw with whatever the store now holds.

        The file, its verdict and the printed-text settings all live on the
        job, so rebuilding the screen keeps them.
        """
        self.app.show(GenerateScreen)

    def make_sample(self):
        job = self.app.job

        def work():
            return engine.render_samples(job.profile, job.input_path,
                                         **(job.style or {}))

        self.app.run_async(work, self.on_samples, self.on_validation_error)

    def on_samples(self, samples):
        self.app.job.samples = samples
        self.app.show(ReviewScreen)


class ReviewScreen(Screen):
    """Step 3. The gate: nothing proceeds without an explicit approval here.

    The app makes no judgement about the cards -- it renders them and shows
    them. Checking is the support team's job, which is why the preview is big
    enough to scan off the screen and why more than one row is offered.
    """

    step = 3

    def build(self):
        job = self.app.job
        self.samples = job.samples
        self.selected = 0
        self._photos = []

        column = tk.Frame(self, background=t.BG)
        column.place(relx=0.5, rely=0, anchor="n", relheight=1, width=940)
        body = tk.Frame(column, background=t.BG)
        body.pack(fill="both", expand=True, pady=t.XL)

        self.left = tk.Frame(body, background=t.BG)
        self.left.pack(side="left", fill="both", expand=True, padx=(0, t.HUGE))
        # Its own frame: select() rebuilds the details on every row change and
        # every restyle, and must not take the style controls down with them.
        self.details_holder = tk.Frame(self.left, background=t.BG)
        self.details_holder.pack(fill="x", anchor="n")

        right = tk.Frame(body, background=t.BG)
        right.pack(side="left", anchor="n")

        well = tk.Frame(right, background=t.BORDER)
        well.pack()
        self.well = tk.Frame(well, background=t.PREVIEW_WELL, width=400,
                             height=400)
        self.well.pack(padx=1, pady=1)
        self.well.pack_propagate(False)
        self.image_label = tk.Label(self.well, background=t.PREVIEW_WELL, bd=0)
        self.image_label.pack(expand=True)

        if len(self.samples) > 1:
            self.strip = tk.Frame(right, background=t.BG)
            self.strip.pack(fill="x", pady=(t.MD, 0))
            self.chips = []
            for index, sample in enumerate(self.samples):
                chip = tk.Label(
                    self.strip, text=f"Row {sample.row_number:,}",
                    font=t.FONTS.caption, padx=t.MD, pady=6,
                    background=t.SURFACE_2, foreground=t.TEXT_2)
                chip.pack(side="left", padx=(0, t.SM))
                chip.bind("<Button-1>",
                          lambda _, i=index: self.select(i))
                chip.configure(cursor="pointinghand")
                self.chips.append(chip)

        ttk.Button(right, text="Open full size", style="Tertiary.TButton",
                   command=self.open_full).pack(anchor="w", pady=(t.SM, 0))

        self.select(0)

    def select(self, index):
        """Show one of the preview rows: swap the image and the details."""
        self.selected = index
        sample = self.samples[index]

        for position, chip in enumerate(getattr(self, "chips", [])):
            chosen = position == index
            chip.configure(background=t.TINT_ACCENT if chosen else t.SURFACE_2,
                           foreground=t.ACCENT if chosen else t.TEXT_2)

        # Pillow does the downscale: Tk's PhotoImage.subsample() is
        # integer-only and turns the QR modules to mush at 688 -> 360.
        image = Image.open(io.BytesIO(sample.image)).convert("RGB")
        image.thumbnail((360, 360), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self._photos.append(photo)          # Tk keeps no reference of its own
        self.image_label.configure(image=photo)

        for child in self.details_holder.winfo_children():
            child.destroy()
        details = w.DefinitionList(self.details_holder)
        details.pack(fill="x", anchor="n")
        details.add("Profile", self.app.job.profile.name)
        details.add("Row", f"{sample.row_number:,} of "
                           f"{self.app.job.row_count:,}")
        # The two values a person is actually checking against a spreadsheet.
        details.add("Name", sample.fields["top_text"] or "—", mono=True,
                    large=True)
        details.add("QR code", sample.fields["bottom_text"], mono=True,
                    large=True)
        details.add("Expected URL", sample.fields["qr_content"], mono=True,
                    wrap=340)
        details.add("Filename", sample.fields["filename"], mono=True)

        card = Image.open(io.BytesIO(sample.image))
        style = self.app.job.style or self.app.job.profile.style
        changed = style != self.app.job.profile.style
        details.add(
            "Printed text",
            f"size {style['name_size']}/{style['code_size']}   "
            f"spacing {style['name_tracking']}px   card {card.width}×{card.height}",
            mono=True, colour=t.ATTENTION if changed else t.TEXT)

    def open_full(self):
        sample = self.samples[self.selected]
        handle, path = tempfile.mkstemp(suffix=".png", prefix="extraa-sample-")
        with os.fdopen(handle, "wb") as fh:
            fh.write(sample.image)
        open_file(path)

    def actions(self):
        return [("Back", "tertiary", self.back, True),
                ("Regenerate", "secondary", self.regenerate, True),
                ("Approve & generate", "primary", self.approve, True)]

    def back(self):
        """Return to the upload step with everything intact.

        This is the loop the printed-text controls exist for: set a size, look
        at the card, come back and change it. Nothing is re-uploaded or
        re-validated.
        """
        self.app.show(GenerateScreen)

    def regenerate(self):
        job = self.app.job
        job.samples = engine.render_samples(job.profile, job.input_path,
                                            **job.style)
        self.app.show(ReviewScreen)

    def approve(self):
        job = self.app.job
        default = f"{job.profile.id}_{date.today().isoformat()}.zip"
        path = filedialog.asksaveasfilename(
            title="Save the ZIP as", defaultextension=".zip",
            initialfile=default, filetypes=[("ZIP archive", "*.zip")])
        if not path:
            return
        self.app.show(ProgressScreen, zip_path=path)


class ProgressScreen(Screen):
    """Step 4. Generation runs on a worker thread; Tk polls a queue."""

    step = 4

    def __init__(self, app, zip_path):
        super().__init__(app)
        self.zip_path = zip_path
        self.updates = queue.Queue()
        self.cancelled = threading.Event()
        self.started = None
        self.finished = False

    def build(self):
        column = tk.Frame(self, background=t.BG, width=620)
        column.place(relx=0.5, rely=0.34, anchor="center", width=620)

        tk.Label(column, text="Generating QR codes", font=t.FONTS.heading,
                 foreground=t.TEXT, background=t.BG,
                 anchor="w").pack(fill="x", pady=(0, t.XL))

        self.bar = t.GradientBar(column, height=8)
        self.bar.pack(fill="x")

        counters = tk.Frame(column, background=t.BG)
        counters.pack(fill="x", pady=(t.MD, t.XL))
        self.count = tk.Label(counters, text="0 / 0", font=t.FONTS.mono_big,
                              foreground=t.TEXT, background=t.BG)
        self.count.pack(side="left")
        self.percent = tk.Label(counters, text="0%", font=t.FONTS.body,
                                foreground=t.TEXT_2, background=t.BG)
        self.percent.pack(side="right")

        self.stats = w.StatGrid(column)
        self.stats.pack(fill="x")
        self.stats.build([("successful", "Successful"), ("remaining", "Remaining"),
                          ("failed", "Failed"), ("throughput", "Throughput")])

        self.note = tk.Label(column, text="Starting…", font=t.FONTS.caption,
                             foreground=t.TEXT_2, background=t.BG, anchor="w")
        self.note.pack(fill="x", pady=(t.MD, 0))

        self.start()

    def start(self):
        job = self.app.job
        self.started = time.time()

        def progress(done, total, successful, failed):
            self.updates.put((done, total, successful, failed))

        def work():
            return engine.generate_batch(
                job.profile, job.input_path, self.zip_path,
                on_progress=progress, should_cancel=self.cancelled.is_set,
                style=job.style)

        self.note.configure(
            text=f"Rendering with {engine.default_workers()} worker processes")
        self.app.run_async(work, self.on_done, self.on_error)
        self.after(100, self.drain)

    def drain(self):
        latest = None
        try:
            while True:
                latest = self.updates.get_nowait()
                # Keep only the newest: a 50,000-row job produces far more
                # updates than the screen can usefully draw.
        except queue.Empty:
            pass

        if latest:
            done, total, successful, failed = latest
            fraction = done / total if total else 0
            self.bar.set(fraction)
            self.count.configure(text=f"{done:,} / {total:,}")
            self.percent.configure(text=f"{fraction:.0%}")
            self.stats.set("successful", f"{successful:,}")
            self.stats.set("failed", f"{failed:,}",
                           t.ERROR if failed else t.TEXT)

            elapsed = time.time() - self.started
            rate = done / elapsed if elapsed > 0.5 and done else 0
            self.stats.set("throughput", f"{rate:,.0f} / sec" if rate else "—")
            remaining = (total - done) / rate if rate else 0
            self.stats.set("remaining", _duration(remaining) if rate else "—")

        if not self.finished:
            self.after(150, self.drain)

    def on_done(self, result):
        self.finished = True
        self.app.job.result = result
        if result.cancelled:
            from ui.screens.home import DashboardScreen
            self.app.show(DashboardScreen)
            return
        self.app.show(CompleteScreen)

    def on_error(self, exc):
        self.finished = True
        self.note.configure(text=f"✗ {exc}", foreground=t.ERROR)
        self.app.rebuild_actions()

    def actions(self):
        if self.finished:
            return [("Back", "secondary", self.app.restart_wizard, True)]
        return [("Cancel", "secondary", self.cancel, True)]

    def cancel(self):
        self.cancelled.set()
        self.note.configure(text="Cancelling — cleaning up temporary files…")

    def on_leave(self):
        # If the screen goes away for any reason, do not leave workers running.
        self.cancelled.set()
        self.finished = True


def _duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"~{seconds}s"
    return f"~{seconds // 60}m {seconds % 60:02d}s"


class CompleteScreen(Screen):
    step = 4

    def build(self):
        result = self.app.job.result
        column = tk.Frame(self, background=t.BG, width=620)
        column.place(relx=0.5, rely=0.34, anchor="center", width=620)

        tk.Label(column, text="✓", font=t.FONTS.glyph, foreground=t.SUCCESS,
                 background=t.BG, anchor="w").pack(fill="x")
        tk.Label(column, text="Generation complete", font=t.FONTS.display,
                 foreground=t.TEXT, background=t.BG,
                 anchor="w").pack(fill="x", pady=(t.SM, t.XL))

        panel = w.Panel(column, padding=t.XL)
        panel.pack(fill="x")
        grid = w.KeyValueGrid(panel.inner, key_width=14)
        grid.pack(fill="x")
        grid.add("Total", f"{result.total:,}")
        grid.add("Successful", f"{result.successful:,}")
        grid.add("Failed", f"{result.failed:,}",
                 colour=t.ERROR if result.failed else t.TEXT)
        grid.add("Time", _elapsed(result.seconds))
        size = os.path.getsize(result.zip_path) if result.zip_path else 0
        grid.add("Output", f"{os.path.basename(result.zip_path)}   "
                           f"{size / 1e9:.2f} GB" if size >= LARGE_ZIP_BYTES
                 else f"{os.path.basename(result.zip_path)}   "
                      f"{size / 1e6:.1f} MB")

        if size >= LARGE_ZIP_BYTES:
            w.AttentionStrip(
                column,
                f"! This archive is {size / 1e9:.2f} GB. "
                f"Allow time to copy or upload it.").pack(fill="x",
                                                         pady=(t.MD, 0))

    def actions(self):
        result = self.app.job.result
        buttons = [("New batch", "tertiary", self.app.restart_wizard, True)]
        if result.error_report:
            buttons.append(("Show error report", "secondary",
                            lambda: reveal(result.error_report), True))
        buttons.append(("Open ZIP", "primary",
                        lambda: reveal(result.zip_path), True))
        return buttons


def _elapsed(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"
