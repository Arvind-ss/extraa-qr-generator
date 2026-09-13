# UI mockup prompt — dark theme, Tkinter-buildable

Copy everything below the line into your mockup tool. It is self-contained.

**Toolkit:** Python Tkinter/ttk using the `clam` theme, which accepts colour on
every widget and renders identically on macOS and Windows. Everything specified
below is reachable with `ttk.Style` plus a `tk.Canvas` for the two gradients.

---

## PROMPT

Design high-fidelity mockups for **Extraa QR Generator** — an internal desktop
application used by an event-tech company's support team to generate large
batches of QR-code card images from CSV files.

### Visual direction

A **dark, flat, typographic desktop instrument.** Apple's Human Interface
principles, executed under severe rendering constraints.

The three principles, and what each means here:

- **Deference** — the interface recedes so the content leads. The only real
  content in this app is the generated QR card. On the Review screen it is the
  brightest object on the display and everything else steps back.
- **Clarity** — hierarchy comes from type weight, size and spacing, never from
  boxes and colour. Ruthless legibility; nothing decorative competes with
  anything functional.
- **Depth** — layering is shown by surface lightness stepping up in small
  increments and by 1px hairlines. Nothing else.

Because rounded corners, shadows and translucency are all unavailable, the
design must be carried entirely by **spacing, type hierarchy, hairlines and a
disciplined palette**. Closer to Sublime Text or a good terminal UI than to a
web dashboard. If a surface, border or colour is not carrying information,
remove it. Restraint is the aesthetic.

### Hard rendering constraints — these are physical, not stylistic

The toolkit **cannot** render, and the mockup must not contain:

- **Rounded corners.** Every rectangle is square. Radius 0 everywhere, with no
  exceptions — no pills, no rounded chips, no rounded buttons.
- **Shadows, glows, elevation blur, or frosted/glass effects.**
- **Alpha or translucency of any kind.** Every colour is a flat opaque hex. A
  "12% tint" must be given as a pre-blended solid value.
- **Gradients anywhere except the two specified below**, each of which is drawn
  on a dedicated canvas band.
- **Custom or downloaded fonts.** Only fonts already on the OS: the system UI
  face (SF Pro on macOS, Segoe UI on Windows) and the system monospace face (SF
  Mono, Consolas). Do not use Inter, Geist, or any web font.
- Icon fonts, SVG, illustration, or animation.

### Platform

Native desktop application for macOS and Windows. Window **1080 × 720px**,
resizable, minimum 960 × 660. Not a website. No browser chrome, no responsive or
mobile layout.

### Who uses it

Internal support staff repeating the same task several times a week. Batches are
typically 1,000–2,000 rows; the largest is 50,000, taking about three minutes.
They are not designers or developers. Two roles: **support** (generate only) and
**admin / support lead** (generate + manage profiles).

---

## DESIGN TOKENS — use exactly

### Surfaces and text

| Token | Value | Use |
|---|---|---|
| `bg-base` | `#0B0A10` | Window background |
| `surface-1` | `#131120` | Panels, tables, grouped content |
| `surface-2` | `#1B1829` | Inputs, selected rows, hover |
| `surface-3` | `#241F36` | Pressed, active row |
| `border` | `#272338` | Default hairline, 1px |
| `border-strong` | `#3A3350` | Focus, selection, emphasis |
| `text-primary` | `#F2F0F7` | Headings, values |
| `text-secondary` | `#A29DB5` | Labels, captions |
| `text-tertiary` | `#6A657A` | Hints, disabled |

### Accents

| Token | Value | Use |
|---|---|---|
| `accent` | `#8B5CF6` | Primary action, current step |
| `accent-deep` | `#4C2B83` | Gradient ends only |
| `attention` | `#FCB712` | Warnings, offline |
| `success` | `#34D399` | Verification passed |
| `error` | `#F87171` | Failures |

The brand colours are `#4C2B83` (purple) and `#FCB712` (amber). `#4C2B83` is too
dark to read as an accent on a near-black background, so `accent` is the same
hue lifted; `#4C2B83` survives only as the deep end of the two gradients. Purple
and amber are the only hues besides semantic green and red.

### Pre-blended tint fills — use these solid values, never opacity

| Use | Value |
|---|---|
| Accent tint on `surface-1` | `#291F47` |
| Success tint on `surface-1` | `#193436` |
| Error tint on `surface-1` | `#3C222F` |
| Attention tint on `surface-1` | `#3D2F1D` |

These stand in for what would be a 18% overlay. They are flat fills.

### The only two gradients

1. **Header band** — a 104px-tall canvas spanning the window width behind the
   title strip and step rail, filled with a vertical gradient from `#1A1430` at
   the top to `#0B0A10` at the bottom. Subtle; it should read as depth, not as a
   coloured header.
2. **Progress fill** — the filled portion of the progress bar, a horizontal
   gradient from `#4C2B83` to `#8B5CF6`.

No other gradient anywhere. Buttons are flat fills.

### Type — system fonts only

| Role | Spec |
|---|---|
| Display | System UI, 26px, semibold |
| Heading | System UI, 18px, semibold |
| Body | System UI, 14px, regular |
| Label | System UI, 12px, medium, `text-secondary` |
| Caption | System UI, 12px, regular, `text-secondary` |
| Micro-header | System UI, 11px, semibold, letter-spaced, `text-tertiary`, UPPERCASE |
| **Mono** | System monospace, 13px, regular |

**Every QR code, URL, filename and `{template}` string is monospace.** This is
functional, not stylistic: support staff compare these values against
spreadsheets by eye, and in a proportional typeface `0/O` and `1/l/I` are
indistinguishable. Everything else is proportional.

### Geometry and spacing

- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48px. Prefer the larger option —
  generous negative space is doing the work that shadows and radius would.
- **Radius: 0 on everything.**
- Borders: always exactly 1px, `border`, unless emphasis needs `border-strong`.
- Elevation: shown only by stepping `surface-1` → `surface-2` → `surface-3`.
- Content column: centred, max width 820px.

### Interaction states

Every interactive element needs: default, hover (`surface-2`), focus (1px
`accent` border), pressed (`surface-3`), disabled (`text-tertiary` text on
`surface-1`, no border emphasis). Show at least one hover and one focus somewhere
in the deliverable. Focus is a **border colour change**, never a soft ring.

---

## PERSISTENT CHROME (every screen except Sign in)

Sitting on the gradient header band:

- **Title strip, 48px:** left, app name in Heading. Right: `support@example.com`
  in Caption, a `·`, then a role tag (`SUPPORT` / `ADMIN`) as a **square** 20px
  tag in `surface-2` with a 1px `border`, micro-header type — then a `Sign out`
  text button in `text-secondary`.
- **Step rail, 56px:** `① Profile · ② Upload · ③ Review · ④ Generate`, centred.
  Current step: `text-primary` with a filled square `accent` numeral tile.
  Completed: `text-secondary` with a `success` tile showing `✓`. Upcoming:
  `text-tertiary` with a `surface-2` tile and a 1px `border`. Connectors are 1px
  `border` lines. This rail exists to make it visually obvious that the Review
  step cannot be skipped.
- **Action bar, 68px**, flat `bg-base`, 1px `border` top edge. Connection status
  bottom-left: a 6px **square** dot plus Caption. Buttons bottom-right, in the
  same position on every screen.

Button hierarchy — all square, 34px tall, 20px horizontal padding:
**primary** = flat `accent` fill, `#0B0A10` text, semibold.
**secondary** = `surface-2` fill, 1px `border`, `text-primary`.
**tertiary** = text only, `text-secondary`, no fill or border.
**Exactly one primary button per screen.**

Never signal state by colour alone — always pair with a `✓ ✗ !` glyph and a word.
A `Failed 0` counter is never red; red appears only above zero.

---

## SCREENS

Design all eight. Use the real sample data given — no lorem ipsum, no invented
brand names, no placeholder avatars.

### 1. Sign in

Full-bleed `bg-base`. The gradient band is taller here — the top 45% of the
window. Centred panel, 380px wide, `surface-1`, 1px `border`, 40px padding,
square.

App name in Display, one Caption line: `Internal QR generation tool`. Two
fields, `Email` and `Password`, Label above a 38px input (`surface-2`, 1px
`border`). One primary button, full width: `Sign in`. Nothing else — no
forgot-password, no remember-me, no social login, no illustration, no logo mark.

**Error variant:** both inputs take a 1px `error` border and the line
`✗ Incorrect email or password` in `error` appears below them.

### 2. Dashboard

Two panels side by side, each ~360 × 180px, `surface-1`, 1px `border`, 24px
padding. Heading, a Caption line, and a `›` in `text-secondary` bottom-right.
Hover state lifts the fill to `surface-2` and the border to `border-strong`.

- **Generate QR codes** — `Upload a CSV and produce a batch of cards`
- **Profile management** — `Create and edit generation profiles`

Show **two variants**: as admin (both active), and as support (Profile
management with `text-tertiary` text throughout and the Caption
`Admin access required`).

No step rail on this screen.

### 3. Generate — profile and file

Three sections separated by 32px and a 1px `border` rule.

**PROFILE** (micro-header). A 38px select, `surface-2`, showing `Extraa Cards`.
Beneath it a `surface-1` panel with 20px padding and a two-column definition
list — labels in Label style, values in **mono**:
```
Required columns   name, qr_code
QR content         https://www.extraacards.com/cards/{qr_code}
Top text           {name}
Bottom text        {qr_code}
Filename           {qr_code}.png
```

**INPUT FILE.** A 110px drop zone: 1px **dashed** `border`, `surface-1` fill,
centred `Drop a CSV here` in Body plus `or choose a file` as a tertiary button.
Then show the **filled state** instead: a `surface-1` row with a mono filename
`B0004.csv`, a Caption `500 rows · 24 KB`, and a right-aligned `Replace`
tertiary button.

**VALIDATION.** A single line: `✓ 500 rows, no errors` in `success`.

Primary button: `Generate sample`.

**Second version of this screen, with failures:**
- `✗ 3 of 500 rows have errors` in `error`.
- A table in a `surface-1` panel with a 1px `border`: micro-header header row on
  `surface-2`, 1px `border` row separators, 38px rows. Columns
  `Row | QR code | Error`; the first two mono:
```
  12   ABC12      qr_code must be exactly 6 characters, got 5
  89   XY-Z45     qr_code must be alphanumeric; found '-'
 204   RDFXRN     duplicate qr_code 'RDFXRN', already used by row 17
```
- Below: Caption `Showing 3 of 3 errors` and a `Copy all` tertiary button.
- The primary button is **disabled**, with the Caption `Fix the input file to
  continue` beside it.

### 4. Review sample — the hero screen

This screen decides whether 50,000 cards are correct. It should be the most
composed screen in the set.

Two columns, 40 / 60 split.

**Left** — a definition list, 24px vertical rhythm, Label above value:
```
Profile         Extraa Cards
Name            26-B0008-1                                  (mono)
QR code         RDFXRN                                      (mono)
Expected URL    https://www.extraacards.com/cards/RDFXRN    (mono, wraps)
Filename        RDFXRN.png                                  (mono)
```

**Right** — the card preview, the brightest object on the screen:
- A square **preview well**, ~400 × 400px, flat fill `#2E2E33`, 1px `border`,
  20px internal padding. Square corners.
- Inside it the generated card: a **white square** containing a black QR code
  with two centred black text lines beneath — a small bold letter-spaced
  `26-B0008-1` above, a larger `RDFXRN` below.
- **The well must be neutral grey `#2E2E33`, not purple-tinted and not
  near-black.** The card is white-edged and destined for print; a tinted
  surround casts colour onto the white and a black surround exaggerates its
  contrast, so neither lets anyone judge the real thing. This is the one place
  in the interface where the dark purple palette is deliberately suspended.
- Below the well: `✓ QR decodes to the expected value` in `success`, and an
  `Open full size` tertiary button.

Action bar: `Cancel` (tertiary), `Regenerate` (secondary), **`Approve & generate`**
(primary — the only `accent` button on screen). It must **not** render focused
or highlighted by default: this is the irreversible commit point and must not be
triggerable by a stray Enter key.

### 5. Generating

No step navigation available. Centred column, 620px.

Heading `Generating QR codes`. A 8px-tall progress track, `surface-2`, square,
filled ~70% with the progress gradient. Under it, a baseline-aligned row:
`34,820 / 50,000` in 20px mono on the left, `70%` in `text-secondary` right.

Below, a four-cell stat grid in a `surface-1` panel with 1px `border`, cells
divided by 1px `border` lines — each cell a micro-header above a 20px mono
value:
```
SUCCESSFUL    34,815    │    REMAINING     ~1m 10s
──────────────────────────────────────────────────
FAILED             5    │    THROUGHPUT    210 / sec
```
`FAILED` value in `error`. Beneath the panel, a Caption:
`Rendering with 9 worker processes`.

Action bar: a single `Cancel` secondary button. **No primary button.**

**Zero-failure variant:** `FAILED 0` in `text-primary`, not red.

### 6. Complete

A 40px `✓` in `success` above a Display `Generation complete`. A `surface-1`
summary panel with 1px `border`, values mono and right-aligned:
```
Total          50,000
Successful     49,972
Failed             28
Time           2m 45s
Output         extraa_cards_2026-09-13.zip     2.24 GB
```
`28` in `error`. Below the panel, an attention strip — `#3D2F1D` fill with a 3px
solid `attention` left edge, 12px padding:
`! This archive is 2.24 GB. Allow time to copy or upload it.`

Action bar: `Show error report` (secondary), `Open ZIP` (primary).

**Clean variant:** `Failed 0`, no error-report button, no attention strip.

### 7. Profile management (admin)

Above the table: a 34px search input left (`surface-2`, 1px `border`,
placeholder `Search profiles`), a `New profile` primary button right.

A table in a `surface-1` panel with 1px `border`: micro-header header row on
`surface-2`, 1px `border` row separators, 48px rows, one row selected
(`surface-3` fill with a 3px solid `accent` left edge). Columns
`Profile | Renderer | Version | Status | Updated`:
```
Extraa Cards      standard   v3   Active     2026-09-12 · admin@example.com
Event Ticket      standard   v1   Active     2026-08-30 · admin@example.com
Zomato            standard   v2   Inactive   2026-07-14 · admin@example.com
```
`Renderer` and `Version` mono. Status as a **square** tag: `Active` = `success`
text on `#193436`; `Inactive` = `text-tertiary` on `surface-2`.

Below: `Edit`, `Preview`, `Deactivate` — all secondary, shown disabled until a
row is selected. There is deliberately **no Delete control anywhere**; profiles
are deactivated, never removed.

### 8. Profile editor (admin)

A form in two groups separated by 32px and a 1px `border` rule.

**IDENTITY.** `Profile name` text input. `Required input columns` as a tag
input: **square** `name ×` and `qr_code ×` tags in `surface-2` with 1px
`border`, plus an empty entry.

**TEMPLATES** — all inputs mono:
```
QR content template    https://www.extraacards.com/cards/{qr_code}
Top text template      {name}
Bottom text template   {qr_code}
Filename template      {qr_code}.png
Output format          [select: PNG file (JPEG encoded)]
```

To the right of the template group, a 240px `surface-1` helper panel with 1px
`border`:
```
AVAILABLE VARIABLES
  {name}
  {qr_code}

Only these variables are allowed.
Templates cannot contain code.
```
Variables as **square** mono tags, `accent` text on `#291F47`.

One **inline error** under the filename field:
`✗ Filename template cannot contain "/" or ".."` in `error`, with that input
carrying a 1px `error` border.

Action bar: `Cancel` (secondary), `Save profile` (primary).

---

## STATE VARIANTS TO INCLUDE

1. **Offline** — action-bar status: `attention` square dot +
   `Offline · using cached profiles`. The app still works; never a modal.
2. **Connected** — `success` square dot + `Profiles up to date`.
3. **Read-only** — a support user viewing a profile: inputs on `surface-1` with
   `text-tertiary` values, Caption `Read-only · admin access required to edit`.
4. **Empty** — centred `text-secondary` `No profiles yet` with a `New profile`
   primary button beneath.

---

## EXPLICITLY DO NOT

- No rounded corners of any radius, anywhere, on anything.
- No shadows, glows, elevation blur, glassmorphism, or translucency.
- No opacity values — every colour flat and opaque.
- No gradient except the two specified (header band, progress fill).
- No custom or web fonts — system UI and system monospace only.
- No icon fonts, illustrations, 3D renders, mascots, or emoji as UI. The only
  symbols are `✓ ✗ ! ● › ① ② ③ ④`.
- No sidebars, hamburger menus, tabs, breadcrumbs, or floating action buttons.
- No light-mode variants.
- No mobile, tablet, or responsive layouts.
- No marketing copy, taglines, hero sections, or onboarding tours.
- No hue beyond purple, amber, and the semantic green/red.
- Do not invent screens, settings pages, notifications, or features beyond the
  eight described.

## DELIVERABLE

Eight screens plus the listed variants, presented as a flat board, each
1080 × 720px, dark appearance, labelled with its screen name. Flow:
Sign in → Dashboard → Generate → Review → Generating → Complete, with Profile
management and Profile editor as an admin-only branch from Dashboard.
