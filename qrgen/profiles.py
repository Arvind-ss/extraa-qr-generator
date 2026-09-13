"""Profile model.

A profile is business configuration and nothing else: which columns the input
must have, what goes into the QR, what text is printed, what the file is called.
It carries no code and no import path -- ``renderer`` is a key into
:mod:`qrgen.renderers`, validated on load against a fixed registry.

The dict shape here is the same one the Profile API stores and serves, so a
built-in profile and a remote one are indistinguishable to the engine.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from qrgen import paths, renderers, templates
from qrgen.renderers import standard  # noqa: F401  (font list)

BUILTIN_DIR = paths.resource("profiles")

OUTPUT_FORMATS = {
    # The reference script encodes JPEG and writes it to a .png filename. That
    # is preserved deliberately -- see docs/PROFILE_MAPPING.md.
    "jpeg": "JPEG",
}


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    renderer: str
    required_columns: Tuple[str, ...]
    qr_content: str
    bottom_text: str
    filename: str
    top_text: Optional[str] = None
    output_format: str = "jpeg"
    unique_columns: Tuple[str, ...] = ()
    validation: Dict[str, dict] = field(default_factory=dict)
    active: bool = True
    version: int = 1

    # Printed text style. Data, not code -- the renderer reads these numbers
    # and nothing else. Bounds exist because a 400px name would push the card
    # past any sane size and a negative one would crash Pillow.
    name_font: str = "rob.ttf"
    code_font: str = "rob.ttf"
    name_size: int = 48
    code_size: int = 80
    name_tracking: int = 5
    code_tracking: int = 0

    def __post_init__(self):
        if not self.required_columns:
            raise ProfileError(f"profile {self.name!r} declares no input columns")
        if self.renderer not in renderers.REGISTRY:
            raise ProfileError(
                f"profile {self.name!r} names unknown renderer {self.renderer!r}; "
                f"known: {sorted(renderers.REGISTRY)}")
        if self.output_format not in OUTPUT_FORMATS:
            raise ProfileError(
                f"profile {self.name!r} has unsupported output format "
                f"{self.output_format!r}; supported: {sorted(OUTPUT_FORMATS)}")

        for label in ("qr_content", "bottom_text", "filename", "top_text"):
            value = getattr(self, label)
            if value is not None:
                templates.check(value, self.required_columns, label)

        # Catch a path-shaped filename template at save time rather than
        # discovering it row by row. Per-row output is still checked by
        # validate.safe_filename, since column values can smuggle these in too.
        for bad in ("/", "\\", ".."):
            if bad in self.filename:
                raise ProfileError(
                    f"profile {self.name!r} has a filename template containing "
                    f"{bad!r}: {self.filename!r}")

        for field_name, low, high in (("name_size", 12, 160),
                                      ("code_size", 12, 160),
                                      ("name_tracking", -10, 40),
                                      ("code_tracking", -10, 40)):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ProfileError(
                    f"profile {self.name!r}: {field_name} must be a whole "
                    f"number, got {value!r}")
            if not low <= value <= high:
                raise ProfileError(
                    f"profile {self.name!r}: {field_name} is {value}, "
                    f"outside {low}..{high}")

        fonts = renderers.standard.available_fonts()
        for field_name in ("name_font", "code_font"):
            value = getattr(self, field_name)
            if value not in fonts:
                raise ProfileError(
                    f"profile {self.name!r}: {field_name} is {value!r}; "
                    f"bundled fonts are {fonts}")

        for column in tuple(self.unique_columns) + tuple(self.validation):
            if column not in self.required_columns:
                raise ProfileError(
                    f"profile {self.name!r} validates column {column!r} which it "
                    f"does not require")

    @property
    def render(self):
        return renderers.get(self.renderer)

    @property
    def pil_format(self):
        return OUTPUT_FORMATS[self.output_format]

    @property
    def style(self):
        """Printed text style, as the renderer's keyword arguments."""
        return {"name_font": self.name_font, "code_font": self.code_font,
                "name_size": self.name_size, "code_size": self.code_size,
                "name_tracking": self.name_tracking,
                "code_tracking": self.code_tracking}

    def build(self, row):
        """Resolve one row into everything needed to render and save it."""
        return {
            "qr_content": templates.resolve(self.qr_content, row),
            "bottom_text": templates.resolve(self.bottom_text, row),
            "top_text": (templates.resolve(self.top_text, row)
                         if self.top_text else None),
            "filename": templates.resolve(self.filename, row),
        }

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ProfileError(f"unknown profile field(s): {sorted(unknown)}")
        data = dict(data)
        for key in ("required_columns", "unique_columns"):
            if key in data:
                data[key] = tuple(data[key])
        try:
            return cls(**data)
        except TypeError as exc:
            raise ProfileError(f"invalid profile: {exc}") from None

    def to_dict(self):
        out = {f: getattr(self, f) for f in self.__dataclass_fields__}
        out["required_columns"] = list(out["required_columns"])
        out["unique_columns"] = list(out["unique_columns"])
        return out


def load_builtin():
    """Profiles shipped with the app, keyed by id.

    A stand-in for the Profile API until Stage 8. The engine does not care where
    a profile came from.
    """
    found = {}
    for name in sorted(os.listdir(BUILTIN_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(BUILTIN_DIR, name), encoding="utf-8") as fh:
            profile = Profile.from_dict(json.load(fh))
        found[profile.id] = profile
    return found


def get(profile_id):
    try:
        return load_builtin()[profile_id]
    except KeyError:
        raise ProfileError(
            f"no profile with id {profile_id!r}; "
            f"available: {sorted(load_builtin())}") from None
