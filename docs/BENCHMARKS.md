# Large-batch measurements

Machine: Apple Silicon, 10 cores, macOS 25.5. Python 3.9.6, Pillow 11.3.0,
qrcode 8.2. Profile: Extraa Cards. 9 worker processes (cores - 1).

Reproduce with `python cli.py generate -p extraa_cards -i <csv> -o <zip> -y`.

| Rows | Wall time | Per card | Parent RSS | Worker RSS | Temp disk | ZIP | Failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 3.2 s | 3.21 ms | 21 MB | 38 MB | 0.05 GB | 0.05 GB | 0 |
| 2,000 | 5.9 s | 2.93 ms | 22 MB | 39 MB | 0.09 GB | 0.09 GB | 0 |
| 10,000 | 32.0 s | 3.20 ms | 28 MB | 39 MB | 0.45 GB | 0.45 GB | 0 |
| 50,000 | **165.5 s** | 3.31 ms | 59 MB | 39 MB | 2.24 GB | **2.24 GB** | 0 |

Sequential baseline for comparison: 14.4 ms/card, so 50,000 rows took ~12
minutes before the pool and takes **2 min 45 s** after. Speedup is ~4.3x on 9
workers -- short of linear because the parent process does all the ZIP writing,
which is single-threaded I/O at the end of the run.

## Reading the memory numbers

Peak resident memory is flat in the batch size, which is the whole point of the
disk-backed design: a card is rendered, written, and released. Total footprint
at 50,000 rows is roughly `59 + 9 x 39 = ~410 MB` across all processes.

The parent's growth from 21 MB to 59 MB is not card data -- it is
`imap_unordered` buffering pending tasks. Each task is the row projected down to
just the profile's columns, so 50,000 of them cost tens of megabytes. If that
ever matters, feed the pool in slices rather than one generator.

## Things to plan around

* **The 50,000-row ZIP is 2.24 GB.** Nothing compresses it further -- the
  payload is already-encoded JPEG, which is why the archive is ZIP_STORED.
  Moving that file is the slowest part of the whole workflow, and it is
  somebody's network, not our code.
* **Peak disk during a 50,000-row job is ~4.5 GB**: the temporary PNGs and the
  ZIP being built from them coexist until the job finishes. The temp directory
  is removed immediately afterwards.
* **The app does no QR verification.** It renders samples for rows 1, 2 and the
  last one, and support staff check them. Nothing decodes a QR anywhere in the
  codebase, which is why OpenCV and numpy are not dependencies -- they were
  157 MB of the 172 MB the app used to carry.
