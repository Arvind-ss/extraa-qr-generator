"""Generation engine.

Callable with no UI present -- the CLI harness and the desktop app both go
through here, and neither passes anything but data.

Memory discipline: one image per worker exists at a time. Every card is written
to a per-job temporary directory and released; the ZIP is built by streaming
those files; the directory is deleted whether the job succeeded, failed, or was
cancelled. Peak RSS is flat in the batch size -- measured 38 MB for 10,000 rows.

Rendering is CPU-bound and Pillow holds the GIL, so the work is spread across
processes rather than threads.
"""

import csv
import multiprocessing
import os
import shutil
import tempfile
import time
import zipfile

from qrgen import rows as rows_io
from qrgen import validate
from qrgen.renderers.standard import code_size_for  # noqa: F401  (UI helper)

TEMP_ROOT = os.path.join(tempfile.gettempdir(), "extraa-qr")

# Values Excel would execute if a cell began with one of these.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Below this many rows, starting a pool costs more than it saves.
POOL_THRESHOLD = 200

# Rows handed to a worker at a time. Large enough that queue overhead vanishes
# against ~13ms of rendering, small enough that cancel stays responsive.
CHUNKSIZE = 25


def default_workers():
    """Leave one core for the UI and the rest of the machine."""
    return max(1, (os.cpu_count() or 2) - 1)


def can_spawn():
    """Whether worker processes can be started from this entry point.

    ``spawn`` re-imports ``__main__`` in each child, so a REPL, a ``python -``
    heredoc, or an ``exec``'d string has nothing importable to re-enter and the
    pool hangs forever. Falling back to one in-process pass is slower; hanging
    is not recoverable.
    """
    import sys
    main = sys.modules.get("__main__")
    return bool(getattr(main, "__file__", None))


# --- worker -----------------------------------------------------------------
# The profile and job settings are pushed into each worker once at startup
# rather than pickled alongside all 50,000 tasks.

_WORKER = {}


def _init_worker(profile, workdir, style=None):
    _WORKER["profile"] = profile
    _WORKER["workdir"] = workdir
    _WORKER["style"] = style or profile.style


def _render_one(task):
    """Render one row. Never raises -- a bad row must not kill the pool."""
    number, row = task
    profile = _WORKER["profile"]
    try:
        fields = profile.build(row)
        filename = validate.safe_filename(fields["filename"])
        image = profile.render(fields["qr_content"], fields["bottom_text"],
                               top_text=fields["top_text"], **_WORKER["style"])
        with open(os.path.join(_WORKER["workdir"], filename), "wb") as fh:
            fh.write(image)
        return number, None, None
    except Exception as exc:
        return number, str(row.get("qr_code", "")), f"{type(exc).__name__}: {exc}"


class Sample:
    """A rendered preview card shown for approval before the batch runs.

    The app does not decode or check the QR: support staff look at the image
    and scan it themselves if they want to. Approval is a human judgement.
    """

    def __init__(self, row_number, fields, image):
        self.row_number = row_number
        self.fields = fields          # qr_content, bottom_text, top_text, filename
        self.image = image            # encoded bytes


class BatchResult:
    def __init__(self, total, successful, failures, zip_path, error_report,
                 cancelled, seconds, workers=1):
        self.total = total
        self.successful = successful
        self.failures = failures
        self.zip_path = zip_path
        self.error_report = error_report
        self.cancelled = cancelled
        self.seconds = seconds
        self.workers = workers

    @property
    def failed(self):
        return len(self.failures)

    @property
    def summary(self):
        state = "cancelled" if self.cancelled else "complete"
        return (f"{state}: {self.successful} succeeded, {self.failed} failed "
                f"of {self.total} in {self.seconds:.1f}s "
                f"({self.workers} worker{'s' if self.workers != 1 else ''})")


def render_sample(profile, row, row_number=1, **style):
    """Render one row for review.

    ``style`` overrides the profile's printed text settings for this render
    only -- how the Review screen previews a size change before anyone commits
    to it. Anything omitted comes from the profile.
    """
    fields = profile.build(row)
    validate.safe_filename(fields["filename"])
    image = profile.render(fields["qr_content"], fields["bottom_text"],
                           top_text=fields["top_text"],
                           **{**profile.style, **style})
    return Sample(row_number, fields, image)


def first_row(input_path):
    for row in rows_io.read_rows(input_path):
        return row
    raise rows_io.InputError("input file has no data rows")


def preview_rows(input_path):
    """Rows 1, 2 and the last, as ``(row_number, row)``.

    Three rows rather than one because the failure that matters is usually not
    in the first record: a name long enough to wrap changes the card's height,
    and the last row is where a truncated export shows up. Reads the file once.
    """
    leading, last = [], None
    for number, row in enumerate(rows_io.read_rows(input_path), start=1):
        if number <= 2:
            leading.append((number, row))
        last = (number, row)
    if last and last[0] > 2:
        leading.append(last)
    return leading


def render_samples(profile, input_path, **style):
    return [render_sample(profile, row, number, **style)
            for number, row in preview_rows(input_path)]


def validate_input(profile, input_path):
    return validate.validate_rows(rows_io.read_rows(input_path), profile)


def generate_batch(profile, input_path, zip_path, on_progress=None,
                   should_cancel=None, error_report=None, workers=None,
                   style=None):
    """Generate every row into ``zip_path``.

    ``on_progress(done, total, successful, failed)`` is called periodically, not
    per row -- 50,000 callbacks would cost more than the rendering.
    ``should_cancel()`` is polled the same way; returning True aborts and cleans
    up.

    ``workers`` defaults to one fewer than the machine has cores, dropping to a
    single in-process pass for small inputs where spawning would cost more than
    it saves. ``style`` overrides the profile's printed text settings for this
    batch -- what the Review screen's steppers produce.
    """
    started = time.time()
    total = rows_io.count(input_path)
    if workers is None:
        workers = default_workers() if total >= POOL_THRESHOLD else 1
    if workers > 1 and not can_spawn():
        workers = 1

    successful, failures = 0, []
    done = 0
    cancelled = False
    os.makedirs(TEMP_ROOT, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="job-", dir=TEMP_ROOT)

    def report():
        if on_progress:
            on_progress(done, total, successful, len(failures))

    # Only the columns the profile uses cross the process boundary; the source
    # CSVs carry eighteen columns including phone numbers.
    wanted = tuple(set(profile.required_columns) | {"qr_code"})

    def tasks():
        for number, row in enumerate(rows_io.read_rows(input_path), start=1):
            yield number, {k: row.get(k, "") for k in wanted}

    pool = None
    try:
        report()
        if should_cancel and should_cancel():
            cancelled = True
        else:
            if workers > 1:
                # spawn on every platform so behaviour matches what we ship;
                # fork would inherit state the workers must not see.
                pool = multiprocessing.get_context("spawn").Pool(
                    workers, initializer=_init_worker,
                    initargs=(profile, workdir, style))
                results = pool.imap_unordered(_render_one, tasks(),
                                              chunksize=CHUNKSIZE)
            else:
                _init_worker(profile, workdir, style)
                results = map(_render_one, tasks())

            for number, qr_code, error in results:
                if error is None:
                    successful += 1
                else:
                    failures.append(validate.RowError(number, qr_code, error))
                done += 1
                if done % CHUNKSIZE == 0:
                    report()
                    if should_cancel and should_cancel():
                        cancelled = True
                        break

        report()
        # imap_unordered returns in completion order; a report that reshuffles
        # row numbers run to run is useless for chasing down a bad row.
        failures.sort(key=lambda f: f.row_number)

        if cancelled:
            return BatchResult(total, successful, failures, None, None, True,
                               time.time() - started, workers)

        written = write_zip(workdir, zip_path)
        report_path = None
        if failures:
            report_path = error_report or os.path.join(
                os.path.dirname(os.path.abspath(zip_path)), "generation_errors.csv")
            write_error_report(failures, report_path)
        return BatchResult(total, written, failures, zip_path, report_path, False,
                           time.time() - started, workers)
    finally:
        if pool is not None:
            pool.terminate()
            pool.join()
        shutil.rmtree(workdir, ignore_errors=True)


def write_zip(source_dir, zip_path):
    """Flat ZIP of every file in ``source_dir``. Returns the count written.

    ZIP_STORED on purpose: the payload is already-compressed JPEG, so deflating
    it burns minutes of CPU for about one percent. ZIP64 turns itself on when
    the archive needs it.
    """
    names = sorted(os.listdir(source_dir))
    parent = os.path.dirname(os.path.abspath(zip_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name in names:
            # arcname is the bare filename: no directories, and nothing that
            # could escape the extraction root.
            archive.write(os.path.join(source_dir, name), arcname=name)
    return len(names)


def _escape(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def write_error_report(failures, path):
    """Row-level failures as CSV. Carries no personal data -- only the code."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_number", "qr_code", "error"])
        for failure in failures:
            writer.writerow([failure.row_number, _escape(failure.qr_code),
                             _escape(failure.error)])
    return path


def sweep_stale(older_than_hours=24):
    """Delete job directories a previous run left behind (crash, power loss)."""
    if not os.path.isdir(TEMP_ROOT):
        return 0
    cutoff = time.time() - older_than_hours * 3600
    removed = 0
    for name in os.listdir(TEMP_ROOT):
        path = os.path.join(TEMP_ROOT, name)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed
