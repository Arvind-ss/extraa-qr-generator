import pytest

from qrgen import templates


def test_resolves_tokens():
    row = {"name": "John Doe", "qr_code": "ABC123"}
    assert templates.resolve("https://x.test/{qr_code}", row) == "https://x.test/ABC123"
    assert templates.resolve("{name} - {qr_code}", row) == "John Doe - ABC123"
    assert templates.resolve("no tokens here", row) == "no tokens here"


def test_tokens_found():
    assert templates.tokens("{a}/{b}{a}") == {"a", "b"}
    assert templates.tokens("literal") == set()


@pytest.mark.parametrize("template", [
    "{0}",                  # positional
    "{a.b}",                # attribute access
    "{a!r}",                # conversion
    "{a:>10}",              # format spec
    "{ a }",                # spaces
    "{}",                   # empty
    "{__class__}",
])
def test_format_string_syntax_is_inert(template):
    """Only bare {name} is a token. Everything str.format understands is literal.

    This is the whole reason we do not use str.format: {x.__class__.__init__
    .__globals__} would hand a profile author the process internals.
    """
    assert templates.tokens(template) in (set(), {"__class__"})
    row = {"a": "VALUE", "__class__": "X"}
    if template != "{__class__}":
        assert templates.resolve(template, row) == template


def test_attribute_traversal_cannot_reach_internals():
    row = {"qr_code": "ABC123"}
    assert templates.resolve("{qr_code.__class__}", row) == "{qr_code.__class__}"


def test_missing_column_is_a_clear_error():
    with pytest.raises(templates.TemplateError, match="needs column 'name'"):
        templates.resolve("{name}", {"qr_code": "ABC123"})


def test_none_becomes_empty_string():
    assert templates.resolve("[{name}]", {"name": None}) == "[]"


def test_check_rejects_undeclared_columns():
    templates.check("{qr_code}.png", ["qr_code"], "filename")
    with pytest.raises(templates.TemplateError, match="unknown column"):
        templates.check("{secret}.png", ["qr_code"], "filename")


def test_check_rejects_non_text():
    with pytest.raises(templates.TemplateError, match="must be text"):
        templates.check(42, ["qr_code"], "filename")
