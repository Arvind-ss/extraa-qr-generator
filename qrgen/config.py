"""Runtime configuration.

No credential is ever hardcoded, committed, or logged. Values come from the
environment first, then a per-user config file that must not be readable by
anyone else.
"""

import json
import os
import stat
import sys

APP_DIR = "extraa-qr"

ENV = {
    "api_url": "EXTRAA_QR_API_URL",
    "admin_secret": "EXTRAA_QR_ADMIN_SECRET",
    "token": "EXTRAA_QR_TOKEN",
    "role": "EXTRAA_QR_ROLE",
}

SECRET_KEYS = {"admin_secret", "token"}


class ConfigError(RuntimeError):
    pass


def config_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_DIR)


def config_path():
    return os.path.join(config_dir(), "config.json")


def _read_file(path):
    if not os.path.exists(path):
        return {}
    info = os.stat(path)
    # A secret in a world-readable file is not a secret. Refuse loudly rather
    # than silently using it.
    if os.name != "nt" and info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(
            f"{path} is readable by other users (mode "
            f"{stat.S_IMODE(info.st_mode):o}); run: chmod 600 {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def load(path=None):
    """Merged configuration. Environment wins over the file."""
    settings = _read_file(path or config_path())
    for key, variable in ENV.items():
        value = os.environ.get(variable)
        if value:
            settings[key] = value
    return settings


def save(settings, path=None):
    """Write the per-user configuration, readable by nobody else.

    Created 0600 from the start rather than chmod'ed afterwards: between the
    two there is a moment where a credential sits in a world-readable file.
    Values already supplied by the environment are not written, so a machine
    configured by IT through env vars is not quietly duplicated into a file.
    """
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from_env = {key for key, variable in ENV.items() if os.environ.get(variable)}
    body = {k: v for k, v in settings.items() if v and k not in from_env}

    temporary = path + ".tmp"
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return path


def redacted(settings):
    """A copy safe to print, log, or put in a bug report."""
    return {k: ("<set>" if k in SECRET_KEYS and v else v)
            for k, v in settings.items()}
