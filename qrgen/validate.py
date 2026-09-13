"""Input validation: filenames, rows, and whole-batch checks.

A batch does not start while blocking errors exist. Everything here runs before
a single image is rendered, so a 50,000-row job fails in seconds rather than
twenty minutes in.
"""

import re

from qrgen import templates

# Characters that are illegal in a path segment on Windows, plus the separators
# that would turn a filename into a path on any OS.
ILLEGAL = set('/\\:*?"<>|') | {chr(c) for c in range(32)} | {"\x7f"}

# Windows refuses these stems regardless of extension, even today.
RESERVED = {"CON", "PRN", "AUX", "NUL"} | \
           {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


class FilenameError(ValueError):
    pass


def safe_filename(name):
    """Return ``name`` if it is a safe single path segment, else raise.

    Rejects path traversal (``../../evil.png``), absolute paths, separators,
    control characters, Windows-reserved stems, and the trailing dots/spaces
    Windows silently strips (which would collide two rows into one file).
    """
    if not isinstance(name, str) or not name:
        raise FilenameError("filename is empty")
    if name in (".", ".."):
        raise FilenameError(f"{name!r} is not a filename")
    if ".." in name:
        raise FilenameError(f"{name!r} contains '..' (path traversal)")
    bad = sorted(ILLEGAL & set(name))
    if bad:
        raise FilenameError(
            f"{name!r} contains illegal character(s) {[repr(c) for c in bad]}")
    if name[-1] in ". ":
        raise FilenameError(f"{name!r} ends with a dot or space")
    if name.split(".")[0].upper() in RESERVED:
        raise FilenameError(f"{name!r} uses the Windows-reserved name "
                            f"{name.split('.')[0].upper()!r}")
    if len(name.encode("utf-8")) > 255:
        raise FilenameError(f"filename is too long ({len(name)} characters)")
    return name


class RowError:
    __slots__ = ("row_number", "qr_code", "error")

    def __init__(self, row_number, qr_code, error):
        self.row_number = row_number
        self.qr_code = qr_code
        self.error = error

    def __repr__(self):
        return f"RowError(row {self.row_number}, {self.qr_code!r}, {self.error})"

    def as_dict(self):
        return {"row_number": self.row_number, "qr_code": self.qr_code,
                "error": self.error}


class Report:
    """Outcome of validating a whole input file."""

    def __init__(self, total, errors, missing_columns):
        self.total = total
        self.errors = errors
        self.missing_columns = missing_columns

    @property
    def ok(self):
        return not self.errors and not self.missing_columns

    @property
    def summary(self):
        if self.missing_columns:
            return f"missing required column(s): {', '.join(self.missing_columns)}"
        if self.errors:
            return f"{len(self.errors)} of {self.total} rows have errors"
        return f"{self.total} rows, no errors"


def _check_value(rule, value, column):
    if rule.get("length") is not None and len(value) != rule["length"]:
        return (f"{column} must be exactly {rule['length']} characters, "
                f"got {len(value)}")
    charset = rule.get("charset")
    if charset == "alnum" and not value.isalnum():
        offenders = sorted({c for c in value if not c.isalnum()})
        return (f"{column} must be alphanumeric; found "
                f"{', '.join(repr(c) for c in offenders)}")
    if charset == "alnum" and not value.isascii():
        return f"{column} must be plain ASCII letters and digits"
    pattern = rule.get("pattern")
    if pattern and not re.fullmatch(pattern, value):
        return f"{column} does not match the required pattern {pattern}"
    return None


def validate_rows(rows, profile):
    """Validate every row against a profile. Returns a :class:`Report`.

    ``rows`` is any iterable of dicts; it is consumed once, so callers that
    also need the data should pass a list.
    """
    errors = []
    seen_filenames = {}
    seen_unique = {column: {} for column in profile.unique_columns}
    total = 0
    missing_columns = None

    for number, row in enumerate(rows, start=1):
        total = number

        if missing_columns is None:  # header shape is the same for every row
            missing_columns = [c for c in profile.required_columns if c not in row]
            if missing_columns:
                return Report(0, [], missing_columns)

        qr_code = str(row.get("qr_code", "") or "")

        blank = [c for c in profile.required_columns
                 if not str(row.get(c) or "").strip()]
        if blank:
            errors.append(RowError(number, qr_code,
                                   f"empty value(s) for: {', '.join(blank)}"))
            continue

        bad_value = None
        for column, rule in profile.validation.items():
            if column in row:
                bad_value = _check_value(rule, str(row[column]).strip(), column)
                if bad_value:
                    errors.append(RowError(number, qr_code, bad_value))
                    break
        if bad_value:
            continue

        duplicate = False
        for column in profile.unique_columns:
            value = str(row.get(column, "")).strip()
            first = seen_unique[column].get(value)
            if first is not None:
                errors.append(RowError(
                    number, qr_code,
                    f"duplicate {column} {value!r}, already used by row {first}"))
                duplicate = True
                break
            seen_unique[column][value] = number
        if duplicate:
            continue

        try:
            filename = safe_filename(templates.resolve(profile.filename, row))
        except (FilenameError, templates.TemplateError) as exc:
            errors.append(RowError(number, qr_code, f"unsafe filename: {exc}"))
            continue

        # Two rows writing the same file means one silently overwrites the
        # other -- the ZIP would be short and nobody would know.
        key = filename.lower()  # macOS and Windows are case-insensitive
        first = seen_filenames.get(key)
        if first is not None:
            errors.append(RowError(
                number, qr_code,
                f"filename {filename!r} collides with row {first}"))
            continue
        seen_filenames[key] = number

    return Report(total, errors, missing_columns or [])
