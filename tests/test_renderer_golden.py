"""Golden-image tests against real cards the support team already shipped.

The differential test proves the lift is faithful to the script. This proves
the *environment* still produces the same pixels -- a Pillow or qrcode bump
shows up here first. Measured: Pillow 10.1.0 vs 11.3.0 moves 131 pixels on a
660x660 card. Byte equality is the gate; the pixel report is the diagnostic.

Do not regenerate the fixtures to make this pass. If it goes red, find out
which dependency moved.
"""

import hashlib
import io
import json
import os

import pytest
from PIL import Image, ImageChops

from qrgen.renderers import standard
from qrgen.renderers.standard import render

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden")
MANIFEST = json.load(open(os.path.join(GOLDEN, "manifest.json")))


@pytest.fixture(autouse=True)
def historical_font_sizes(request, monkeypatch):
    """Every reference image here was printed at the original 36/60.

    Tests marked ``current_sizes`` opt out -- those check what the renderer
    does today rather than what it must still be able to reproduce.
    """
    if "current_sizes" in request.keywords:
        return
    monkeypatch.setattr(standard, "NAME_FONT", "rob_batch.ttf")
    monkeypatch.setattr(standard, "CODE_FONT", "rob_batch.ttf")
    monkeypatch.setattr(standard, "NAME_SIZE", 36)
    monkeypatch.setattr(standard, "CODE_SIZE", 60)

# Entries tagged "standard_v1" were produced by the older qr_gen.py renderer,
# which cropped to a fixed 600x640 instead of padding to a square. They are kept
# as evidence and as the corpus for that renderer if it is ever migrated -- they
# are NOT expected to match the current one. See docs/PROFILE_MAPPING.md.
CURRENT = [c for c in MANIFEST if c["renderer"] == "standard"]


def _diff_report(new_bytes, ref_path):
    a = Image.open(io.BytesIO(new_bytes)).convert("RGB")
    b = Image.open(ref_path).convert("RGB")
    if a.size != b.size:
        return f"size differs: {a.size} vs {b.size}"
    bbox = ImageChops.difference(a, b).getbbox()
    if bbox is None:
        return ("pixels identical, encoded bytes differ -- JPEG encoder changed, "
                "not the rendering")
    changed = sum(1 for p in ImageChops.difference(a, b).convert("L").getdata() if p)
    return f"{changed} pixels differ, bbox {bbox}"


@pytest.mark.parametrize("case", CURRENT, ids=[c["file"] for c in CURRENT])
def test_matches_shipped_card(case):
    out = render(case["qr_content"], case["bottom_text"], top_text=case["top_text"])
    if hashlib.sha256(out).hexdigest() == case["sha256"]:
        return
    pytest.fail(f"{case['file']} ({case['note']}): "
                f"{_diff_report(out, os.path.join(GOLDEN, case['file']))}")


# Opt-in sweep over the full ~2,250-image corpus, which is far too large to
# commit. Point EXTRAA_GOLDEN_DIR at the old working directory to run it:
#   EXTRAA_GOLDEN_DIR=~/Extraa/scriptcodes/qr_gen pytest tests/test_renderer_golden.py
CORPUS = os.environ.get("EXTRAA_GOLDEN_DIR")


@pytest.mark.skipif(not CORPUS, reason="set EXTRAA_GOLDEN_DIR to run the full corpus")
@pytest.mark.parametrize("batch", ["B0004", "B0005", "B0006", "B0007"])
def test_full_batch_corpus(batch):
    import csv

    src = os.path.join(CORPUS, batch)
    with open(os.path.join(src, f"{batch}.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))

    checked, mismatches = 0, []
    for row in rows:
        ref = os.path.join(src, row["qr_code"] + ".png")
        if not os.path.exists(ref):
            continue
        out = render("https://www.extraacards.com/cards/" + row["qr_code"],
                     row["qr_code"], top_text=row["name"])
        checked += 1
        if hashlib.sha256(out).hexdigest() != hashlib.sha256(
                open(ref, "rb").read()).hexdigest():
            mismatches.append(f"{row['qr_code']}: {_diff_report(out, ref)}")

    assert checked, f"no reference images found in {src}"
    assert not mismatches, (f"{len(mismatches)}/{checked} cards differ in {batch}:\n"
                            + "\n".join(mismatches[:10]))


# --- current defaults -------------------------------------------------------
# The fixtures above deliberately pin 36/60, the sizes every shipped card was
# printed at. These check what the renderer does *today*, so an accidental
# change to NAME_SIZE/CODE_SIZE is caught as loudly as a Pillow bump.

@pytest.mark.current_sizes
def test_current_printed_style():
    assert (standard.NAME_SIZE, standard.CODE_SIZE) == (48, 80)
    assert (standard.NAME_FONT, standard.CODE_FONT) == ("rob.ttf", "rob.ttf")


@pytest.mark.current_sizes
def test_current_card_geometry():
    card = Image.open(io.BytesIO(render(
        "https://www.extraacards.com/cards/RDFXRN", "RDFXRN",
        top_text="26-B0008-1"))).convert("L")
    assert card.size == (697, 697)

    # The QR itself must be untouched by a caption change: the caption is
    # pasted at a fixed y and grows downward, so it can never reach the modules.
    pixels = card.load()
    first_ink = next(y for y in range(card.height)
                     if any(pixels[x, y] < 128 for x in range(card.width)))
    assert first_ink == 15, "the QR's quiet zone moved"

    # No top row: one text line instead of two, so still square and still
    # driven only by the caption -- 606 rather than the old 600 because
    # Roboto's line box is taller than Geist Mono's.
    plain = Image.open(io.BytesIO(render(
        "Inai_001", "Inai_001"))).convert("L")
    assert plain.size == (606, 606)


@pytest.mark.current_sizes
def test_font_name_cannot_escape_the_bundled_directory():
    """A profile supplies this filename, so it must never be a path."""
    from qrgen.renderers.standard import FontLoadError, _font
    for bad in ("../../etc/passwd", "/etc/passwd", "sub/dir.ttf", ".hidden"):
        with pytest.raises(FontLoadError):
            _font(bad, 12)


@pytest.mark.current_sizes
def test_bundled_fonts_are_listed():
    assert standard.available_fonts() == ["rob.ttf", "rob_batch.ttf"]


@pytest.mark.current_sizes
def test_startup_selftest_passes_here():
    """The hash the packaged app checks itself against must be a real one."""
    from qrgen import selftest
    assert selftest.check() == selftest.EXPECTED


@pytest.mark.current_sizes
def test_startup_selftest_catches_a_broken_font(monkeypatch):
    """The failure it exists for: a font that did not make it into the bundle."""
    from qrgen import selftest
    from qrgen.renderers import standard

    monkeypatch.setattr(standard, "_assets_dir", lambda: "/nonexistent")
    with pytest.raises(selftest.SelfTestError, match="could not be rendered"):
        selftest.check()


@pytest.mark.current_sizes
def test_startup_selftest_catches_wrong_output(monkeypatch):
    """And the quieter failure: it renders, but not the right thing."""
    from qrgen import selftest

    monkeypatch.setitem(selftest.REFERENCE["style"], "name_size", 37)
    with pytest.raises(selftest.SelfTestError, match="does not render"):
        selftest.check()
