"""Startup check: does this build still render a known card correctly?

A packaged application can fail in ways no test catches, because the tests run
from a source checkout. The font may not have been bundled. Pillow may have
been swapped. The frozen archive may resolve ``assets/`` somewhere unexpected.
Every one of those produces cards that look plausible and are wrong, and nobody
notices until fifty thousand of them have been printed.

So the app renders one known row at startup and compares it to a hash recorded
here. A mismatch stops the application from opening, which is a far better
outcome than a batch nobody can trust.

The row is the Brigade reference card, rendered with the typeface and sizes it
was actually printed with, so this hash is the same one
``tests/golden/manifest.json`` asserts.
"""

import hashlib

REFERENCE = {
    "qr_content": "https://www.extraacards.com/cards/RDFXRN",
    "bottom_text": "RDFXRN",
    "top_text": "26-B0008-1",
    "style": {"name_font": "rob_batch.ttf", "code_font": "rob_batch.ttf",
              "name_size": 36, "code_size": 60, "name_tracking": 5,
              "code_tracking": 0},
}
EXPECTED = "5aa5be7844b0266c60b7510e1eca79516a26426734451b9da9bd7bdde38688b3"


class SelfTestError(RuntimeError):
    """This build does not render the reference card correctly."""


def check():
    """Raise :class:`SelfTestError` if this build renders incorrectly."""
    from qrgen.renderers import standard

    try:
        image = standard.render(REFERENCE["qr_content"],
                                REFERENCE["bottom_text"],
                                top_text=REFERENCE["top_text"],
                                **REFERENCE["style"])
    except Exception as exc:
        raise SelfTestError(
            f"the reference card could not be rendered at all: "
            f"{type(exc).__name__}: {exc}") from exc

    actual = hashlib.sha256(image).hexdigest()
    if actual != EXPECTED:
        raise SelfTestError(
            "this build does not render the reference card correctly.\n"
            f"  expected  {EXPECTED}\n"
            f"  produced  {actual}\n"
            "The most likely causes are a font that was not bundled, or a "
            "Pillow version other than the pinned one. Generating cards from "
            "this build would produce output that does not match what has "
            "already been printed.")
    return actual
