# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. One file for both platforms.

    pyinstaller packaging/qrgen.spec --noconfirm

Everything the application reads at runtime has to be listed in `datas`, and
`qrgen.paths` is what finds it again inside the bundle. Leave a font out and the
startup self-test refuses to open the app -- which is the point of it.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    # The typefaces cards are printed with. Not optional: the self-test
    # reproduces a known card at launch and stops the app if it cannot.
    (os.path.join(ROOT, "assets", "fonts"), "assets/fonts"),
    # UI palettes. Editable in the bundle without a rebuild.
    (os.path.join(ROOT, "assets", "theme.json"), "assets"),
    # Profiles shipped as the offline fallback when the API is unreachable.
    (os.path.join(ROOT, "profiles"), "profiles"),
    # Mock accounts, until the login API exists. Hashed, never plain text.
    (os.path.join(ROOT, "mock_users.json"), "."),
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=[
        # Reached only through the renderer registry, so not statically visible.
        "qrgen.renderers.standard",
    ],
    excludes=[
        # Never imported at runtime; excluded so a stray import cannot pull a
        # test-only dependency into a shipped build.
        "pytest", "_pytest", "pluggy", "numpy", "cv2", "pandas",
        "tkinter.test", "test", "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="QRGenerator",
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="QRGenerator",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="QR Generator.app",
        bundle_identifier="in.extraa.qrgenerator",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,      # Tk 9 renders at Retina scale
            "LSMinimumSystemVersion": "11.0",
        },
    )
