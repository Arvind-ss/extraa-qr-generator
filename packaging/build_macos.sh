#!/usr/bin/env bash
# Build and verify the macOS application.
#
#   ./packaging/build_macos.sh
#
# Produces dist/QR Generator.app and then runs the bundle's own --verify,
# so a broken build fails here rather than on a support machine.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
APP="dist/QR Generator.app"

echo "==> dependencies"
"$PYTHON" -m pip install -q -r requirements-dev.txt pyinstaller

echo "==> tests (the golden corpus must pass before anything ships)"
"$PYTHON" -m pytest -q

echo "==> build"
rm -rf build dist
"$PYTHON" -m PyInstaller packaging/qrgen.spec --noconfirm

echo "==> verifying the bundle"
"$APP/Contents/MacOS/QRGenerator" --verify

echo
echo "Built: $APP  ($(du -sh "$APP" | cut -f1))"
echo "Unsigned. To distribute outside this machine, sign and notarise:"
echo "  codesign --deep --force --options runtime --sign \"Developer ID Application: ...\" \"$APP\""
echo "  xcrun notarytool submit ... && xcrun stapler staple \"$APP\""
