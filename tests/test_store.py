"""Profile store: transport, fallback chain, and credential handling.

No network. A fake transport stands in for Hasura.
"""

import json
import os
import stat

import pytest

from qrgen import auth, config, profiles
from qrgen.profiles import ProfileError
from qrgen.store import BUILTIN, CACHED, LIVE, ProfileStore, cache, to_profile
from qrgen.store.hasura import TABLE, StoreError as _StoreError  # noqa: F401
from qrgen.store.hasura import HasuraStore, StoreError

RECORD = {
    "id": "extraa_cards", "name": "Extraa Cards", "renderer": "standard",
    "required_columns": ["name", "qr_code"],
    "qr_content": "https://www.extraacards.com/cards/{qr_code}",
    "top_text": "{name}", "bottom_text": "{qr_code}", "filename": "{qr_code}.png",
    "output_format": "jpeg", "unique_columns": ["qr_code"],
    "validation": {"qr_code": {"length": 6, "charset": "alnum"}},
    "active": True, "version": 3,
    # Columns the API returns that the model does not carry.
    "created_by": "admin@example.com", "updated_by": "admin@example.com",
    "__typename": TABLE,
}


class Fake:
    """Stands in for urllib. Records what it was asked to send."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


ADMIN = auth.User("admin@example.com", "Support Lead", auth.ADMIN)
SUPPORT = auth.User("support@example.com", "Support User", auth.SUPPORT)


def store_with(*responses, secret=None, settings=None, user=ADMIN):
    fake = Fake(*responses)
    remote = HasuraStore("https://hasura.test/v1/graphql", admin_secret=secret,
                         transport=fake)
    return ProfileStore(remote=remote, settings=settings or {}, user=user), fake


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", lambda: str(tmp_path))
    for variable in config.ENV.values():
        monkeypatch.delenv(variable, raising=False)


# --- record conversion ------------------------------------------------------

def test_api_row_becomes_a_validated_profile():
    profile = to_profile(RECORD)
    assert profile.id == "extraa_cards" and profile.version == 3
    assert profile.required_columns == ("name", "qr_code")
    assert profile.build({"name": "A", "qr_code": "RDFXRN"})["filename"] == \
        "RDFXRN.png"


def test_api_row_with_a_bad_renderer_is_refused():
    with pytest.raises(ProfileError, match="unknown renderer"):
        to_profile({**RECORD, "renderer": "os.system"})


def test_one_bad_row_does_not_hide_the_others():
    store, _ = store_with({"data": {TABLE: [
        {**RECORD, "id": "broken", "name": "Broken", "renderer": "nope"},
        RECORD]}})
    found = store.list()
    assert [p.id for p in found] == ["extraa_cards"]
    assert "ignored profile 'broken'" in store.error


# --- transport --------------------------------------------------------------

def test_graphql_errors_are_raised_not_returned():
    remote = HasuraStore("https://hasura.test/v1/graphql",
                         transport=Fake({"errors": [{"message": "permission denied"}]}))
    with pytest.raises(StoreError, match="permission denied"):
        remote.list()


def test_unreachable_api_is_a_store_error():
    remote = HasuraStore("https://hasura.test/v1/graphql",
                         transport=Fake(OSError("connection refused")))
    with pytest.raises(StoreError, match="could not reach"):
        remote.list()


def test_reads_send_no_credential():
    """Support users must not carry a secret; the unauthorized role covers reads."""
    remote = HasuraStore("https://hasura.test/v1/graphql",
                         transport=(fake := Fake({"data": {TABLE: []}})))
    remote.list()
    assert fake.calls[0]["headers"] == {}
    assert not remote.writable


def test_writes_require_and_send_the_admin_secret():
    remote = HasuraStore("https://hasura.test/v1/graphql", admin_secret="s3cret",
                         transport=(fake := Fake(
                             {"data": {f"insert_{TABLE}_one": RECORD}})))
    assert remote.writable
    remote.save({k: v for k, v in RECORD.items() if k != "__typename"},
                "admin@example.com")
    assert fake.calls[0]["headers"]["x-hasura-admin-secret"] == "s3cret"


def test_saving_without_credentials_is_refused_before_any_request():
    fake = Fake()
    remote = HasuraStore("https://hasura.test/v1/graphql", transport=fake)
    with pytest.raises(StoreError, match="needs admin credentials"):
        remote.save(RECORD, "someone@example.com")
    assert fake.calls == [], "must not even attempt the request"


def test_secret_never_appears_in_repr():
    remote = HasuraStore("https://hasura.test/v1/graphql", admin_secret="s3cret")
    assert "s3cret" not in repr(remote)


def test_version_is_left_to_the_database():
    """Two admins saving the same profile must not both write version 4."""
    remote = HasuraStore("https://hasura.test/v1/graphql", admin_secret="s",
                         transport=(fake := Fake(
                             {"data": {f"insert_{TABLE}_one": RECORD}})))
    remote.save({k: v for k, v in RECORD.items() if k != "__typename"}, "admin")
    assert "version" not in fake.calls[0]["payload"]["variables"]["object"]


def test_missing_url_is_a_clear_error():
    with pytest.raises(StoreError, match="EXTRAA_QR_API_URL"):
        HasuraStore(None)


# --- fallback chain ---------------------------------------------------------

def test_live_store_populates_the_cache():
    store, _ = store_with({"data": {TABLE: [RECORD]}})
    assert [p.id for p in store.list()] == ["extraa_cards"]
    assert store.source == LIVE
    records, _ = cache.read()
    assert records[0]["id"] == "extraa_cards"


def test_falls_back_to_cache_when_the_api_is_down():
    cache.write([RECORD])
    store, _ = store_with(OSError("network is unreachable"))
    assert [p.id for p in store.list()] == ["extraa_cards"]
    assert store.source == CACHED
    assert "Offline" in store.status and "saved" in store.status


def test_falls_back_to_builtin_when_there_is_no_cache():
    store, _ = store_with(OSError("network is unreachable"))
    assert [p.id for p in store.list()] == ["extraa_cards"]
    assert store.source == BUILTIN
    assert "built into this app" in store.status


def test_corrupt_cache_is_ignored_rather_than_fatal():
    with open(cache.cache_path(), "w", encoding="utf-8") as fh:
        fh.write("{ truncated")
    store, _ = store_with(OSError("down"))
    assert store.list() and store.source == BUILTIN


def test_inactive_profiles_are_hidden_unless_asked_for():
    store, _ = store_with(
        {"data": {TABLE: [{**RECORD, "active": False}]}},
        {"data": {TABLE: [{**RECORD, "active": False}]}})
    assert store.list() == []
    assert [p.id for p in store.list(include_inactive=True)] == ["extraa_cards"]


def test_writes_do_not_fall_back_to_the_cache():
    """A queued write would silently overwrite another admin's change."""
    cache.write([RECORD])
    store, _ = store_with(OSError("down"), secret="s")
    with pytest.raises(StoreError):
        store.save(profiles.get("extraa_cards"), ADMIN)


def test_save_validates_before_sending():
    store, fake = store_with(secret="s")
    with pytest.raises(ProfileError, match="unknown renderer"):
        store.save({**{k: v for k, v in RECORD.items() if k != "__typename"},
                    "renderer": "evil"}, ADMIN)
    assert fake.calls == []


def test_deactivate_sends_active_false():
    store, fake = store_with(
        {"data": {f"update_{TABLE}_by_pk": {**RECORD, "active": False}}},
        secret="s")
    assert store.deactivate("extraa_cards", ADMIN).active is False
    assert fake.calls[0]["payload"]["variables"] == {
        "id": "extraa_cards", "active": False, "actor": "admin@example.com"}


# --- configuration ----------------------------------------------------------

def test_environment_overrides_the_config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"api_url": "https://from-file.test"}))
    os.chmod(path, 0o600)
    monkeypatch.setenv("EXTRAA_QR_API_URL", "https://from-env.test")
    assert config.load(str(path))["api_url"] == "https://from-env.test"


def test_world_readable_config_is_refused(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"admin_secret": "s3cret"}))
    os.chmod(path, 0o644)
    with pytest.raises(config.ConfigError, match="readable by other users"):
        config.load(str(path))


def test_missing_config_file_is_fine(tmp_path):
    assert config.load(str(tmp_path / "nope.json")) == {}


def test_redacted_hides_the_secret():
    out = config.redacted({"api_url": "https://x.test", "admin_secret": "s3cret"})
    assert out == {"api_url": "https://x.test", "admin_secret": "<set>"}


def test_config_file_permissions_are_not_checked_on_windows(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"api_url": "https://x.test"}))
    os.chmod(path, 0o644)
    monkeypatch.setattr(os, "name", "nt")
    assert config.load(str(path))["api_url"] == "https://x.test"


def test_cache_write_is_atomic(tmp_path):
    """A truncated cache after a crash would break every later launch."""
    cache.write([RECORD])
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []
    assert stat.S_ISREG(os.stat(cache.cache_path()).st_mode)


# --- role enforcement -------------------------------------------------------

def test_support_user_cannot_save_a_profile():
    store, fake = store_with(secret="s", user=SUPPORT)
    with pytest.raises(auth.PermissionDenied, match="cannot profile.edit"):
        store.save(profiles.get("extraa_cards"), SUPPORT)
    assert fake.calls == [], "must not reach the network"


def test_support_user_cannot_deactivate_a_profile():
    store, fake = store_with(secret="s", user=SUPPORT)
    with pytest.raises(auth.PermissionDenied):
        store.deactivate("extraa_cards", SUPPORT)
    assert fake.calls == []


def test_support_user_never_carries_the_admin_secret():
    """Authority comes from the role, not from what is in the config file.

    A support user on a machine where an admin secret happens to be configured
    still sends none of it. With no token either, the request carries no
    credential at all and depends on Hasura's unauthorized role.
    """
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql",
                                   "admin_secret": "s3cret"}, user=SUPPORT)
    assert "x-hasura-admin-secret" not in store.remote._headers
    assert "s3cret" not in str(store.remote._headers)
    assert not store.writable


def test_support_user_does_carry_a_token_when_there_is_one():
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql",
                                   "admin_secret": "s3cret",
                                   "token": "guest-jwt"}, user=SUPPORT)
    assert store.remote._headers == {"Authorization": "Bearer guest-jwt"}
    assert not store.writable, "a read token must not enable saving"


def test_admin_carries_the_secret_when_one_is_configured():
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql",
                                   "admin_secret": "s3cret"}, user=ADMIN)
    assert store.remote._headers["x-hasura-admin-secret"] == "s3cret"
    assert store.writable


def test_admin_without_a_configured_secret_is_not_writable():
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql"},
                         user=ADMIN)
    assert not store.writable


def test_writing_while_signed_out_is_refused():
    store, fake = store_with(secret="s", user=None)
    with pytest.raises(auth.PermissionDenied, match="not signed in"):
        store.save(profiles.get("extraa_cards"))
    assert fake.calls == []


def test_cannot_act_on_behalf_of_another_user():
    store, fake = store_with(secret="s", user=SUPPORT)
    with pytest.raises(auth.PermissionDenied):
        store.save(profiles.get("extraa_cards"), ADMIN)
    assert fake.calls == []


def test_support_user_can_still_read():
    store, _ = store_with({"data": {TABLE: [RECORD]}}, user=SUPPORT)
    assert [p.id for p in store.list()] == ["extraa_cards"]


# --- the model, the API and the database must agree -------------------------
# All three drifted once: six printed-text fields were added to the model and
# to nothing else, so saving a profile would have failed outright and reading
# one would have silently returned defaults instead of what was stored.

import re

from qrgen.profiles import Profile
from qrgen.store import hasura

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "server")

# Columns the database keeps that the model deliberately does not carry.
AUDIT_ONLY = {"created_by", "updated_by", "created_at", "updated_at"}


def schema_columns():
    sql = open(os.path.join(SERVER, "schema.sql"), encoding="utf-8").read()
    block = sql[sql.index("CREATE TABLE IF NOT EXISTS qr_profiles"):
                sql.index("-- Every version ever saved")]
    return set(re.findall(r"^\s{4}(\w+)\s+(?:text|jsonb|boolean|integer|timestamptz)",
                          block, re.M))


def test_api_requests_every_field_the_model_has():
    """A field missing here reads back as a default, not as what is stored."""
    requested = set(hasura.FIELDS.split())
    missing = set(Profile.__dataclass_fields__) - requested
    assert not missing, f"the API never asks for: {sorted(missing)}"


def test_database_has_a_column_for_every_field():
    missing = set(Profile.__dataclass_fields__) - schema_columns()
    assert not missing, (
        f"server/schema.sql has no column for: {sorted(missing)} — "
        f"add them there and in a migration file")


def test_schema_has_no_column_the_model_ignores():
    """The other direction: a column nothing reads is dead weight or a bug."""
    extra = schema_columns() - set(Profile.__dataclass_fields__) - AUDIT_ONLY
    assert not extra, f"the model ignores these columns: {sorted(extra)}"


def test_upsert_writes_every_editable_field():
    """Anything absent from update_columns silently keeps its old value."""
    listed = re.findall(r"update_columns: \[(.*?)\]", hasura.UPSERT, re.S)[0]
    columns = set(listed.replace("\n", " ").replace(",", " ").split())
    # id is the conflict target; version belongs to the database trigger.
    editable = set(Profile.__dataclass_fields__) - {"id", "version"}
    missing = editable - columns
    assert not missing, f"an update would silently skip: {sorted(missing)}"


def test_seed_inserts_every_non_defaulted_field():
    seed = open(os.path.join(SERVER, "seed_extraa_cards.sql"),
                encoding="utf-8").read()
    inserted = seed[seed.index("INSERT INTO qr_profiles ("):seed.index(") VALUES")]
    named = set(re.findall(r"\w+", inserted)) - {"INSERT", "INTO", "qr_profiles"}
    for field in ("name_font", "code_font", "name_size", "code_size",
                  "name_tracking", "code_tracking"):
        assert field in named, f"the seed does not set {field}"


def test_a_migration_exists_for_the_added_columns():
    """Anyone who ran schema.sql before these columns existed needs this."""
    migration = os.path.join(SERVER, "migration_001_printed_text.sql")
    assert os.path.exists(migration)
    sql = open(migration, encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS" in sql, "must be safe to re-run"
    for field in ("name_font", "code_font", "name_size", "code_size",
                  "name_tracking", "code_tracking"):
        assert field in sql


def test_round_trip_through_the_api_preserves_the_printed_text():
    """What a profile is saved with is what comes back."""
    record = {**RECORD, "name_font": "rob_batch.ttf", "code_font": "rob.ttf",
              "name_size": 36, "code_size": 60, "name_tracking": 2,
              "code_tracking": 1}
    profile = to_profile(record)
    assert profile.style == {"name_font": "rob_batch.ttf", "code_font": "rob.ttf",
                             "name_size": 36, "code_size": 60,
                             "name_tracking": 2, "code_tracking": 1}

    store, fake = store_with(
        {"data": {f"insert_{TABLE}_one": record}}, secret="s")
    saved = store.save(profile, ADMIN)
    sent = fake.calls[0]["payload"]["variables"]["object"]
    for key, value in profile.style.items():
        assert sent[key] == value, f"{key} was not sent"
    assert saved.style == profile.style


# --- JWT authentication -----------------------------------------------------

FAKE_JWT = "header.payload.signature"


def test_token_is_sent_as_a_bearer_header():
    """What the login API issues, and the only credential safe on a laptop."""
    fake = Fake({"data": {TABLE: []}})
    remote = HasuraStore("https://hasura.test/v1/graphql", token=FAKE_JWT,
                         transport=fake)
    remote.list()
    assert fake.calls[0]["headers"] == {"Authorization": f"Bearer {FAKE_JWT}"}
    assert remote.authenticated and not remote.writable


def test_role_header_is_not_sent_with_a_token():
    """Hasura ignores x-hasura-role unless authenticated, and a JWT already
    names its own role. Sending both invites a confusing 'role not allowed'."""
    fake = Fake({"data": {TABLE: []}})
    HasuraStore("https://hasura.test/v1/graphql", token=FAKE_JWT,
                role="guest", transport=fake).list()
    assert "x-hasura-role" not in fake.calls[0]["headers"]


def test_role_header_is_sent_with_the_admin_secret():
    """There it is useful: it drops an admin request down to a lesser role."""
    fake = Fake({"data": {TABLE: []}})
    HasuraStore("https://hasura.test/v1/graphql", admin_secret="s",
                role="guest", transport=fake).list()
    assert fake.calls[0]["headers"]["x-hasura-role"] == "guest"


def test_token_never_appears_in_the_repr():
    remote = HasuraStore("https://hasura.test/v1/graphql", token=FAKE_JWT)
    assert FAKE_JWT not in repr(remote)


def test_token_is_redacted_in_configuration():
    out = config.redacted({"api_url": "https://x.test", "token": FAKE_JWT})
    assert out["token"] == "<set>" and FAKE_JWT not in str(out)


def test_a_signed_in_user_token_beats_the_machine_one():
    """Once the login API lands, each person's own token is what is used."""
    user = auth.User("s@example.com", "S", auth.SUPPORT, token="user-token")
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql",
                                   "token": "machine-token"}, user=user)
    assert store.remote._headers["Authorization"] == "Bearer user-token"


def test_a_token_does_not_grant_write_access():
    """The guest token is read-only; saving must still refuse before the wire."""
    fake = Fake()
    remote = HasuraStore("https://hasura.test/v1/graphql", token=FAKE_JWT,
                         transport=fake)
    with pytest.raises(StoreError, match="needs admin credentials"):
        remote.save(RECORD, "someone@example.com")
    assert fake.calls == []


# --- caching and refresh ----------------------------------------------------

def test_records_are_fetched_once_and_reused():
    """Every list() used to hit the network -- eight requests to type a word
    into the profile search box."""
    store, fake = store_with(*[{"data": {TABLE: [RECORD]}}] * 4)
    store.list()
    store.get("extraa_cards")
    for _ in "extraa":
        store.list(include_inactive=True)
    assert len(fake.calls) == 1


def test_refresh_asks_again():
    store, fake = store_with({"data": {TABLE: [RECORD]}},
                             {"data": {TABLE: [{**RECORD, "version": 9}]}})
    assert store.list()[0].version == RECORD["version"]
    store.refresh()
    assert store.list()[0].version == 9
    assert len(fake.calls) == 2


def test_a_save_invalidates_what_is_held():
    """Otherwise an admin saves a profile and keeps seeing the old one."""
    later = {**RECORD, "version": RECORD["version"] + 1}
    store, _ = store_with({"data": {TABLE: [RECORD]}},
                          {"data": {f"insert_{TABLE}_one": later}},
                          {"data": {TABLE: [later]}}, secret="s")
    assert store.list()[0].version == RECORD["version"]
    store.save(to_profile(RECORD), ADMIN)
    assert store.list()[0].version == RECORD["version"] + 1


def test_deactivating_invalidates_what_is_held():
    store, _ = store_with(
        {"data": {TABLE: [RECORD]}},
        {"data": {f"update_{TABLE}_by_pk": {**RECORD, "active": False}}},
        {"data": {TABLE: [{**RECORD, "active": False}]}},
        secret="s")
    assert len(store.list()) == 1
    store.deactivate("extraa_cards", ADMIN)
    assert store.list() == []


def test_a_failed_refresh_keeps_working_from_the_cache():
    store, _ = store_with({"data": {TABLE: [RECORD]}}, OSError("down"))
    assert store.list()[0].id == "extraa_cards"
    store.refresh()
    assert store.list()[0].id == "extraa_cards"
    assert store.source == CACHED
