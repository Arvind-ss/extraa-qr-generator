# Developer guide

```bash
brew install python@3.13 python-tk@3.13      # Tk 8.5 renders blurry on Retina
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                # ~270 tests, under 30s
.venv/bin/python main.py
```

The full golden corpus — ~2,000 cards already shipped, verified byte-for-byte —
only runs when you point it at the old working directory:

```bash
EXTRAA_GOLDEN_DIR=~/Extraa/scriptcodes/qr_gen .venv/bin/python -m pytest -q
```

Run that before shipping anything that touches rendering.

## Layout

```
qrgen/            everything that is not the interface
  renderers/      standard.py -- the lifted original
  store/          the shared profile store and its disk cache
  engine.py       validate, sample, batch, ZIP
  profiles.py     the Profile model
  templates.py    {name} substitution -- not str.format, see below
  validate.py     CSV rules and filename safety
  auth.py         mock and API providers, roles
  paths.py        where bundled files are, frozen or not
ui/               Tk. Imports qrgen; qrgen never imports ui
legacy/           the frozen original script, the differential reference
server/           SQL for the profile store, run by hand
packaging/        PyInstaller spec and build scripts
```

`qrgen` has no knowledge of the UI. `cli.py` drives the whole pipeline without a
window, which is what you want when debugging a 50,000-row job.

## The renderer is not yours to improve

`qrgen/renderers/standard.py` is a verbatim lift of `legacy/qr_gen_3.py`. Its
strange parts are load-bearing:

* the QR is pasted at `y=-10`, losing its top 10px
* the caption is pasted over the QR's bottom 80px, then everything is cropped
  from `y=40` — leaving a **0.92-module quiet zone** where the spec asks for 4
* `qr_width` is a parameter that has never done anything
* output is **JPEG bytes written into files named `.png`**

Those produced ~2,000 cards that are in people's hands. `tests/test_renderer_golden.py`
and `tests/test_renderer_differential.py` reproduce them byte-for-byte on every
run, pinning the typeface and sizes back to the original Geist Mono 36/60.

If you change rendering, those tests will go red. **That is the tests working.**
Find out what moved before you touch a fixture.

Printed text is parameterised — `name_font`, `code_font`, `name_size`,
`code_size`, `name_tracking`, `code_tracking` — defaulting to module constants
and overridable per profile and per batch. The historical tests pin the
constants; tests marked `current_sizes` check today's defaults.

## Adding a renderer

The registry is a dict:

```python
# qrgen/renderers/__init__.py
REGISTRY = {"standard": render_standard}
```

Write a module with `render(qr_content, bottom_text, top_text=None, **style)`,
add an entry, and profiles can name it. A profile carries the **key**, never a
path or an import — `renderer: "os.system"` is refused on load.

One entry today. A branded variant with the Extraa logo was prototyped and not
merged; if it ships it becomes `"branded"`.

## Adding a profile

Through the admin UI, or a row in `ec_qr_profiles`. `profiles/*.json` is the
offline fallback baked into the bundle and should stay small.

Adding a **field** to `Profile` means three other places: `server/schema.sql`, a
migration, and `hasura.FIELDS` plus the upsert columns. Six tests in
`tests/test_store.py` fail if you miss one — they exist because this drifted
once and would have silently returned defaults instead of stored values.

## Templates never execute

`qrgen/templates.py` resolves `{column}` with a regex and a dict lookup.
Deliberately **not** `str.format`, which would let a profile reach the process
internals through `{x.__class__.__init__.__globals__}`. `{0}`, `{a.b}`, `{a!r}`
are literal text. No `eval`, no `exec`, no import by name.

## Batch processing

```
csv.DictReader (streaming)
  -> rows projected to the profile's columns only
  -> multiprocessing.Pool, spawn, cores - 1
  -> each worker renders and writes one file, then releases it
  -> parent counts, reports progress, builds the ZIP
```

Peak memory is flat in the batch size. Measured: **50,000 rows in 2m45s, 38 MB**.

Things that look wrong and are not:

* **spawn, not fork, everywhere** — so behaviour matches the frozen build
* `freeze_support()` is the first statement in `main.py`; without it each of
  nine workers opens its own window
* `can_spawn()` falls back to a single process when `__main__` is not
  importable (a REPL, a heredoc), because the alternative is an unrecoverable
  hang
* failures are sorted by row before reporting — `imap_unordered` returns in
  completion order, and a report that reshuffles run-to-run is useless
* the ZIP is `ZIP_STORED`: the payload is already-compressed JPEG

## The UI

`ttk` with the `clam` theme, which takes colour on every widget and looks the
same on both platforms. Tk cannot do rounded corners, shadows or alpha, so:
square everything, tints pre-blended to solid hex, and the only two gradients
are canvas-drawn.

Palettes live in `assets/theme.json` — `mono`, `monoDark`, `light`, `dark`.
`EXTRAA_QR_THEME` picks one. `palette(mode)` is a pure function so the contrast
tests can check all four without reloading the module.

Two rules with tests behind them: every status colour clears WCAG AA in every
palette, and the preview well behind the sample card stays neutral grey — never
tinted, never white, never black, because that is the one thing a person has to
judge by eye.

Three UI traps worth knowing:

* **One Tk root per process.** Creating a second after destroying the first
  segfaults on macOS. The tests build one and reuse it.
* **Never use `StringVar`.** Each is a Tcl object whose `__del__` makes Tcl
  calls; a few hundred dead ones freeze the event loop mid-collection. Entries
  hold their own text.
* **`run_async` drops stale results.** It records which screen asked and
  discards the reply if the user has moved on, or the callback writes into
  destroyed widgets.

## Packaging

`./packaging/build_macos.sh`, or the PowerShell script **on Windows** — there is
no cross-compilation.

Every launch renders one known card and refuses to open on a mismatch. A
bundle that lost its font renders plausible cards that are wrong, and nobody
notices until fifty thousand are printed. `--verify` does the same check plus a
real 300-row batch.

Anything read at runtime goes through `qrgen.paths.resource()`. Guessing from
`__file__` works in a checkout and silently breaks when frozen.

## Dependencies

Pillow and qrcode. That is all that ships — **15 MB**, in a 40 MB bundle.

Pillow's version is part of the output contract: 10.1.0 versus 11.3.0 moves 131
pixels on one card. Pinned, and the startup self-test catches a mismatch.

OpenCV was here for QR verification and was 157 MB of the 172 MB the app
carried. Verification is now the support team's job, so it is gone.
