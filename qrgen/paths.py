"""Where the bundled files are.

One place, because the answer differs between a source checkout and a frozen
build, and four modules were each guessing at it separately. PyInstaller
unpacks bundled data into ``sys._MEIPASS``; a checkout has it beside the code.
"""

import os
import sys

# The repository root in a checkout: qrgen/paths.py -> qrgen -> root.
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def root():
    return getattr(sys, "_MEIPASS", None) or _SOURCE_ROOT


def resource(*parts):
    """Absolute path to a file that ships with the application."""
    return os.path.join(root(), *parts)


def frozen():
    return hasattr(sys, "_MEIPASS")
