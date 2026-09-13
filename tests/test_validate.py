import pytest

from qrgen import profiles, validate
from qrgen.validate import FilenameError, safe_filename


@pytest.mark.parametrize("name", [
    "ABC123.png", "26-B0008-1.png", "Café.png", "M41 - I520.png",
])
def test_accepts_real_filenames(name):
    assert safe_filename(name) == name


@pytest.mark.parametrize("name,reason", [
    ("../../evil.png", "traversal"),
    ("..", "traversal"),
    ("a/b.png", "separator"),
    ("a\\b.png", "separator"),
    ("/etc/passwd", "absolute"),
    ("a\x00b.png", "control character"),
    ("a\nb.png", "control character"),
    ('a"b.png', "illegal on windows"),
    ("a:b.png", "illegal on windows"),
    ("a*b.png", "illegal on windows"),
    ("CON.png", "windows reserved"),
    ("nul.PNG", "windows reserved"),
    ("COM1.png", "windows reserved"),
    ("trailing.png ", "trailing space"),
    ("trailing.", "trailing dot"),
    ("", "empty"),
    ("x" * 300 + ".png", "too long"),
])
def test_rejects_dangerous_filenames(name, reason):
    with pytest.raises(FilenameError):
        safe_filename(name)


def _profile(**overrides):
    base = dict(id="t", name="T", renderer="standard",
                required_columns=("name", "qr_code"),
                qr_content="https://x.test/{qr_code}", bottom_text="{qr_code}",
                top_text="{name}", filename="{qr_code}.png",
                unique_columns=("qr_code",),
                validation={"qr_code": {"length": 6, "charset": "alnum"}})
    base.update(overrides)
    return profiles.Profile(**base)


def test_clean_input_passes():
    report = validate.validate_rows(
        [{"name": "A", "qr_code": "ABC123"}, {"name": "B", "qr_code": "XYZ456"}],
        _profile())
    assert report.ok and report.total == 2 and report.summary == "2 rows, no errors"


def test_missing_column_stops_everything():
    report = validate.validate_rows([{"qr_code": "ABC123"}], _profile())
    assert not report.ok
    assert report.missing_columns == ["name"]
    assert "missing required column" in report.summary


@pytest.mark.parametrize("qr_code,fragment", [
    ("ABC12", "exactly 6 characters"),
    ("ABC1234", "exactly 6 characters"),
    ("ABC-12", "alphanumeric"),
    ("ABC 12", "alphanumeric"),
    ("ABC_12", "alphanumeric"),
])
def test_bad_qr_codes_are_reported(qr_code, fragment):
    report = validate.validate_rows([{"name": "A", "qr_code": qr_code}], _profile())
    assert not report.ok
    assert fragment in report.errors[0].error
    assert report.errors[0].row_number == 1


def test_blank_values_are_reported():
    report = validate.validate_rows(
        [{"name": "   ", "qr_code": "ABC123"}], _profile())
    assert "empty value" in report.errors[0].error


def test_duplicate_qr_codes_name_the_first_row():
    report = validate.validate_rows(
        [{"name": "A", "qr_code": "ABC123"},
         {"name": "B", "qr_code": "XYZ456"},
         {"name": "C", "qr_code": "ABC123"}], _profile())
    assert len(report.errors) == 1
    assert report.errors[0].row_number == 3
    assert "already used by row 1" in report.errors[0].error


def test_filename_collision_is_caught_even_when_codes_differ():
    """Two rows writing one file means the ZIP silently comes up short."""
    profile = _profile(filename="{name}.png", unique_columns=(),
                       validation={})
    report = validate.validate_rows(
        [{"name": "store", "qr_code": "A"}, {"name": "STORE", "qr_code": "B"}],
        profile)
    assert "collides with row 1" in report.errors[0].error


def test_path_traversal_through_a_column_value_is_blocked():
    profile = _profile(filename="{name}.png", unique_columns=(), validation={})
    report = validate.validate_rows(
        [{"name": "../../evil", "qr_code": "ABC123"}], profile)
    assert "unsafe filename" in report.errors[0].error


def test_errors_do_not_stop_at_the_first_row():
    rows = [{"name": "A", "qr_code": "BAD"},
            {"name": "B", "qr_code": "OK1234"},
            {"name": "C", "qr_code": "ALSOBAD"}]
    report = validate.validate_rows(rows, _profile())
    assert report.total == 3
    assert [e.row_number for e in report.errors] == [1, 3]
