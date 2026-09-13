"""The standard Extraa QR card renderer.

Verbatim lift of the rendering half of ``legacy/qr_gen_3.py``. Byte-for-byte
output parity with that reference script is the contract, enforced by
``tests/test_renderer_differential.py``.

Do not "fix" anything in here. The odd values are all load-bearing:

* ``qr_width`` is accepted and ignored -- every width below is hardcoded to
  600/580 regardless of what the caller passes.
* The QR is pasted at y=-10, so its top 10px are discarded.
* The caption is pasted over the QR's bottom 80px, then the whole thing is
  cropped from y=40.
* Output is JPEG bytes, which callers write into files named ``.png``.

Only two things differ from the reference, both deliberate and both recorded
in the Stage 3 notes:

1. Fonts resolve through :func:`_font` so they survive PyInstaller bundling.
   The file loaded is byte-identical to ``legacy/rob_batch.ttf``.
2. A font that fails to load raises instead of silently falling back to
   Pillow's default bitmap font. The reference printed a warning and carried
   on, which produces cards that are wrong in a way nobody notices until
   they are printed.
"""

import os
import sys
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
import qrcode

from qrgen import paths


# Printed text sizes. Changed from 36/60 on 2026-09-13 by request; see
# docs/PROFILE_MAPPING.md. Everything else about the renderer is untouched, and
# the golden tests still pin these back to 36/60 to prove the ~2,000 cards
# already shipped can still be reproduced byte-for-byte.
# Typeface, by filename inside assets/fonts. The historical cards were printed
# in rob_batch.ttf, which despite the name is Geist Mono Light; rob.ttf is
# Roboto Regular. Changed to Roboto on 2026-09-13 by request.
NAME_FONT = "rob.ttf"
CODE_FONT = "rob.ttf"

NAME_SIZE = 48
CODE_SIZE = 80

# Letter-spacing, in pixels. Only the name row has ever used it.
NAME_TRACKING = 5
CODE_TRACKING = 0

# The two sizes have always been in a 5:3 ratio (36/60, and now 48/80), so one
# number drives both unless a profile overrides the code size explicitly.
SIZE_RATIO = 5 / 3


class FontLoadError(RuntimeError):
    """The bundled font could not be loaded, so output cannot match golden."""


def _assets_dir():
    return paths.resource("assets", "fonts")


def _font(name, size):
    # A profile supplies this name, so it must be a bare filename inside the
    # bundled font directory and nothing else -- never a path.
    if os.path.basename(name) != name or name.startswith("."):
        raise FontLoadError(f"{name!r} is not a bundled font name")
    path = os.path.join(_assets_dir(), name)
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError) as exc:
        raise FontLoadError(f"could not load bundled font {path!r}: {exc}") from exc


def get_text_dimensions(text, font):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(text, font, max_width, tracking=0):
    words = text.split()
    lines = []
    current_line = words[0]

    for word in words[1:]:
        candidate = current_line + ' ' + word
        width, _ = get_text_dimensions(candidate, font)
        width += tracking * (len(candidate) - 1)  # letter-spacing counts toward the line
        if width <= max_width:
            current_line += ' ' + word
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


def create_caption_image(caption_text, qr_width, top_text=None, name_size=None,
                         code_size=None, name_tracking=None, code_tracking=None,
                         name_font=None, code_font=None):
    """Build the text block that sits under the QR.

    The four style arguments default to the module constants, so every existing
    caller -- and the golden tests, which pin those constants back to the
    historical 36/60 -- behaves exactly as before.
    """
    name_size = NAME_SIZE if name_size is None else name_size
    code_size = CODE_SIZE if code_size is None else code_size
    name_tracking = NAME_TRACKING if name_tracking is None else name_tracking
    code_tracking = CODE_TRACKING if code_tracking is None else code_tracking
    name_font = NAME_FONT if name_font is None else name_font
    code_font = CODE_FONT if code_font is None else code_font

    caption_font = _font(code_font, code_size)  # the code, lower row
    batch_font = _font(name_font, name_size)    # the name, upper row

    rendered_items = []  # List of tuples: (line_text, font, line_height, stroke, tracking)
    top_pad = 25 if top_text else 0  # breathing room between the QR and the name

    if top_text:
        batch_lines = wrap_text(top_text, batch_font, 580, tracking=name_tracking)
        b_bbox = batch_font.getbbox('hg')
        b_height = (b_bbox[3] - b_bbox[1]) + 20
        for line in batch_lines:
            rendered_items.append((line, batch_font, b_height, 1, name_tracking))  # stroke=1 -> faux bold

    caption_lines = wrap_text(caption_text, caption_font, 580,
                              tracking=code_tracking)
    c_bbox = caption_font.getbbox('hg')
    c_height = (c_bbox[3] - c_bbox[1]) + 40
    for line in caption_lines:
        rendered_items.append((line, caption_font, c_height, 0, code_tracking))

    caption_height = sum(item[2] for item in rendered_items) + top_pad

    caption_image = Image.new('RGB', (600, caption_height), color='white')
    draw = ImageDraw.Draw(caption_image)

    y = top_pad
    for line, font, h, stroke, tracking in rendered_items:
        if tracking:
            text_width = (sum(draw.textlength(c, font=font) for c in line)
                          + tracking * (len(line) - 1))
            x = (600 - text_width) / 2
            for ch in line:  # draw per character to apply letter-spacing
                draw.text((x, y), ch, font=font, fill='black',
                          stroke_width=stroke, stroke_fill='black')
                x += draw.textlength(ch, font=font) + tracking
        else:
            bbox = font.getbbox(line)
            x = (600 - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font, fill='black',
                      stroke_width=stroke, stroke_fill='black')
        y += h

    return caption_image


def generate_qr_code(link, caption):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )

    qr.add_data(link)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.resize((600, 600))

    qr_img_with_caption = Image.new('RGB', (qr_img.width, qr_img.height + caption.height), color='white')
    # default value 20 curr:(-10)
    qr_img_with_caption.paste(qr_img, (0, -10))
    # daflaut value -18 ---> curr(80)
    qr_img_with_caption.paste(caption, ((qr_img.width - caption.width) // 2, qr_img.height - 80))
    qr_img_with_caption = qr_img_with_caption.crop((0, 40, 600, qr_img.height - 80 + caption.height + 10))

    # pad (never scale) to a perfect square so the QR is not resampled
    side = max(qr_img_with_caption.size)
    square = Image.new('RGB', (side, side), color='white')
    square.paste(qr_img_with_caption,
                 ((side - qr_img_with_caption.width) // 2,
                  (side - qr_img_with_caption.height) // 2))
    qr_img_with_caption = square

    img_byte_array = BytesIO()
    qr_img_with_caption.save(img_byte_array, format='JPEG')
    return img_byte_array.getvalue()


def render(qr_content, bottom_text, top_text=None, **style):
    """Render one card and return its encoded bytes.

    The single entry point the generation engine calls. Thin wrapper over the
    two reference functions above, kept separate so the lifted code stays a
    literal copy. ``style`` carries name_size / code_size / name_tracking /
    code_tracking; anything omitted falls back to the module constants.
    """
    caption = create_caption_image(bottom_text, 600, top_text=top_text, **style)
    return generate_qr_code(qr_content, caption)


def code_size_for(name_size):
    """The code size that keeps the historical 5:3 proportion."""
    return round(name_size * SIZE_RATIO)


def available_fonts():
    """Font filenames that ship with the app, for the profile editor."""
    try:
        return sorted(n for n in os.listdir(_assets_dir())
                      if n.lower().endswith((".ttf", ".otf")))
    except OSError:
        return []
