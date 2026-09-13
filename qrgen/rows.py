"""Streaming input reader for CSV and JSON.

Replaces the reference script's pandas ``read_csv`` + ``iterrows``. Nothing here
holds the whole file: a 50,000-row CSV is read a row at a time, and callers that
need two passes (validate, then generate) simply read it twice -- cheaper than
keeping 50,000 wide dicts alive.
"""

import csv
import json
import os


class InputError(ValueError):
    pass


def _open(path):
    # utf-8-sig strips the BOM Excel writes, which would otherwise turn the
    # first header into '﻿qr_code' and read as a missing column.
    return open(path, "r", encoding="utf-8-sig", newline="")


def header(path):
    """Column names, without reading the body."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".csv":
        with _open(path) as fh:
            try:
                names = next(csv.reader(fh))
            except StopIteration:
                raise InputError(f"{os.path.basename(path)} is empty") from None
        return [n.strip() for n in names]
    return sorted({k for row in _read_json(path) for k in row})


def _read_json(path):
    with _open(path) as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise InputError(f"{os.path.basename(path)} is not valid JSON: {exc}") from None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise InputError(
            f"{os.path.basename(path)} must be a JSON array of objects")
    return data


def read_rows(path):
    """Yield one dict per record. Values are stripped strings."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".csv":
        yield from _read_csv(path)
    elif suffix == ".json":
        for row in _read_json(path):
            yield {str(k).strip(): ("" if v is None else str(v).strip())
                   for k, v in row.items()}
    else:
        raise InputError(
            f"unsupported file type {suffix!r}; use .csv or .json")


def _read_csv(path):
    with _open(path) as fh:
        reader = csv.reader(fh)
        try:
            names = [n.strip() for n in next(reader)]
        except StopIteration:
            raise InputError(f"{os.path.basename(path)} is empty") from None
        if not any(names):
            raise InputError(f"{os.path.basename(path)} has a blank header row")
        duplicates = {n for n in names if names.count(n) > 1 and n}
        if duplicates:
            raise InputError(
                f"{os.path.basename(path)} has duplicate column(s): "
                f"{', '.join(sorted(duplicates))}")

        width = len(names)
        for line_number, values in enumerate(reader, start=2):
            if not any(v.strip() for v in values):
                continue  # trailing blank line
            if len(values) != width:
                raise InputError(
                    f"{os.path.basename(path)} line {line_number} has "
                    f"{len(values)} fields, expected {width}")
            yield dict(zip(names, (v.strip() for v in values)))


def count(path):
    """Number of records, for showing a total before work starts."""
    return sum(1 for _ in read_rows(path))
