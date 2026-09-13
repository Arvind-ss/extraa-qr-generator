"""End-to-end: CSV -> profile -> sample -> batch -> ZIP."""

import csv
import hashlib
import os
import zipfile

import pytest

from qrgen import engine, profiles

PROFILE = profiles.get("extraa_cards")


def make_csv(tmp_path, rows, name="in.csv"):
    path = tmp_path / name
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "qr_code"])
        writer.writerows(rows)
    return str(path)


def codes(n):
    return [(f"26-B0004-{i}", f"A{i:05d}") for i in range(1, n + 1)]


def test_sample_reports_fields(tmp_path):
    path = make_csv(tmp_path, [("26-B0008-1", "RDFXRN")])
    sample = engine.render_sample(PROFILE, engine.first_row(path))
    assert sample.fields == {
        "qr_content": "https://www.extraacards.com/cards/RDFXRN",
        "bottom_text": "RDFXRN", "top_text": "26-B0008-1",
        "filename": "RDFXRN.png"}
    assert sample.row_number == 1


def test_sample_matches_the_shipped_card(tmp_path):
    """The whole pipeline can still reproduce a card that was already printed.

    Asked for the original typeface and sizes through the same override the
    upload screen uses. The shipped cards were printed in Geist Mono at 36/60;
    the profile now prints Roboto at 48/80, and the pipeline must stay able to
    reproduce the old ones exactly.
    """
    reference = os.path.join(os.path.dirname(__file__), "golden",
                             "Brigade_RDFXRN.png")
    path = make_csv(tmp_path, [("26-B0008-1", "RDFXRN")])
    sample = engine.render_sample(PROFILE, engine.first_row(path),
                                  name_font="rob_batch.ttf",
                                  code_font="rob_batch.ttf",
                                  name_size=36, code_size=60)
    assert hashlib.sha256(sample.image).hexdigest() == \
        hashlib.sha256(open(reference, "rb").read()).hexdigest()


def test_batch_produces_a_flat_zip(tmp_path):
    path = make_csv(tmp_path, codes(5))
    out = str(tmp_path / "cards.zip")
    result = engine.generate_batch(PROFILE, path, out)

    assert result.total == 5 and result.successful == 5 and result.failed == 0
    assert not result.cancelled and result.error_report is None
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
    assert names == sorted(f"A{i:05d}.png" for i in range(1, 6))
    assert not any("/" in n for n in names)


def test_progress_is_reported_and_ends_at_the_total(tmp_path):
    path = make_csv(tmp_path, codes(60))
    seen = []
    engine.generate_batch(PROFILE, path, str(tmp_path / "c.zip"),
                          on_progress=lambda *a: seen.append(a))
    assert seen[0] == (0, 60, 0, 0)
    assert seen[-1] == (60, 60, 60, 0)
    assert len(seen) > 2, "progress should be reported during the run"


def test_one_bad_row_does_not_lose_the_others(tmp_path):
    rows = codes(4)
    # "CON" resolves to CON.png, which Windows refuses to create.
    rows.insert(2, ("26-B0004-x", "CON"))
    path = make_csv(tmp_path, rows)
    out = str(tmp_path / "cards.zip")
    result = engine.generate_batch(PROFILE, path, out)

    assert result.total == 5 and result.successful == 4 and result.failed == 1
    assert result.failures[0].row_number == 3
    assert result.failures[0].qr_code == "CON"
    assert "reserved" in result.failures[0].error
    with zipfile.ZipFile(out) as archive:
        assert len(archive.namelist()) == 4


def test_error_report_is_written_beside_the_zip(tmp_path):
    rows = codes(2)
    rows.append(("26-B0004-x", "CON"))
    path = make_csv(tmp_path, rows)
    result = engine.generate_batch(PROFILE, path, str(tmp_path / "cards.zip"))

    assert os.path.basename(result.error_report) == "generation_errors.csv"
    with open(result.error_report, encoding="utf-8", newline="") as fh:
        report = list(csv.DictReader(fh))
    assert list(report[0]) == ["row_number", "qr_code", "error"]
    assert report[0]["qr_code"] == "CON"


def test_error_report_carries_no_personal_data(tmp_path):
    """Input CSVs carry phone numbers and user names. The report must not."""
    path = tmp_path / "in.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "qr_code", "Phone"])
        writer.writerow(["26-B0004-x", "CON", "9845443540"])
    result = engine.generate_batch(PROFILE, str(path), str(tmp_path / "c.zip"))
    assert "9845443540" not in open(result.error_report, encoding="utf-8").read()


def test_error_report_neutralises_spreadsheet_formulas(tmp_path):
    failures = [engine.validate.RowError(1, "=cmd|'/c calc'!A1", "=1+1")]
    path = str(tmp_path / "errors.csv")
    engine.write_error_report(failures, path)
    text = open(path, encoding="utf-8").read()
    assert "'=cmd" in text and "'=1+1" in text


def test_cancel_stops_early_and_leaves_no_zip(tmp_path):
    path = make_csv(tmp_path, codes(200))
    out = str(tmp_path / "cards.zip")
    state = {"n": 0}

    def should_cancel():
        state["n"] += 1
        return state["n"] > 1

    result = engine.generate_batch(PROFILE, path, out, should_cancel=should_cancel)
    assert result.cancelled
    assert result.successful < 200
    assert result.zip_path is None
    assert not os.path.exists(out)


def test_temporary_files_are_always_cleaned_up(tmp_path):
    def existing_jobs():
        root = engine.TEMP_ROOT
        return set(os.listdir(root)) if os.path.isdir(root) else set()

    before = existing_jobs()
    path = make_csv(tmp_path, codes(10))
    engine.generate_batch(PROFILE, path, str(tmp_path / "c.zip"))
    assert existing_jobs() == before

    # ... including when the job is cancelled half way.
    engine.generate_batch(PROFILE, make_csv(tmp_path, codes(200), "b.csv"),
                          str(tmp_path / "d.zip"),
                          should_cancel=lambda: True)
    assert existing_jobs() == before


def test_validate_input_refuses_a_bad_file(tmp_path):
    path = make_csv(tmp_path, [("A", "TOOLONG1"), ("B", "OK1234")])
    report = engine.validate_input(PROFILE, path)
    assert not report.ok and report.errors[0].row_number == 1


def test_preview_rows_picks_first_second_and_last(tmp_path):
    """Row 1 alone hides the failures that matter -- a wrapping name, a
    truncated export."""
    path = make_csv(tmp_path, codes(40))
    assert [n for n, _ in engine.preview_rows(path)] == [1, 2, 40]

    two = make_csv(tmp_path, codes(2), "two.csv")
    assert [n for n, _ in engine.preview_rows(two)] == [1, 2]

    one = make_csv(tmp_path, codes(1), "one.csv")
    assert [n for n, _ in engine.preview_rows(one)] == [1]


def test_render_samples_returns_one_card_per_preview_row(tmp_path):
    path = make_csv(tmp_path, codes(40))
    samples = engine.render_samples(PROFILE, path)
    assert [s.row_number for s in samples] == [1, 2, 40]
    assert all(s.image[:2] == b"\xff\xd8" for s in samples)  # JPEG magic


def test_zip_has_no_compression_and_stays_readable(tmp_path):
    path = make_csv(tmp_path, codes(3))
    out = str(tmp_path / "cards.zip")
    engine.generate_batch(PROFILE, path, out)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        assert all(i.compress_type == zipfile.ZIP_STORED
                   for i in archive.infolist())


def test_blank_name_renders_a_card_with_no_name_row(tmp_path):
    """Matches the reference: `if top_text:` treats "" as absent.

    A blank name does not fail -- it produces a 600x600 card with only the code.
    CSV validation rejects blank required values before a batch ever starts, so
    this shape cannot reach generation through the normal workflow. Pinned so
    the behaviour is a decision rather than a surprise.
    """
    path = make_csv(tmp_path, [("", "ABC123")])
    sample = engine.render_sample(PROFILE, engine.first_row(path))
    assert sample.fields["top_text"] == ""
    from PIL import Image
    import io
    # 606, not 600: with no name row the card is the QR plus one text line, and
    # Roboto's line box is taller than the Geist Mono the card used to use.
    assert Image.open(io.BytesIO(sample.image)).size == (606, 606)

    assert not engine.validate_input(PROFILE, path).ok


# --- parallel execution -----------------------------------------------------
# These force workers>1 explicitly. Without that nothing exercises the pool:
# the cancel test trips its cancel before a pool is ever created, and every
# other case is under POOL_THRESHOLD.

def test_pool_output_is_identical_to_sequential(tmp_path):
    """Parallelism is an implementation detail; the bytes must not move."""
    path = make_csv(tmp_path, codes(40))
    one = str(tmp_path / "one.zip")
    many = str(tmp_path / "many.zip")

    engine.generate_batch(PROFILE, path, one, workers=1)
    result = engine.generate_batch(PROFILE, path, many, workers=2)
    assert result.workers == 2 and result.successful == 40

    with zipfile.ZipFile(one) as a, zipfile.ZipFile(many) as b:
        assert a.namelist() == b.namelist()
        for name in a.namelist():
            assert a.read(name) == b.read(name), name


def test_pool_records_failures_in_row_order(tmp_path):
    """imap_unordered completes out of order; the report must not."""
    rows = codes(40)
    for position in (5, 20, 35):
        rows[position] = ("26-B0004-x", "CON")
    path = make_csv(tmp_path, rows)
    result = engine.generate_batch(PROFILE, path, str(tmp_path / "c.zip"),
                                   workers=2)
    assert result.failed == 3
    assert [f.row_number for f in result.failures] == sorted(
        f.row_number for f in result.failures)


def test_falls_back_to_one_worker_when_main_is_not_importable(monkeypatch, tmp_path):
    """A REPL or heredoc has no importable __main__; spawn would hang there."""
    import sys
    monkeypatch.delattr(sys.modules["__main__"], "__file__", raising=False)
    assert not engine.can_spawn()
    path = make_csv(tmp_path, codes(5))
    result = engine.generate_batch(PROFILE, path, str(tmp_path / "c.zip"),
                                   workers=4)
    assert result.workers == 1 and result.successful == 5


def test_style_override_only_affects_the_render_it_is_given(tmp_path):
    """Previewing a size change must not mutate the shared profile."""
    path = make_csv(tmp_path, [("26-B0008-1", "RDFXRN")])
    row = engine.first_row(path)
    before = PROFILE.style
    small = engine.render_sample(PROFILE, row, name_size=36, code_size=60)
    after = engine.render_sample(PROFILE, row)
    assert PROFILE.style == before
    assert small.image != after.image
    from PIL import Image
    import io
    assert Image.open(io.BytesIO(small.image)).size == (666, 666)
    assert Image.open(io.BytesIO(after.image)).size == (697, 697)


def test_tracking_changes_the_card(tmp_path):
    path = make_csv(tmp_path, [("26-B0008-1", "RDFXRN")])
    row = engine.first_row(path)
    tight = engine.render_sample(PROFILE, row, name_tracking=0)
    loose = engine.render_sample(PROFILE, row, name_tracking=14)
    assert tight.image != loose.image


def test_profile_rejects_an_absurd_text_size():
    from qrgen.profiles import Profile, ProfileError
    base = PROFILE.to_dict()
    for field, value in (("name_size", 400), ("code_size", 0),
                         ("name_tracking", 999), ("name_size", "big")):
        with pytest.raises(ProfileError):
            Profile.from_dict({**base, field: value})
