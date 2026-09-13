# Build and verify the Windows application.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Run this ON Windows. There is no cross-compilation: PyInstaller bundles the
# interpreter and the Tk libraries of the machine it runs on.
#
# Requires Python 3.13 from python.org (the Microsoft Store build omits Tk).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = if ($env:PYTHON) { $env:PYTHON } else { ".venv\Scripts\python.exe" }
$exe = "dist\QRGenerator\QRGenerator.exe"

Write-Host "==> dependencies"
& $python -m pip install -q -r requirements-dev.txt pyinstaller

Write-Host "==> tests (the golden corpus must pass before anything ships)"
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "tests failed" }

Write-Host "==> build"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $python -m PyInstaller packaging\qrgen.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "build failed" }

Write-Host "==> verifying the bundle"
& $exe --verify
if ($LASTEXITCODE -ne 0) { throw "the built application does not render correctly" }

Write-Host ""
Write-Host "Built: dist\QRGenerator\"
Write-Host "Unsigned: SmartScreen will warn on first run. Sign with signtool to avoid that."
