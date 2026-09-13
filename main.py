#!/usr/bin/env python3
"""Desktop application entry point.

The multiprocessing guard matters here: the generation engine spawns worker
processes, and a spawned child re-imports __main__. Without this guard each
worker would open its own window.
"""

import multiprocessing
import os
import sys

from qrgen import selftest


def _fail(message):
    """Report a broken build to whoever launched it, however they launched it."""
    print(f"QR Generator cannot start.\n\n{message}", file=sys.stderr)
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("QR Generator cannot start", message)
        root.destroy()
    except Exception:
        pass          # no display: the stderr message above is the report
    raise SystemExit(2)


def _attach_console():
    """Make stdout visible on Windows.

    The shipped executable is built windowed, which on Windows means it is
    detached from the terminal that launched it -- so --verify would print
    into nothing. Re-attaching to the parent console is the documented way to
    have both a GUI app and usable command-line output.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", buffering=1)
            sys.stderr = open("CONOUT$", "w", buffering=1)
    except Exception:
        pass          # not launched from a console; the exit code still tells


def _verify():
    """Prove this build renders correctly and can drive its worker pool."""
    import csv
    import tempfile
    import zipfile

    from qrgen import engine, paths, profiles

    print(f"build       {'frozen' if paths.frozen() else 'source checkout'}")
    print(f"resources   {paths.root()}")
    print(f"reference   {selftest.check()[:16]}…  ok")

    profile = profiles.get("extraa_cards")
    print(f"profile     {profile.name} v{profile.version}, "
          f"{profile.name_font} {profile.name_size}/{profile.code_size}")

    work = tempfile.mkdtemp(prefix="extraa-verify-")
    source = os.path.join(work, "verify.csv")
    with open(source, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "qr_code"])
        for i in range(1, 301):          # over the pool threshold on purpose
            writer.writerow([f"26-B0004-{i}", f"V{i:05d}"])

    archive = os.path.join(work, "verify.zip")
    result = engine.generate_batch(profile, source, archive)
    with zipfile.ZipFile(archive) as z:
        count = len(z.namelist())
    print(f"batch       {result.summary}")
    print(f"archive     {count} cards")

    ok = result.successful == 300 and result.failed == 0 and count == 300
    print("\nVERIFIED" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    # Required before any pool is created when frozen: spawned workers re-run
    # this executable, and without this they would re-run the app instead of
    # starting as workers.
    multiprocessing.freeze_support()

    # Refuse to open rather than produce cards that do not match the ones
    # already printed. Costs about 40ms.
    try:
        selftest.check()
    except selftest.SelfTestError as exc:
        _fail(str(exc))

    # `QRGenerator --verify` checks an installation without a display:
    # renders the reference card, then runs a real batch through the process
    # pool. This is what to run when a support machine behaves oddly.
    if "--verify" in sys.argv:
        _attach_console()
        raise SystemExit(_verify())

    from ui.app import main
    main()
