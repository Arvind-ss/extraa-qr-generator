# Admin guide

For the support lead. Everything in the user guide applies to you too; this
covers the parts only you can do.

## Connecting to the shared store

**Dashboard → Settings.**

| Field | What it is |
|---|---|
| Profile API address | `https://backend.extraa.in/v1/graphql` |
| Access token | the read token issued by the login service |
| Admin secret | **only** on your machine, and only to edit profiles |

**Test connection** checks both before you save. Saving writes
`~/Library/Application Support/extraa-qr/config.json` on macOS or
`%APPDATA%\extraa-qr\` on Windows, readable only by you — created with those
permissions from the start, not tightened afterwards.

Environment variables (`EXTRAA_QR_API_URL`, `EXTRAA_QR_TOKEN`,
`EXTRAA_QR_ADMIN_SECRET`) override the file and are not copied into it, so a
fleet configured centrally does not end up with stale copies on disk.

**Support machines need the address and token; they must never get the admin
secret.** It is the Hasura admin secret — full access to the entire database,
not just profiles. See `server/README.md`.

## What a profile decides

A profile is business configuration. It holds no code and cannot run anything.

| | Example | |
|---|---|---|
| Required input columns | `name, qr_code` | what the CSV must contain |
| QR content | `https://www.extraacards.com/cards/{qr_code}` | what a scan opens |
| Top text | `{name}` | printed above the code |
| Bottom text | `{qr_code}` | printed below it |
| Filename | `{qr_code}.png` | the file inside the ZIP |
| Printed text | Roboto, 48/80, 5px spacing | how it looks |

Only `{name}` and `{qr_code}` — whatever columns the profile requires — can
appear in a template. Anything else is refused when you save, with the list of
what is allowed.

## Creating and editing

**Dashboard → Profile management → New profile** or **Edit**.

Both are refused unless the admin secret is configured. The buttons grey out,
and the refusal is enforced by the store, not just hidden in the interface.

Things that will stop a save, on purpose:

* a template using a column the profile does not require
* a filename template containing `/`, `\` or `..` — that is how a ZIP escapes
  its own folder on extraction
* a text size outside 12–160px, or spacing outside −10 to 40
* a font that is not one of the bundled files

**Preview** opens the same form read-only, for checking without risk.

## Deactivating

**There is no delete, anywhere.** Deactivating hides a profile from the support
team and keeps it in the database. A batch generated last year has to stay
explicable, and the version history exists for that.

Every save increments the version and writes the previous one to
`qr_profile_versions`, with who changed it and when. The database does the
counting, so two admins saving at once cannot both write version 4.

## Changing how cards look

Size and spacing are on the upload screen and apply to **one batch**. To change
them for everyone, edit the profile.

⚠️ **Cards printed before a change will not match cards printed after it.**
Currently: Roboto at 48/80, giving a 697×697 card. Everything shipped before
2026-09-13 was Geist Mono at 36/60, giving 660×660. Both typefaces ship, so the
old look can be restored exactly — `docs/PROFILE_MAPPING.md` has the numbers.

## When something looks wrong

**Profiles are stale.** Bottom-left says how old they are; **Refresh** re-fetches.
A save invalidates it automatically.

**Someone cannot connect.** Have them open Settings → Test connection. It
distinguishes a wrong address from a rejected token.

**The app will not open**, complaining about the reference card: that
installation is damaged and is refusing to print cards that would not match the
existing ones. Reinstall. To confirm from a terminal:

```
"QR Generator.app/Contents/MacOS/QRGenerator" --verify
QRGenerator.exe --verify
```

It renders a known card and runs a real 300-row batch. Three seconds, and it
separates a broken install from a broken input file.

## Accounts

There are none in v1 — the app opens straight to the dashboard. The login
service, the role rules (`superadmin` → admin, `guest` → support, everything
else refused) and the token plumbing are all built and tested, waiting on v2.
`EXTRAA_QR_REQUIRE_LOGIN=1` turns it on. See `docs/AUTH.md`.
