# Themes

Four palettes live in `assets/theme.json`. They ship with the app, so they can
be edited without touching Python — change the file and restart.

| Mode | Background | Text | Character |
|---|---|---|---|
| `mono` | `#ffffff` | `#0a0a0a` | Monochrome, paper-white. |
| `monoDark` | `#0a0a0a` | `#f5f5f5` | Monochrome, terminal-dark. **Default.** |
| `light` | `#f5f5ff` | `#2a2a4a` | Violet accent, from the supplied token file. |
| `dark` | `#0f0f1a` | `#e2e2f5` | Violet accent, dark. |

Switch without editing anything:

```bash
EXTRAA_QR_THEME=monoDark .venv/bin/python main.py
```

Or set `MODE` in `ui/theme.py` to change the default.

## What is derived rather than declared

`BORDER_STRONG`, `TEXT_3`, `ACCENT_DEEP`, `ACCENT_HOVER`, `ACCENT_PRESSED` and
the four tints are computed from the declared colours, so a new palette only
needs the shadcn token set and they follow.

Two rules are enforced by tests, in every palette:

* **Every status colour clears WCAG AA.** `readable()` walks a colour toward
  the text colour until it does, preserving hue. A mint green that reads 1.77:1
  on white is present and invisible, and it is the line that says whether a
  batch is safe to run.
* **The progress gradient and the hover state must actually differ from the
  accent.** In a monochrome palette the accent *is* the text, so anything
  derived by blending the two collapses to a flat bar and an invisible hover.

## What no palette may change

The **preview well** behind the sample card is always a neutral grey, chosen by
the background's luminance: `#8A8A90` on light, `#2E2E33` on dark. It is never
tinted, never white, never black. The card is white-edged and destined for
print — a tinted surround casts colour onto the white, a white one hides the
card's boundary, and a black one exaggerates its contrast. None of those let
anyone judge the real thing, which is the only visual judgement this
application asks a person to make.

## What no palette can have

Rounded corners, shadows, elevation, blur, or alpha. Tk draws none of them. The
supplied token file's `radius: 0.5rem` and its nine-step `shadows` scale are
read and ignored; tints are pre-blended to flat hex instead of using opacity.
