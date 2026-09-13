# Working in this repository

A desktop app that generates batches of QR cards from a CSV. Start with
`README.md`, then `docs/DEVELOPER_GUIDE.md` — it leads with what not to change.

## Setup

```bash
.venv/bin/python -m pytest -q                # ~283 tests, ~30s
.venv/bin/python main.py                     # the app
.venv/bin/python cli.py generate -p extraa_cards -i examples/sample_clean.csv -o out.zip -y
```

Python 3.13 with Tk 9 (`brew install python@3.13 python-tk@3.13`). Python 3.9's
system Tk is 8.5 and renders blurry on Retina.

## Before changing anything that renders

```bash
EXTRAA_GOLDEN_DIR=~/Extraa/scriptcodes/qr_gen .venv/bin/python -m pytest -q
```

That sweeps ~2,000 cards already in customers' hands and checks them
byte-for-byte. **They are not in this repo** — without the variable those tests
skip silently, so a green suite alone does not prove the shipped cards still
reproduce.

`qrgen/renderers/standard.py` is a verbatim lift of `legacy/qr_gen_3.py`. The
paste at `y=-10`, the crop leaving under one module of quiet zone, and the JPEG
bytes written into `.png` files are all load-bearing. If a renderer test goes
red, find out what moved — do not adjust the fixture.

## House rules

* `qrgen/` never imports `ui/`. The engine runs headless; `cli.py` proves it.
* Profiles are data. No code, no import paths — `renderer` is a key into a dict,
  and templates are regex substitution, never `str.format`.
* Adding a field to `Profile` means four places: the model, `server/schema.sql`,
  a migration, and `hasura.FIELDS` + the upsert columns. Tests enforce it.
* Never signal state by colour alone; a glyph and a word go with it. That is
  what makes the monochrome palettes usable.
* Credentials come from the environment or a 0600 config file. Never a literal,
  never a log, never a `repr`.

## Tk traps that have already cost time

* One `Tk()` root per process — a second after destroying the first segfaults on
  macOS.
* No `StringVar`. Each is a Tcl object whose `__del__` calls into Tcl; a few
  hundred dead ones freeze the event loop mid-collection.
* `run_async` must drop stale results, or a callback writes into destroyed
  widgets after the user navigates away.
* `multiprocessing.freeze_support()` is the first statement in `main.py`.
  Without it every worker opens its own window when frozen.

## Measured, not guessed

50,000 rows in 3m48s through the UI, worst frame 1.3 ms, 148 MB. Pillow 10.1.0
vs 11.3.0 moves 131 pixels on one card, which is why it is pinned. When a claim
about performance or output matters here, measure it — `docs/BENCHMARKS.md` is
the record.
