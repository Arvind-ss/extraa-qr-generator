"""Differential test: the extracted renderer vs the frozen reference script.

This is the Stage 3 gate. ``legacy/qr_gen_3.py`` is the script support has been
running; ``qrgen.renderers.standard`` is the lift of it. For every input below
both must produce identical bytes. If this file goes red, the refactor changed
what the support team ships -- fix the renderer, never this test.
"""

import importlib.util
import os
import sys
import types

import pytest

from qrgen.renderers import standard
from qrgen.renderers.standard import create_caption_image, generate_qr_code

LEGACY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "legacy", "qr_gen_3.py")


def _load_legacy():
    # The reference imports pandas at module scope but only uses it inside
    # main(), which nothing here calls. Stub it so the frozen script stays
    # loadable without dragging pandas into the app's dependency set.
    sys.modules.setdefault("pandas", types.ModuleType("pandas"))
    spec = importlib.util.spec_from_file_location("legacy_qr_gen_3", LEGACY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


legacy = _load_legacy()


@pytest.fixture(autouse=True)
def historical_font_sizes(monkeypatch):
    """The frozen script hardcodes 36/60.

    The current renderer defaults to 48/80 by request, so these tests pin it
    back. That is the point: the renderer must still be able to reproduce every
    card already shipped, byte for byte.
    """
    monkeypatch.setattr(standard, "NAME_FONT", "rob_batch.ttf")
    monkeypatch.setattr(standard, "CODE_FONT", "rob_batch.ttf")
    monkeypatch.setattr(standard, "NAME_SIZE", 36)
    monkeypatch.setattr(standard, "CODE_SIZE", 60)


# (qr_content, bottom_text, top_text)
CASES = [
    # The rows that produced the on-disk reference batches.
    ("https://www.extraacards.com/cards/RDFXRN", "RDFXRN", "26-B0008-1"),
    ("https://www.extraacards.com/cards/3YDNGV", "3YDNGV", "26-B0004-500"),
    ("https://www.extraacards.com/cards/036315", "036315", "26-B0123-3331"),
    # No top row -- the POS / Zomato / legacy shape, 600x600 output.
    ("Inai_001", "Inai_001", None),
    ("https://www.extraacards.com/cards/ABC123", "ABC123", None),
    # Names that wrap: the tracking-aware wrap path and the multi-line layout.
    ("https://www.extraacards.com/cards/B0007X", "B0007X",
     "Coimbatore Central Flagship Store"),
    ("https://www.extraacards.com/cards/ZYG5J4", "ZYG5J4",
     "A very long store name that will certainly need three whole lines to fit"),
    # Single character, and a word too long to ever fit (wrap_text emits it anyway).
    ("https://www.extraacards.com/cards/AAAAAA", "AAAAAA", "A"),
    ("https://www.extraacards.com/cards/BBBBBB", "BBBBBB",
     "Supercalifragilisticexpialidociousandthensome"),
    # Caption text that wraps (the untracked path).
    ("https://www.extraacards.com/cards/CCCCCC",
     "A caption long enough to wrap across lines", "Store"),
    # Non-ASCII in the name row.
    ("https://www.extraacards.com/cards/DDDDDD", "DDDDDD", "Café Münster"),
    # QR payloads that push the symbol to a higher version (more modules).
    ("https://www.extraacards.com/cards/" + "X" * 120, "LONGER", "26-B0004-1"),
    ("#GOGAS1", "#GOGAS1", None),
    # Whitespace-padded name: split() drops the padding in both.
    ("https://www.extraacards.com/cards/EEEEEE", "EEEEEE", "   Spaced   Out   "),
]


@pytest.mark.parametrize("qr_content,bottom,top", CASES,
                         ids=[c[1][:18] + ("+" + str(c[2])[:14] if c[2] else "-notop")
                              for c in CASES])
def test_bytes_match_reference(qr_content, bottom, top):
    new = generate_qr_code(qr_content, create_caption_image(bottom, 600, top_text=top))
    ref = legacy.generate_qr_code(
        qr_content, legacy.create_caption_image(bottom, 600, top_text=top))
    assert new == ref, (
        f"renderer diverged from legacy/qr_gen_3.py for {qr_content!r} / "
        f"{bottom!r} / {top!r}: {len(new)} bytes vs {len(ref)}")


@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_blank_text_fails_the_same_way(bad):
    """wrap_text indexes words[0] and blows up on blank text.

    Preserved deliberately: CSV validation rejects blank values long before a
    row reaches the renderer, and quietly rendering an empty caption would ship
    a card with no code printed on it.
    """
    with pytest.raises(IndexError):
        create_caption_image(bad, 600)
    with pytest.raises(IndexError):
        legacy.create_caption_image(bad, 600)


def test_qr_width_argument_is_ignored():
    """The second parameter has never done anything. Zomato passed 400."""
    a = create_caption_image("ABC123", 600, top_text="Store")
    b = create_caption_image("ABC123", 400, top_text="Store")
    assert a.tobytes() == b.tobytes()


def test_caption_geometry_is_unchanged():
    """Pins the measured constants so a Pillow bump that shifts metrics is loud."""
    assert create_caption_image("RDFXRN", 600, top_text="26-B0008-1").size == (600, 170)
    assert create_caption_image("RDFXRN", 600).size == (600, 93)
    assert create_caption_image(
        "B0007X", 600, top_text="Coimbatore Central Flagship Store").size == (600, 222)
