import pytest

from qrgen import profiles
from qrgen.profiles import Profile, ProfileError

GOOD = dict(id="t", name="T", renderer="standard",
            required_columns=("name", "qr_code"),
            qr_content="https://x.test/{qr_code}", bottom_text="{qr_code}",
            top_text="{name}", filename="{qr_code}.png")


def test_extraa_cards_profile_ships_and_is_correct():
    profile = profiles.get("extraa_cards")
    assert profile.name == "Extraa Cards"
    assert profile.renderer == "standard"
    assert profile.required_columns == ("name", "qr_code")
    assert profile.unique_columns == ("qr_code",)
    assert profile.validation == {"qr_code": {"length": 6, "charset": "alnum"}}
    assert profile.build({"name": "26-B0008-1", "qr_code": "RDFXRN"}) == {
        "qr_content": "https://www.extraacards.com/cards/RDFXRN",
        "bottom_text": "RDFXRN",
        "top_text": "26-B0008-1",
        "filename": "RDFXRN.png",
    }


def test_round_trips_through_dict():
    profile = profiles.get("extraa_cards")
    assert Profile.from_dict(profile.to_dict()) == profile


def test_unknown_renderer_is_refused():
    with pytest.raises(ProfileError, match="unknown renderer"):
        Profile(**{**GOOD, "renderer": "does_not_exist"})


def test_renderer_cannot_be_an_import_path():
    """Profile data must never be able to name arbitrary code."""
    with pytest.raises(ProfileError, match="unknown renderer"):
        Profile(**{**GOOD, "renderer": "os.system"})
    with pytest.raises(ProfileError, match="unknown renderer"):
        Profile(**{**GOOD, "renderer": "qrgen.renderers.standard"})


def test_template_referencing_an_undeclared_column_is_refused():
    with pytest.raises(Exception, match="unknown column"):
        Profile(**{**GOOD, "qr_content": "https://x.test/{secret}"})


@pytest.mark.parametrize("filename", [
    "../{qr_code}.png", "out/{qr_code}.png", "a\\b{qr_code}.png",
])
def test_path_shaped_filename_template_is_refused(filename):
    with pytest.raises(ProfileError, match="filename template containing"):
        Profile(**{**GOOD, "filename": filename})


def test_unknown_field_is_refused():
    with pytest.raises(ProfileError, match="unknown profile field"):
        Profile.from_dict({**GOOD, "on_generate": "rm -rf /"})


def test_no_columns_is_refused():
    with pytest.raises(ProfileError, match="no input columns"):
        Profile(**{**GOOD, "required_columns": ()})


def test_validating_an_undeclared_column_is_refused():
    with pytest.raises(ProfileError, match="does not require"):
        Profile(**{**GOOD, "validation": {"phone": {"length": 10}}})


def test_unsupported_output_format_is_refused():
    with pytest.raises(ProfileError, match="unsupported output format"):
        Profile(**{**GOOD, "output_format": "tiff"})


def test_profile_is_immutable():
    profile = profiles.get("extraa_cards")
    with pytest.raises(Exception):
        profile.qr_content = "https://evil.test/{qr_code}"


def test_missing_profile_lists_what_exists():
    with pytest.raises(ProfileError, match="available: \\['extraa_cards'\\]"):
        profiles.get("nope")
