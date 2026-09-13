import json

import pytest

from qrgen import rows
from qrgen.rows import InputError


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_csv(tmp_path):
    path = write(tmp_path, "a.csv", "name,qr_code\nJohn Doe,ABC123\nJane,XYZ456\n")
    assert list(rows.read_rows(path)) == [
        {"name": "John Doe", "qr_code": "ABC123"},
        {"name": "Jane", "qr_code": "XYZ456"},
    ]
    assert rows.count(path) == 2
    assert rows.header(path) == ["name", "qr_code"]


def test_strips_excel_bom_and_header_whitespace(tmp_path):
    path = write(tmp_path, "a.csv", "﻿ name , qr_code \nJohn,ABC123\n")
    assert list(rows.read_rows(path)) == [{"name": "John", "qr_code": "ABC123"}]


def test_ignores_trailing_blank_lines(tmp_path):
    path = write(tmp_path, "a.csv", "name,qr_code\nJohn,ABC123\n\n,\n")
    assert rows.count(path) == 1


def test_quoted_commas_survive(tmp_path):
    path = write(tmp_path, "a.csv", 'name,qr_code\n"Doe, John",ABC123\n')
    assert list(rows.read_rows(path))[0]["name"] == "Doe, John"


def test_ragged_row_is_an_error_with_a_line_number(tmp_path):
    path = write(tmp_path, "a.csv", "name,qr_code\nJohn,ABC123\nJane\n")
    with pytest.raises(InputError, match="line 3 has 1 fields, expected 2"):
        list(rows.read_rows(path))


def test_duplicate_columns_are_refused(tmp_path):
    path = write(tmp_path, "a.csv", "qr_code,qr_code\nA,B\n")
    with pytest.raises(InputError, match="duplicate column"):
        list(rows.read_rows(path))


def test_empty_file_is_an_error(tmp_path):
    with pytest.raises(InputError, match="is empty"):
        list(rows.read_rows(write(tmp_path, "a.csv", "")))


def test_reads_json(tmp_path):
    path = write(tmp_path, "a.json", json.dumps(
        [{"qr_code": "036315", "name": "26-B0123-3331"}]))
    assert list(rows.read_rows(path)) == [
        {"qr_code": "036315", "name": "26-B0123-3331"}]


def test_json_must_be_objects(tmp_path):
    path = write(tmp_path, "a.json", json.dumps(["ABC123"]))
    with pytest.raises(InputError, match="array of objects"):
        list(rows.read_rows(path))


def test_broken_json_says_so(tmp_path):
    with pytest.raises(InputError, match="not valid JSON"):
        list(rows.read_rows(write(tmp_path, "a.json", "{oops")))


def test_unsupported_extension(tmp_path):
    with pytest.raises(InputError, match="unsupported file type"):
        list(rows.read_rows(write(tmp_path, "a.xlsx", "x")))


def test_reading_twice_gives_the_same_rows(tmp_path):
    """The engine validates in one pass and generates in another."""
    path = write(tmp_path, "a.csv", "name,qr_code\nJohn,ABC123\n")
    assert list(rows.read_rows(path)) == list(rows.read_rows(path))
