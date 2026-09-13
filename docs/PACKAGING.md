# Packaging

One spec, `packaging/qrgen.spec`, builds both platforms. There is **no
cross-compilation**: PyInstaller bundles the interpreter and Tk libraries of
the machine it runs on, so the Windows build has to happen on Windows.

```bash
./packaging/build_macos.sh                                     # macOS
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1   # Windows
```

Both scripts run the test suite first, build, then run the finished bundle's
own `--verify`. A build that renders incorrectly fails on the build machine
rather than on someone's laptop.

## What comes out

| | |
|---|---|
| macOS | `dist/QR Generator.app` — **40 MB** |
| Windows | `dist\ExtraaQRGenerator\` — expect a similar size |

Measured on the built macOS bundle: reference card correct, **300 cards through
9 worker processes in 1.4s**, verified from a copy with no source tree present.

Support users install nothing. Python, Tk, Pillow, qrcode and both typefaces are
inside the bundle.

## Verifying an installation

```
"QR Generator.app/Contents/MacOS/ExtraaQRGenerator" --verify
QRGenerator.exe --verify
```

Renders the reference card, then generates a real 300-row batch through the
process pool and checks the archive. Run it when a machine behaves oddly; it
separates "this build is broken" from "this input is broken" in about three
seconds. Exit code 0 means good.

## The startup self-test

Every launch renders one known card and compares it to a hash in
`qrgen/selftest.py`. **A mismatch stops the application from opening.**

This exists because a packaged app fails in ways the test suite cannot see — the
tests run from a source checkout, where the fonts are simply present. If a
typeface is not bundled, or Pillow is not the pinned version, the app still
renders *something*: plausible cards, wrong output, discovered after fifty
thousand are printed. Refusing to open is the better failure. It costs 85ms.

The reference is the Brigade card at its original Geist Mono 36/60, so the hash
is the same one `tests/golden/manifest.json` asserts.

## What is bundled, and how it is found

`assets/fonts/`, `assets/theme.json`, `profiles/`, `mock_users.json`.

A frozen app unpacks these into `sys._MEIPASS`, which is nowhere near the code.
Every module goes through `qrgen.paths.resource()` rather than guessing from
`__file__` — four modules used to guess separately, and each was a way for the
bundle to break silently.

`numpy`, `cv2`, `pandas` and the test packages are explicitly excluded, so a
stray import cannot pull a test-only dependency into a shipped build.

## Signing

Both builds are **unsigned**.

* **macOS** — Gatekeeper will refuse to open it on another Mac. Needs an Apple
  Developer ID, then `codesign --deep --force --options runtime` and
  `notarytool submit` + `stapler staple`.
* **Windows** — SmartScreen warns on first run until the executable is signed
  with a code-signing certificate.

Neither blocks internal testing: right-click → Open on macOS, "More info" → "Run
anyway" on Windows. Both should be resolved before the tool is handed to support
staff, because training people to click through security warnings is its own
problem.

## Windows prerequisites

Use **Python 3.13 from python.org**. The Microsoft Store build omits Tk, and
Tk 8.5 (the macOS system Python's version) has no Retina support and renders the
interface blurry.

## Why `freeze_support()` matters

The engine spawns worker processes, and a spawned worker **re-runs the
executable**. Without `multiprocessing.freeze_support()` as the first statement
in `main.py`, each of the nine workers would open its own application window.
It is called before anything else, including the self-test.
