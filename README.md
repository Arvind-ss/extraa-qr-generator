# QR Generator

Generates batches of QR cards from a CSV. Replaces a script that support ran by
hand, editing commented-out blocks to switch between clients.

```bash
brew install python@3.13 python-tk@3.13
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python main.py
```

## Documentation

| | |
|---|---|
| [User guide](docs/USER_GUIDE.md) | for the support team |
| [Admin guide](docs/ADMIN_GUIDE.md) | profiles, settings, the shared store |
| [Developer guide](docs/DEVELOPER_GUIDE.md) | architecture and the traps |
| [Packaging](docs/PACKAGING.md) | building for macOS and Windows |
| [Profile mapping](docs/PROFILE_MAPPING.md) | the old script's thirteen patterns |
| [Benchmarks](docs/BENCHMARKS.md) | measured, not estimated |
| [Themes](docs/THEMES.md) · [Auth](docs/AUTH.md) | palettes; roles and the v2 login |
| [server/README](server/README.md) | the profile store and its credentials |

## The one rule

The renderer in `qrgen/renderers/standard.py` is a verbatim lift of
`legacy/qr_gen_3.py`. Roughly **2,000 cards already in people's hands** were
produced by it, and the golden tests reproduce every one byte-for-byte on each
run.

Its odd parts — a paste at `y=-10`, a crop that leaves under one module of quiet
zone, JPEG bytes written into `.png` files — are preserved on purpose. If a test
in `tests/test_renderer_*.py` goes red, find out what moved. Do not adjust the
fixture.

## Command line

```bash
.venv/bin/python cli.py profiles                                  # what is available
.venv/bin/python cli.py validate -p extraa_cards -i cards.csv     # check a file
.venv/bin/python cli.py generate -p extraa_cards -i cards.csv -o out.zip
.venv/bin/python cli.py store                                     # diagnose the API
```

## Measured

| | |
|---|---|
| 50,000 cards | 2m 45s, nine workers |
| Peak memory | 38 MB, flat in batch size |
| Shipped dependencies | Pillow, qrcode — 15 MB |
| macOS bundle | 40 MB |
| Tests | ~280, plus ~2,000 golden cards |
