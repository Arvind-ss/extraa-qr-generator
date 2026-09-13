"""On-disk copy of the last profiles the store served.

Lets a support user generate a batch when the network is down. Never
authoritative: it is only ever written from a successful fetch, and saving a
profile requires the real store.
"""

import json
import os
import tempfile
import time

from qrgen import config


def cache_path():
    return os.path.join(config.config_dir(), "profiles-cache.json")


def write(records, path=None):
    path = path or cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"fetched_at": time.time(), "profiles": records}
    # Write-and-rename: an interrupted write must not leave a truncated cache
    # that then fails to parse on the next launch.
    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return path


def read(path=None):
    """Returns ``(records, fetched_at)`` or ``(None, None)``."""
    path = path or cache_path()
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload["profiles"], payload.get("fetched_at")
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
