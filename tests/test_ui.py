"""Smoke tests that build every screen for real.

These create an actual Tk window (withdrawn, never shown) and walk the whole
flow. They catch what unit tests cannot: a screen that raises while building,
a style name that was never registered, a widget packed into the wrong parent.

Skipped automatically where there is no display.
"""

import csv
import os
import time
import tkinter as tk

import pytest

from qrgen import auth

# Do NOT probe for a display by creating a throwaway Tk() root: creating a
# second root after destroying the first segfaults Tk on macOS. The fixture
# below builds exactly one root and skips the module if that fails.

ADMIN = auth.User("admin@example.com", "Support Lead", auth.ADMIN)
SUPPORT = auth.User("support@example.com", "Support User", auth.SUPPORT)


@pytest.fixture(scope="module", autouse=True)
def isolated_config(tmp_path_factory):
    """Keep these tests off the real profile cache.

    Without this the suite reads whatever the developer's own machine last
    fetched -- which is how a stray record from a manual experiment ended up
    driving an assertion.
    """
    from qrgen import config

    directory = str(tmp_path_factory.mktemp("config"))
    original = config.config_dir
    config.config_dir = lambda: directory
    for variable in config.ENV.values():
        os.environ.pop(variable, None)
    yield
    config.config_dir = original


@pytest.fixture(scope="module")
def _root():
    """One Tk root for the whole module.

    Creating and destroying several Tk() roots in one process segfaults on
    macOS, so the window is built once, withdrawn, and reused. Each test gets
    it back at the login screen.
    """
    from ui.app import App
    try:
        application = App()
    except tk.TclError as exc:      # no display (headless CI)
        pytest.skip(f"no display available: {exc}", allow_module_level=True)
    application.withdraw()          # built and measurable, never shown
    yield application
    application.destroy()


@pytest.fixture
def app(_root):
    _root.sign_out()                # back to the entry screen, session cleared
    _root.update_idletasks()
    return _root


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "cards.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "qr_code"])
        for index in range(1, 6):
            writer.writerow([f"26-B0004-{index}", f"A{index:05d}"])
    return str(path)


def descendants(widget):
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(descendants(child))
    return found


def texts(widget):
    out = []
    for child in descendants(widget):
        try:
            value = child.cget("text")
        except Exception:
            continue
        if value:
            out.append(str(value))
    return out


# --- shell ------------------------------------------------------------------

def test_starts_on_the_welcome_screen(app):
    """v1 has no accounts: one button, no passwords."""
    from ui.screens.auth import WelcomeScreen
    assert isinstance(app._screen, WelcomeScreen)
    assert app.user is None


def test_welcome_chrome_is_hidden(app):
    assert not app.action_bar.winfo_ismapped()


def test_get_started_reaches_the_dashboard(app):
    from ui.screens.home import DashboardScreen
    app._screen.start()
    app.update_idletasks()
    assert isinstance(app._screen, DashboardScreen)
    assert app.user is not None and app.user.is_admin


def test_no_identity_strip_without_a_login(app):
    """Nobody is signed in, so there is nobody to show and nowhere to sign out."""
    app._screen.start()
    app.update_idletasks()
    assert texts(app.identity) == []


def test_the_brand_name_is_not_in_the_interface(app):
    """v1 ships unbranded."""
    app._screen.start()
    app.update_idletasks()
    shown = " ".join(texts(app)) + " " + app.title()
    assert "Extraa" not in shown, shown[:200]


def test_the_login_screen_is_still_there_for_v2(app):
    """Kept, not deleted: the providers and role machinery stay exercised."""
    from ui.screens.auth import LoginScreen

    app.show(LoginScreen)
    app.update_idletasks()
    screen = app._screen
    screen.email.set("admin@example.com")
    screen.password.set("wrong")
    screen.submit()
    app.update_idletasks()
    assert app.user is None
    assert any("Incorrect email or password" in text for text in texts(screen))

    screen.password.set("extraa-admin")
    screen.submit()
    app.update_idletasks()
    assert app.user.is_admin


def test_the_entry_screen_follows_the_switch(monkeypatch):
    from ui import app as app_module
    from ui.screens import auth as auth_screens

    monkeypatch.setattr(auth_screens, "REQUIRE_LOGIN", False)
    assert app_module.App._entry_screen() is auth_screens.WelcomeScreen
    monkeypatch.setattr(auth_screens, "REQUIRE_LOGIN", True)
    assert app_module.App._entry_screen() is auth_screens.LoginScreen


# --- roles ------------------------------------------------------------------

def test_support_dashboard_marks_profile_management_unavailable(app):
    app.sign_in(SUPPORT)
    app.update_idletasks()
    assert any("Admin access required" in text for text in texts(app._screen))


def test_admin_dashboard_offers_profile_management(app):
    app.sign_in(ADMIN)
    app.update_idletasks()
    assert any("Create and edit generation profiles" in text
               for text in texts(app._screen))


def test_support_sees_the_editor_read_only(app):
    from ui.screens.profiles import ProfileEditorScreen
    app.sign_in(SUPPORT)
    profile = app.store.get("extraa_cards")
    app.show(ProfileEditorScreen, profile=profile)
    app.update_idletasks()
    assert app._screen.readonly
    assert any("Read-only" in text for text in texts(app._screen))


def test_editor_is_writable_for_admin(app):
    from ui.screens.profiles import ProfileEditorScreen
    app.sign_in(ADMIN)
    app.show(ProfileEditorScreen, profile=app.store.get("extraa_cards"))
    app.update_idletasks()
    assert not app._screen.readonly
    assert app._screen.fields["qr_content"].get().endswith("{qr_code}")


def test_profile_list_has_no_delete_control(app):
    """Profiles are deactivated, never removed."""
    from ui.screens.profiles import ProfileListScreen
    app.sign_in(ADMIN)
    app.show(ProfileListScreen)
    app.update_idletasks()
    labels = texts(app) + [text for text, *_ in
                           [(a[0],) for a in app._screen.actions()]]
    assert not any("delete" in text.lower() for text in labels)


# --- wizard -----------------------------------------------------------------

def _wait(app, predicate, seconds=10):
    """Pump the event loop until `predicate` holds.

    Real time has to pass: run_async re-polls on a 60ms timer, so spinning on
    update() alone never lets the timer fire.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_generate_screen_shows_the_profile_summary(app):
    from ui.screens.generate import GenerateScreen
    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.update_idletasks()
    joined = " ".join(texts(app._screen))
    assert "https://www.extraacards.com/cards/{qr_code}" in joined
    assert "{qr_code}.png" in joined


def test_primary_action_is_disabled_until_a_file_validates(app):
    from ui.screens.generate import GenerateScreen
    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.update_idletasks()
    primary = [a for a in app._screen.actions() if a[1] == "primary"][0]
    assert primary[0] == "Generate sample" and primary[3] is False


def test_valid_file_enables_the_primary_action(app, csv_path):
    from ui.screens.generate import GenerateScreen
    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.job.input_path = csv_path
    app._screen.show_file(csv_path)
    app._screen.validate()
    assert _wait(app, lambda: app.job.report is not None)
    app.update_idletasks()
    assert app.job.report.ok
    primary = [a for a in app._screen.actions() if a[1] == "primary"][0]
    assert primary[3] is True
    assert any("5 rows, no errors" in text for text in texts(app._screen))


def test_invalid_file_blocks_the_primary_action(app, tmp_path):
    from ui.screens.generate import GenerateScreen
    path = tmp_path / "bad.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "qr_code"])
        writer.writerow(["Store", "TOOLONG1"])
    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.job.input_path = str(path)
    app._screen.show_file(str(path))
    app._screen.validate()
    assert _wait(app, lambda: app.job.report is not None)
    app.update_idletasks()
    primary = [a for a in app._screen.actions() if a[1] == "primary"][0]
    assert primary[3] is False
    # Errors render in a Treeview, whose cells are not label text.
    table = app._screen.error_table
    rows = [table.tree.item(i, "values") for i in table.tree.get_children()]
    assert rows and "exactly 6 characters" in rows[0][2]
    assert rows[0][0] == "1"


def test_review_screen_renders_the_card_and_the_gate(app, csv_path):
    from qrgen import engine
    from ui.screens.generate import ReviewScreen
    app.sign_in(ADMIN)
    app.job.profile = app.store.get("extraa_cards")
    app.job.input_path = csv_path
    app.job.samples = engine.render_samples(app.job.profile, csv_path)
    app.show(ReviewScreen)
    app.update_idletasks()

    joined = " ".join(texts(app._screen))
    assert "A00001" in joined
    assert "https://www.extraacards.com/cards/A00001" in joined
    assert app._screen._photos[-1].width() > 100, "preview image did not render"

    labels = [a[0] for a in app._screen.actions()]
    assert labels == ["Back", "Regenerate", "Approve & generate"]


def test_approve_button_never_starts_focused(app, csv_path):
    """The commit point must not be reachable by a stray Return key."""
    from qrgen import engine
    from ui.screens.generate import ReviewScreen
    app.sign_in(ADMIN)
    app.job.profile = app.store.get("extraa_cards")
    app.job.input_path = csv_path
    app.job.samples = engine.render_samples(app.job.profile, csv_path)
    app.show(ReviewScreen)
    app.update_idletasks()
    primary = [b for b in app.buttons.winfo_children()
               if str(b.cget("style")) == "Primary.TButton"][0]
    assert primary.cget("takefocus") in (0, "0", False)


def test_step_rail_marks_review_as_its_own_step(app):
    from ui.screens.generate import GenerateScreen
    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.update_idletasks()
    assert app._screen.step == 1
    from ui.screens.generate import ReviewScreen
    assert ReviewScreen.step == 3


# --- theme ------------------------------------------------------------------
# No display needed and no module reloading: palette() is a pure function, so
# every mode can be checked in one process without disturbing the live window.

MODES = ("light", "dark", "mono", "monoDark")


@pytest.mark.parametrize("mode", MODES)
def test_every_status_colour_is_legible(mode):
    """The line that says whether a batch is safe to run has to be readable.

    Mint green on a near-white background sits at 1.77:1 -- present, and
    invisible. Every palette in theme.json is checked.
    """
    from ui import theme

    p = theme.palette(mode)
    checks = {
        "body text": (p["TEXT"], p["BG"], 4.5),
        "body text on a panel": (p["TEXT"], p["SURFACE_1"], 4.5),
        "labels": (p["TEXT_2"], p["SURFACE_1"], 4.5),
        "error": (p["ERROR"], p["BG"], 4.5),
        "success": (p["SUCCESS"], p["BG"], 4.5),
        "attention on its strip": (p["ATTENTION"], p["TINT_ATTENTION"], 3.0),
        "text on the accent button": (p["ON_ACCENT"], p["ACCENT"], 4.5),
        "hint text": (p["TEXT_3"], p["BG"], 2.5),
    }
    for what, (fg, bg, minimum) in checks.items():
        ratio = theme.contrast(fg, bg)
        assert ratio >= minimum, (
            f"{mode}: {what} is {ratio:.2f}:1, needs {minimum}:1 "
            f"({fg} on {bg})")


@pytest.mark.parametrize("mode", MODES)
def test_preview_well_is_neutral_and_shows_a_white_card(mode):
    """Tinted or near-white, and nobody can see where the card ends."""
    from ui import theme

    well = theme.palette(mode)["PREVIEW_WELL"]
    red, green, blue = theme._channels(well)
    assert max(red, green, blue) - min(red, green, blue) <= 8, \
        f"{mode}: preview well {well} is tinted"
    assert theme.contrast("#ffffff", well) >= 3.0, \
        f"{mode}: a white card would not be visible against the well"


@pytest.mark.parametrize("mode", ("mono", "monoDark"))
def test_monochrome_palettes_have_no_hue_at_all(mode):
    """"Two colours" means one hue and a lightness ramp: verify zero chroma."""
    from ui import theme

    for name, value in theme.palette(mode).items():
        red, green, blue = theme._channels(value)
        assert red == green == blue, \
            f"{mode}: {name} is {value}, not a pure grey"


@pytest.mark.parametrize("mode", MODES)
def test_progress_bar_and_hover_stay_visible(mode):
    """In monochrome the accent IS the text, so anything derived by blending
    the two together collapses to a flat bar and an invisible hover."""
    from ui import theme

    p = theme.palette(mode)
    assert p["ACCENT_DEEP"] != p["ACCENT"], f"{mode}: flat progress bar"
    assert p["ACCENT_HOVER"] != p["ACCENT"], f"{mode}: invisible hover"
    assert theme.contrast(p["ACCENT_DEEP"], p["ACCENT"]) > 1.4, \
        f"{mode}: progress gradient barely moves"


def test_gradient_blend_endpoints():
    from ui.theme import blend
    assert blend("#000000", "#FFFFFF", 0) == "#000000"
    assert blend("#000000", "#FFFFFF", 1) == "#ffffff"
    assert blend("#000000", "#FFFFFF", 0.5) == "#808080"


def test_printed_text_controls_live_on_the_upload_step(app, csv_path):
    """Set the size before rendering, then check it on Review."""
    import io

    from PIL import Image
    from qrgen import engine
    from ui.screens.generate import GenerateScreen, ReviewScreen

    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.job.input_path = csv_path
    app._screen.show_file(csv_path)
    app._screen.validate()
    assert _wait(app, lambda: app.job.report is not None)

    screen = app._screen
    assert screen.size_step.value == 48
    assert screen.track_step.value == 5

    screen.size_step.bump(-2)                      # 48 -> 46
    screen.track_step.bump(3)                      # 5 -> 8
    app.update_idletasks()
    assert app.job.style["name_size"] == 46
    assert app.job.style["code_size"] == engine.code_size_for(46)
    assert app.job.style["name_tracking"] == 8

    # The shared profile is untouched: this applies to one batch.
    assert app.job.profile.style == {
        "name_font": "rob.ttf", "code_font": "rob.ttf",
        "name_size": 48, "code_size": 80,
        "name_tracking": 5, "code_tracking": 0}

    screen.make_sample()
    assert _wait(app, lambda: app.job.samples)
    app.update_idletasks()
    assert isinstance(app._screen, ReviewScreen)

    default = engine.render_sample(app.job.profile, engine.first_row(csv_path))
    tuned = app.job.samples[0]
    assert tuned.image != default.image, "the setting did not reach the render"
    assert Image.open(io.BytesIO(tuned.image)).size != \
        Image.open(io.BytesIO(default.image)).size


def test_back_from_review_keeps_the_file_and_the_settings(app, csv_path):
    """The whole point of the controls: look, go back, change, look again."""
    from qrgen import engine
    from ui.screens.generate import GenerateScreen, ReviewScreen

    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    app.job.input_path = csv_path
    app._screen.show_file(csv_path)
    app._screen.validate()
    assert _wait(app, lambda: app.job.report is not None)
    app._screen.size_step.bump(4)                  # 48 -> 52
    app._screen.make_sample()
    assert _wait(app, lambda: app.job.samples)
    app.update_idletasks()

    app._screen.back()
    app.update_idletasks()
    assert isinstance(app._screen, GenerateScreen)

    # File still chosen, still validated, setting still 52 -- nothing re-done.
    assert app.job.input_path == csv_path
    assert app.job.report.ok
    assert app._screen.size_step.value == 52
    assert any("5 rows, no errors" in text for text in texts(app._screen))

    app._screen.size_step.bump(-8)                 # 52 -> 44
    app._screen.make_sample()
    # Wait for the screen, not for samples: the previous ones are still there,
    # so any predicate about them is already true.
    assert _wait(app, lambda: isinstance(app._screen, ReviewScreen))
    app.update_idletasks()
    assert app.job.style["name_size"] == 44
    assert app._screen.samples[0].image is not None


def test_reset_restores_the_profile_settings(app, csv_path):
    from ui.screens.generate import GenerateScreen

    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    screen = app._screen
    screen.size_step.bump(6)
    screen.track_step.bump(-4)
    app.update_idletasks()
    assert app.job.style != app.job.profile.style

    screen._reset_style()
    app.update_idletasks()
    assert app.job.style == app.job.profile.style
    assert screen.size_step.value == 48 and screen.track_step.value == 5


def test_steppers_stop_at_their_limits(app):
    from ui.screens.generate import GenerateScreen

    app.sign_in(ADMIN)
    app.show(GenerateScreen)
    step = app._screen.size_step
    for _ in range(200):
        step.bump(-2)
    assert step.value >= 12, "size went below the renderer's floor"
    for _ in range(200):
        step.bump(2)
    assert step.value <= 160


def test_refresh_button_appears_only_where_a_screen_can_redraw(app):
    """Offering Refresh mid-generation would be a button that does nothing."""
    from ui.screens.generate import GenerateScreen
    from ui.screens.home import DashboardScreen
    from ui.screens.profiles import ProfileListScreen

    app._screen.start()
    app.update_idletasks()
    assert isinstance(app._screen, DashboardScreen)
    assert not app.refresh_button.winfo_manager(), "dashboard has no list to redraw"

    for screen in (GenerateScreen, ProfileListScreen):
        app.show(screen)
        app.update_idletasks()
        assert hasattr(app._screen, "reload")
        assert app.refresh_button.winfo_manager(), screen.__name__


def test_refresh_re_reads_the_store_and_redraws(app, csv_path):
    from ui.screens.generate import GenerateScreen

    app._screen.start()
    app.show(GenerateScreen)
    app.job.input_path = csv_path
    app._screen.show_file(csv_path)
    app._screen.validate()
    assert _wait(app, lambda: app.job.report is not None)

    fetches = []
    original = app.store._load
    app.store._load = lambda: (fetches.append(1), original())[1]

    app.refresh_profiles()
    assert _wait(app, lambda: fetches and str(app.refresh_button["text"]) == "Refresh")
    app.update_idletasks()
    assert len(fetches) == 1, "refresh must ask the store exactly once"
    assert isinstance(app._screen, GenerateScreen)
    # The file survives a refresh: only the profiles are re-read.
    assert app.job.input_path == csv_path


def test_the_status_line_says_how_old_offline_profiles_are(app):
    """Someone generating from cached profiles should know how stale they are."""
    import time

    from qrgen.store import CACHED, ProfileStore, _ago

    assert _ago(0) == "just now"
    assert _ago(90) == "1 min ago"
    assert _ago(3 * 3600) == "3h ago"
    assert _ago(50 * 3600) == "2d ago"

    # `app` has not signed in yet, so build one directly.
    store = ProfileStore(settings={})
    store.source = CACHED
    store.fetched_at = time.time() - 7200
    assert store.status == "Offline · using profiles saved 2h ago"

    store.fetched_at = None
    assert "Offline" in store.status


# --- settings ---------------------------------------------------------------

def test_settings_are_reachable_without_environment_variables(app, tmp_path):
    """The deployment gap this screen closes: a support user double-clicks an
    application, they do not export shell variables first."""
    from qrgen import config
    from ui.screens.settings import SettingsScreen

    app._screen.start()
    app.update_idletasks()
    assert any("Settings" in text for text in texts(app._screen))

    app.show(SettingsScreen)
    app.update_idletasks()
    screen = app._screen
    screen.fields["api_url"].set("https://hasura.test/v1/graphql")
    screen.fields["token"].set("a-token")

    path = str(tmp_path / "config.json")
    config.save(screen._current(), path)
    written = config.load(path)
    assert written["api_url"] == "https://hasura.test/v1/graphql"
    assert written["token"] == "a-token"


def test_the_saved_file_is_not_readable_by_anyone_else(tmp_path):
    import stat

    from qrgen import config

    path = str(tmp_path / "config.json")
    config.save({"api_url": "https://x.test", "token": "secret"}, path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"config saved as {mode:o}"
    # And the loader agrees it is safe to read.
    assert config.load(path)["token"] == "secret"


def test_environment_values_are_not_duplicated_into_the_file(tmp_path, monkeypatch):
    """A machine configured by IT through env vars should not end up with a
    second, stale copy of the same credential on disk."""
    from qrgen import config

    monkeypatch.setenv("EXTRAA_QR_TOKEN", "from-the-environment")
    path = str(tmp_path / "config.json")
    config.save({"api_url": "https://x.test", "token": "from-the-environment"},
                path)
    monkeypatch.delenv("EXTRAA_QR_TOKEN")
    assert "token" not in config.load(path)


def test_empty_settings_are_not_written(tmp_path):
    from qrgen import config

    path = str(tmp_path / "config.json")
    config.save({"api_url": "https://x.test", "token": "", "admin_secret": ""},
                path)
    assert set(config.load(path)) == {"api_url"}


def test_test_connection_reports_a_failure_without_saving(app):
    from ui.screens.settings import SettingsScreen

    app._screen.start()
    app.show(SettingsScreen)
    app.update_idletasks()
    screen = app._screen
    screen.fields["api_url"].set("https://nowhere.invalid/v1/graphql")
    screen.test()
    assert _wait(app, lambda: "✗" in screen.result.cget("text")
                 or "Connected" in screen.result.cget("text"), seconds=30)
    assert "✗" in screen.result.cget("text")
