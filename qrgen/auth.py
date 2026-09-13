"""Authentication and role-based authorization.

Mock for the MVP, shaped so the real thing drops in without a rewrite: a
provider takes an email and a password and returns a :class:`User` carrying a
role and, eventually, a token. When the login API exists, write a provider that
calls it and returns a User with ``token`` set -- everything downstream already
passes that token through to Hasura, which enforces row-level permissions.

Permissions are checked in the service layer, not in the UI. Hiding a button is
a courtesy; refusing the call is the control.

Generate a password hash for mock_users.json with:

    python -m qrgen.auth "the password"
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from qrgen import paths
from typing import Optional

ADMIN = "admin"
SUPPORT = "support"

# Hasura roles this application accepts, and what each means here. A token for
# any other role -- `reseller`, say -- is refused at login: those accounts
# belong to other Extraa products and have no business generating card batches.
ROLE_FROM_HASURA = {
    "superadmin": ADMIN,
    "guest": SUPPORT,
}

HASURA_CLAIMS = "https://hasura.io/jwt/claims"
DEFAULT_ROLE_CLAIM = "x-hasura-default-role"

# What each role may do. The support role covers viewing profiles and
# generating images; admin adds profile management.
PERMISSIONS = {
    SUPPORT: frozenset({"profile.view", "batch.generate"}),
    ADMIN: frozenset({"profile.view", "batch.generate",
                      "profile.create", "profile.edit", "profile.deactivate"}),
}

# The reverse map, for the admin-secret path where x-hasura-role is honoured.
HASURA_ROLE = {SUPPORT: os.environ.get("EXTRAA_QR_READ_ROLE") or "guest",
               ADMIN: None}

LOGIN_URL = os.environ.get("EXTRAA_QR_LOGIN_URL") or ""

MOCK_USERS = paths.resource("mock_users.json")

ITERATIONS = 200_000
ALGORITHM = "pbkdf2_sha256"


class AuthError(Exception):
    """Login failed. Deliberately says nothing about why."""


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class User:
    email: str
    name: str
    role: str
    token: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        if self.role not in PERMISSIONS:
            raise AuthError(f"unknown role {self.role!r}")

    @property
    def permissions(self):
        return PERMISSIONS[self.role]

    @property
    def is_admin(self):
        return self.role == ADMIN

    def can(self, permission):
        return permission in self.permissions

    def require(self, permission):
        if not self.can(permission):
            raise PermissionDenied(
                f"{self.email} is {self.role} and cannot {permission}")
        return self


def hash_password(password, salt=None, iterations=ITERATIONS):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "%s$%d$%s$%s" % (ALGORITHM, iterations,
                            base64.b64encode(salt).decode(),
                            base64.b64encode(digest).decode())


def verify_password(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            base64.b64decode(salt), int(iterations))
    except (ValueError, TypeError):
        return False
    # Constant-time: a timing difference here leaks the hash a byte at a time.
    return hmac.compare_digest(candidate, base64.b64decode(expected))


# A real hash to compare against when the email is unknown, so a missing user
# and a wrong password take the same time and cannot be told apart.
_DUMMY = hash_password("dummy", salt=b"\x00" * 16, iterations=ITERATIONS)


class MockAuthProvider:
    username_label = "Email"

    """Reads users from a JSON file. Passwords are stored hashed, never plain.

    The credentials themselves are documented in docs/AUTH.md rather than
    written into the source.
    """

    def __init__(self, path=None):
        self.path = path or os.environ.get("EXTRAA_QR_MOCK_USERS") or MOCK_USERS

    def _users(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                return {u["email"].lower(): u for u in json.load(fh)}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AuthError(f"cannot read the user list: {exc}") from None

    def authenticate(self, email, password):
        record = self._users().get((email or "").strip().lower())
        if record is None:
            verify_password(password or "", _DUMMY)  # equalise the timing
            raise AuthError("incorrect email or password")
        if not verify_password(password or "", record["password"]):
            raise AuthError("incorrect email or password")
        return User(email=record["email"], name=record.get("name", record["email"]),
                    role=record["role"])


def decode_claims(token):
    """Read a JWT's payload without verifying its signature.

    Verification is deliberately not done here, and it is worth being precise
    about why. This application is not the resource server: Hasura holds the
    signing key and validates the token on every request. What is read here
    decides only which buttons a person sees. If a forged token claimed
    superadmin, the app would show the profile editor and Hasura would then
    refuse every write it attempted -- the boundary that matters is enforced
    where the data lives, not in a desktop binary anyone can edit.
    """
    try:
        payload = token.split(".")[1]
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(raw)
    except (AttributeError, IndexError, ValueError, TypeError) as exc:
        raise AuthError(f"the login service returned an unreadable token: {exc}")
    if not isinstance(claims, dict):
        raise AuthError("the login service returned an unreadable token")
    return claims


def role_from_token(token):
    """Map the token's Hasura role onto this application's two roles."""
    claims = decode_claims(token).get(HASURA_CLAIMS) or {}
    hasura_role = claims.get(DEFAULT_ROLE_CLAIM)
    if not hasura_role:
        raise AuthError("the token carries no Hasura role")
    try:
        return ROLE_FROM_HASURA[hasura_role]
    except KeyError:
        raise AuthError(
            f"the account has the {hasura_role!r} role, which cannot use this "
            f"tool. Accepted roles: {', '.join(sorted(ROLE_FROM_HASURA))}"
        ) from None


class ApiAuthProvider:
    """Signs in against the Extraa login service.

    Same shape as :class:`MockAuthProvider`, so the UI does not know or care
    which one it is holding.
    """

    username_label = "Username"

    def __init__(self, url=None, timeout=20, transport=None):
        self.url = url or LOGIN_URL
        self.timeout = timeout
        self._transport = transport or _post_json

    def authenticate(self, username, password):
        if not self.url:
            raise AuthError("no login service configured "
                            "(set EXTRAA_QR_LOGIN_URL)")
        if not (username or "").strip() or not password:
            raise AuthError("incorrect username or password")

        try:
            response = self._transport(
                self.url, {"username": username.strip(), "password": password},
                self.timeout)
        except AuthError:
            raise
        except Exception as exc:
            # Distinguished from a wrong password on purpose: one is the user's
            # problem to fix, the other is not.
            raise AuthError(
                f"the login service could not be reached: {exc}") from None

        # The Lambda wraps its result in a "body" key.
        body = response.get("body", response) if isinstance(response, dict) else {}
        if not isinstance(body, dict) or not body.get("status"):
            raise AuthError(body.get("message") or "incorrect username or password"
                            if isinstance(body, dict) else
                            "incorrect username or password")

        token = body.get("token")
        if not token:
            raise AuthError("the login service returned no token")

        return User(email=str(body.get("ec_account_id") or username),
                    name=decode_claims(token).get("name") or str(username),
                    role=role_from_token(token), token=token)


def _post_json(url, payload, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # A 4xx usually carries the service's own message; surface it.
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            raise AuthError("incorrect username or password") from None


def default_provider():
    """The API provider once a login URL is configured, otherwise the mock."""
    return ApiAuthProvider() if LOGIN_URL else MockAuthProvider()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('usage: python -m qrgen.auth "the password"')
    print(hash_password(sys.argv[1]))
