# User guide

For the support team. You need the application and a CSV file. Nothing else is
installed and nothing is set up.

## Before you start

Your CSV needs two columns, named exactly:

```csv
name,qr_code
26-B0008-1,RDFXRN
26-B0008-2,F7HWVG
```

`qr_code` must be **six letters or digits**. Extra columns are ignored, so an
export straight from the dashboard is fine — it will have `Phone`, `Batch` and
others, and none of them are read or sent anywhere.

## 1. Open the app, press Get started

There is no login. The app opens on a welcome screen with one button.

## 2. Choose a profile and a file

**Profile** decides what goes into the QR code and what the file is called. For
cards that is *Extraa Cards*: the QR holds `extraacards.com/cards/<code>`, the
name prints above the code, and the file is named after the code.

Drop your CSV onto the dashed box, or click **or choose a file**.

The file is checked as soon as you pick it. Two outcomes:

```
✓ 500 rows, no errors
✗ 3 of 500 rows have errors
```

If there are errors, a table lists them with the row number:

| Row | QR code | Error |
|---|---|---|
| 12 | ABC12 | qr_code must be exactly 6 characters, got 5 |
| 89 | XY-Z45 | qr_code must be alphanumeric; found '-' |
| 204 | RDFXRN | duplicate qr_code 'RDFXRN', already used by row 17 |

**Fix the spreadsheet and choose the file again.** Nothing generates until the
file is clean — that is deliberate. A duplicate code means two rows would write
the same file and one would quietly vanish from the ZIP.

`Copy all` puts every error on the clipboard to paste into a message.

## 3. Printed text (optional)

Under the profile there is a row:

```
Size  − 48/80 +     Spacing  − 5 px +     Reset
```

**Size** is how large the printed name and code are; **Spacing** is the gap
between the letters of the name. Changing them affects **this batch only** —
the shared profile is untouched, and the line beneath turns amber to say so.
`Reset` puts them back.

Leave them alone unless somebody has asked for a change.

## 4. Check the sample

Press **Generate sample**. You get real cards for the **first row, the second
row, and the last row** — click `Row 1` / `Row 2` / `Row 50,000` to switch.

Three rows rather than one because the problem is usually not in the first
record: a long store name wraps and makes a taller card, and a truncated export
shows up at the end.

Check the card against the details on the left — name, code, the address the QR
points to, the filename. **Scan it with your phone.** The preview is large
enough, and `Open full size` opens the real file if you want to be sure.

The app does not check the QR for you. That is the point of this screen.

Then:

* **Back** — return to the previous screen, change the size, come back. Your
  file and its check are kept; nothing is re-uploaded.
* **Regenerate** — render the samples again.
* **Approve & generate** — commit. You are asked where to save the ZIP.

## 5. Wait

```
Generating QR codes
██████████████░░░░░░  34,820 / 50,000        70%

SUCCESSFUL   34,815        REMAINING    ~1m 10s
FAILED            5        THROUGHPUT   210 / sec
```

50,000 cards take **under three minutes**. The window stays usable throughout.

**Cancel** stops it and removes the half-finished files. Nothing part-done is
left behind and no ZIP is written.

## 6. Collect the ZIP

```
Total         50,000
Successful    49,972
Failed            28
Time          2m 45s
Output        extraa_cards_2026-09-13.zip     2.24 GB
```

**Open ZIP** shows it in Finder or Explorer. Inside are the PNG files, no
folders, named after each code.

### When some rows fail

The other rows still generate and are still in the ZIP. A **`generation_errors.csv`**
appears beside it listing the row number, the code, and what went wrong — so
those rows can be fixed and run again on their own. It contains no names and no
phone numbers.

### A note on large files

A 50,000-card ZIP is about **2.2 GB** and will not compress further. Allow time
to copy or upload it, and make sure the drive has room: during generation the
app needs roughly double that temporarily.

## Things worth knowing

**The status at the bottom left** says where the profiles came from:

| | |
|---|---|
| ● Profiles up to date | fetched just now |
| ● Offline · using profiles saved 2h ago | working from a saved copy |
| ● Offline · using the profiles built into this app | no connection, ever |

Generating works in all three. **Refresh** re-fetches. If a profile was changed
today and the status says "2h ago", press it.

**Nothing leaves your computer.** Cards are generated locally and the ZIP is
written to the folder you chose. The only thing sent over the network is the
request for the profile list.

**If the app refuses to open** with a message about the reference card, the
installation is damaged — it is deliberately refusing to print cards that would
not match the ones already out there. Ask IT to reinstall it.
