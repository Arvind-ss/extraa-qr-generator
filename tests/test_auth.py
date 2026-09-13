import json
import time

import pytest

from qrgen import auth
from qrgen.auth import AuthError, MockAuthProvider, PermissionDenied, User

# Documented in docs/AUTH.md. Not production credentials.
ADMIN_LOGIN = ("admin@example.com", "extraa-admin")
SUPPORT_LOGIN = ("support@example.com", "extraa-support")


@pytest.fixture
def provider():
    return MockAuthProvider()


# --- passwords --------------------------------------------------------------

def test_hash_is_salted_so_two_users_with_one_password_differ():
    a = auth.hash_password("same password")
    b = auth.hash_password("same password")
    assert a != b
    assert auth.verify_password("same password", a)
    assert auth.verify_password("same password", b)


def test_wrong_password_is_rejected():
    encoded = auth.hash_password("correct")
    assert not auth.verify_password("wrong", encoded)
    assert not auth.verify_password("", encoded)


@pytest.mark.parametrize("junk", ["", "not-a-hash", "a$b$c$d", "$$$"])
def test_malformed_hash_never_verifies(junk):
    assert not auth.verify_password("anything", junk)


def test_no_plaintext_password_is_stored():
    with open(auth.MOCK_USERS, encoding="utf-8") as fh:
        raw = fh.read()
    for _, password in (ADMIN_LOGIN, SUPPORT_LOGIN):
        assert password not in raw
    for record in json.loads(raw):
        assert record["password"].startswith("pbkdf2_sha256$")


# --- login ------------------------------------------------------------------

def test_admin_logs_in(provider):
    user = provider.authenticate(*ADMIN_LOGIN)
    assert user.role == auth.ADMIN and user.is_admin
    assert user.name == "Support Lead"


def test_support_logs_in(provider):
    user = provider.authenticate(*SUPPORT_LOGIN)
    assert user.role == auth.SUPPORT and not user.is_admin


def test_email_is_case_and_space_insensitive(provider):
    assert provider.authenticate("  ADMIN@Example.COM  ", "extraa-admin").is_admin


@pytest.mark.parametrize("email,password", [
    ("admin@example.com", "wrong"),
    ("nobody@example.com", "extraa-admin"),
    ("", ""),
    (None, None),
])
def test_bad_login_is_refused(provider, email, password):
    with pytest.raises(AuthError):
        provider.authenticate(email, password)


def test_failure_message_does_not_reveal_whether_the_email_exists(provider):
    messages = set()
    for email, password in [("admin@example.com", "wrong"),
                            ("nobody@example.com", "wrong")]:
        with pytest.raises(AuthError) as caught:
            provider.authenticate(email, password)
        messages.add(str(caught.value))
    assert len(messages) == 1, messages


def test_unknown_email_is_not_measurably_faster(provider):
    """A fast rejection for unknown emails is a user-enumeration oracle."""
    def elapsed(email):
        start = time.perf_counter()
        with pytest.raises(AuthError):
            provider.authenticate(email, "wrong password")
        return time.perf_counter() - start

    known = min(elapsed("admin@example.com") for _ in range(3))
    unknown = min(elapsed("nobody@example.com") for _ in range(3))
    assert 0.4 < unknown / known < 2.5, (known, unknown)


def test_missing_user_file_is_a_clear_error(tmp_path):
    with pytest.raises(AuthError, match="cannot read the user list"):
        MockAuthProvider(str(tmp_path / "nope.json")).authenticate("a@b.c", "x")


def test_user_file_can_be_overridden_by_environment(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    path.write_text(json.dumps([{"email": "other@example.com", "name": "Other",
                                 "role": "support",
                                 "password": auth.hash_password("pw")}]))
    monkeypatch.setenv("EXTRAA_QR_MOCK_USERS", str(path))
    assert MockAuthProvider().authenticate("other@example.com", "pw").role == "support"


# --- roles ------------------------------------------------------------------

def test_support_can_view_and_generate():
    user = User("s@example.com", "S", auth.SUPPORT)
    assert user.can("profile.view") and user.can("batch.generate")


@pytest.mark.parametrize("permission", [
    "profile.create", "profile.edit", "profile.deactivate"])
def test_support_cannot_manage_profiles(permission):
    user = User("s@example.com", "S", auth.SUPPORT)
    assert not user.can(permission)
    with pytest.raises(PermissionDenied, match="is support and cannot"):
        user.require(permission)


def test_admin_can_do_everything_support_can():
    admin = User("a@example.com", "A", auth.ADMIN)
    support = User("s@example.com", "S", auth.SUPPORT)
    assert support.permissions <= admin.permissions


def test_unknown_role_is_refused():
    with pytest.raises(AuthError, match="unknown role"):
        User("x@example.com", "X", "superuser")


def test_user_is_immutable():
    user = User("s@example.com", "S", auth.SUPPORT)
    with pytest.raises(Exception):
        user.role = auth.ADMIN


def test_token_is_not_in_the_repr():
    """Tokens land here once the login API exists; they must not reach logs."""
    user = User("s@example.com", "S", auth.SUPPORT, token="secret-jwt")
    assert "secret-jwt" not in repr(user)


def test_support_maps_to_the_limited_hasura_role():
    assert auth.HASURA_ROLE[auth.SUPPORT] == "guest"
    assert auth.HASURA_ROLE[auth.ADMIN] is None  # superadmin, via admin secret


# --- the real login service -------------------------------------------------
# No network: a fake transport stands in for the Lambda.

import base64 as _b64


def make_token(hasura_role, name="7708788435", allowed=None):
    """A JWT shaped like the one the Extraa login service issues."""
    def part(data):
        raw = json.dumps(data).encode()
        return _b64.urlsafe_b64encode(raw).decode().rstrip("=")
    claims = {
        "name": name, "iat": 1789282523,
        auth.HASURA_CLAIMS: {
            "x-hasura-allowed-roles": allowed or [hasura_role],
            "x-hasura-default-role": hasura_role,
            "x-hasura-ec-account-id": "4171",
        },
    }
    return f"{part({'alg': 'HS256', 'typ': 'JWT'})}.{part(claims)}.signature"


def api(response):
    """An ApiAuthProvider whose transport returns `response`."""
    calls = []

    def transport(url, payload, timeout):
        calls.append({"url": url, "payload": payload})
        if isinstance(response, Exception):
            raise response
        return response

    provider = auth.ApiAuthProvider(url="https://login.test/", transport=transport)
    return provider, calls


def success(hasura_role):
    return {"body": {"status": True, "message": "Successfully logged in",
                     "account_id": 4171, "ec_account_id": "4171",
                     "token": make_token(hasura_role), "role": 0}}


def test_superadmin_token_becomes_an_admin():
    provider, calls = api(success("superadmin"))
    user = provider.authenticate("7708788435", "12")
    assert user.role == auth.ADMIN and user.is_admin
    assert user.token and user.email == "4171"
    assert calls[0]["payload"] == {"username": "7708788435", "password": "12"}


def test_guest_token_becomes_a_support_user():
    provider, _ = api(success("guest"))
    user = provider.authenticate("7708788435", "12")
    assert user.role == auth.SUPPORT and not user.is_admin
    assert user.can("batch.generate") and not user.can("profile.edit")


@pytest.mark.parametrize("other", ["reseller", "merchant", "user", "anonymous"])
def test_any_other_hasura_role_is_refused(other):
    """Accounts from the other Extraa products must not reach this tool.

    The account used for testing has exactly this shape -- it authenticates
    successfully and is then refused here.
    """
    provider, _ = api(success(other))
    with pytest.raises(AuthError, match=f"{other!r} role, which cannot use"):
        provider.authenticate("7708788435", "12")


def test_the_role_comes_from_the_token_not_the_response_body():
    """The body carries its own `role` field; it is deliberately ignored."""
    response = success("guest")
    response["body"]["role"] = 999
    provider, _ = api(response)
    assert provider.authenticate("u", "p").role == auth.SUPPORT


def test_allowed_roles_do_not_override_the_default_role():
    """A token allowed to become superadmin but defaulting to reseller is
    still a reseller here."""
    token = make_token("reseller", allowed=["reseller", "superadmin"])
    provider, _ = api({"body": {"status": True, "token": token}})
    with pytest.raises(AuthError, match="reseller"):
        provider.authenticate("u", "p")


def test_a_failed_login_reports_the_services_message():
    provider, _ = api({"body": {"status": False,
                                "message": "Invalid username or password"}})
    with pytest.raises(AuthError, match="Invalid username or password"):
        provider.authenticate("7708788435", "wrong")


def test_an_unreachable_service_is_not_reported_as_a_bad_password():
    """One is the user's problem to fix; the other is not."""
    provider, _ = api(OSError("connection refused"))
    with pytest.raises(AuthError, match="could not be reached"):
        provider.authenticate("7708788435", "12")


def test_blank_credentials_never_reach_the_network():
    provider, calls = api(success("guest"))
    for username, password in (("", "x"), ("7708788435", ""), ("  ", "x")):
        with pytest.raises(AuthError):
            provider.authenticate(username, password)
    assert calls == []


@pytest.mark.parametrize("junk", ["", "not-a-jwt", "a.b", "a.!!!.c"])
def test_an_unreadable_token_is_refused(junk):
    provider, _ = api({"body": {"status": True, "token": junk}})
    with pytest.raises(AuthError):
        provider.authenticate("u", "p")


def test_a_token_with_no_hasura_claims_is_refused():
    header = _b64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = _b64.urlsafe_b64encode(b'{"name":"x"}').decode().rstrip("=")
    provider, _ = api({"body": {"status": True,
                                "token": f"{header}.{payload}.sig"}})
    with pytest.raises(AuthError, match="carries no Hasura role"):
        provider.authenticate("u", "p")


def test_a_response_with_no_token_is_refused():
    provider, _ = api({"body": {"status": True, "message": "ok"}})
    with pytest.raises(AuthError, match="no token"):
        provider.authenticate("u", "p")


def test_provider_choice_follows_the_configuration(monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_URL", "")
    assert isinstance(auth.default_provider(), auth.MockAuthProvider)
    monkeypatch.setattr(auth, "LOGIN_URL", "https://login.test/")
    assert isinstance(auth.default_provider(), auth.ApiAuthProvider)


def test_the_signed_in_token_reaches_the_profile_store():
    """The whole point: log in here, and Hasura sees that person's role."""
    from qrgen.store import ProfileStore

    provider, _ = api(success("guest"))
    user = provider.authenticate("7708788435", "12")
    store = ProfileStore(settings={"api_url": "https://hasura.test/v1/graphql"},
                         user=user)
    assert store.remote._headers["Authorization"] == f"Bearer {user.token}"
