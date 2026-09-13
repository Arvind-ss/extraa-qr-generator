"""Hasura GraphQL client for the shared profile store.

stdlib urllib, not requests -- four queries do not justify a dependency in a
bundle that has to ship to two operating systems.

Reads normally carry no credential at all: Hasura's unauthorized role is
configured to see active profiles and nothing else. Writes carry an admin
secret supplied at runtime on an admin's machine. See server/README.md.
"""

import json
import os
import urllib.error
import urllib.request

# The table as tracked in Hasura. Overridable because the name is a deployment
# detail, not a property of this application.
TABLE = os.environ.get("EXTRAA_QR_TABLE") or "ec_qr_profiles"

# Every column the Profile model has. Kept in step by
# tests/test_store.py::test_api_requests_every_field_the_model_has -- a field
# missing here reads back as a silent default instead of what is stored.
FIELDS = """
    id name renderer required_columns qr_content top_text bottom_text
    filename output_format unique_columns validation active version
    name_font code_font name_size code_size name_tracking code_tracking
"""

LIST = ("query Profiles { %s(order_by: {name: asc}) { %s } }"
        % (TABLE, FIELDS))

GET = ("query Profile($id: String!) { "
       "%s_by_pk(id: $id) { %s } }" % (TABLE, FIELDS))

UPSERT = """
mutation SaveProfile($object: %(table)s_insert_input!) {
  insert_%(table)s_one(
    object: $object,
    on_conflict: {
      constraint: %(table)s_pkey,
      update_columns: [name, renderer, required_columns, qr_content, top_text,
                       bottom_text, filename, output_format, unique_columns,
                       validation, active, updated_by,
                       name_font, code_font, name_size, code_size,
                       name_tracking, code_tracking]
    }
  ) { %(fields)s }
}
""" % {"table": TABLE, "fields": FIELDS}

SET_ACTIVE = ("mutation SetActive($id: String!, $active: Boolean!, $actor: String) { "
              "update_%s_by_pk(pk_columns: {id: $id}, "
              "_set: {active: $active, updated_by: $actor}) { %s } }"
              % (TABLE, FIELDS))


class StoreError(RuntimeError):
    """The store could not be reached, or refused the request."""


def _post(url, headers, payload, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class HasuraStore:
    """Three ways to authenticate, in the order they should be preferred.

    * ``token`` -- a JWT, sent as ``Authorization: Bearer``. What the login API
      issues, and the only one that is safe to hold on a support laptop,
      because it carries exactly one role.
    * nothing -- relies on Hasura's unauthorized role. Works only if the
      instance sets one; ``x-hasura-role`` alone is ignored on an
      unauthenticated request.
    * ``admin_secret`` -- god-mode over the whole database. Admin machines
      only, supplied at runtime, never bundled.
    """

    def __init__(self, url, admin_secret=None, role=None, token=None,
                 timeout=10, transport=_post):
        if not url:
            raise StoreError("no profile API URL configured "
                             "(set EXTRAA_QR_API_URL)")
        self.url = url
        self.timeout = timeout
        self._transport = transport
        self._headers = {}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        if admin_secret:
            self._headers["x-hasura-admin-secret"] = admin_secret
        # Hasura honours this only on an authenticated request, and a JWT
        # already names its own role, so it is sent only alongside the admin
        # secret -- where it usefully drops the request down to that role.
        if role and admin_secret:
            self._headers["x-hasura-role"] = role

    @property
    def writable(self):
        """Only a client holding a write credential may save profiles."""
        return "x-hasura-admin-secret" in self._headers

    @property
    def authenticated(self):
        return bool(self._headers)

    def __repr__(self):  # never leak a credential into a traceback or a log
        return (f"HasuraStore({self.url!r}, authenticated={self.authenticated}, "
                f"writable={self.writable})")

    def query(self, document, variables=None):
        try:
            body = self._transport(self.url, self._headers,
                                   {"query": document, "variables": variables or {}},
                                   self.timeout)
        except urllib.error.HTTPError as exc:
            raise StoreError(f"profile API returned HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise StoreError(f"could not reach the profile API: {exc}") from None

        # GraphQL reports failures inside a 200 response.
        if body.get("errors"):
            messages = "; ".join(e.get("message", "?") for e in body["errors"])
            raise StoreError(f"profile API rejected the request: {messages}")
        if "data" not in body:
            raise StoreError("profile API returned no data")
        return body["data"]

    def list(self):
        return self.query(LIST)[TABLE]

    def get(self, profile_id):
        return self.query(GET, {"id": profile_id})[f"{TABLE}_by_pk"]

    def save(self, record, actor):
        if not self.writable:
            raise StoreError("saving a profile needs admin credentials")
        payload = dict(record, updated_by=actor)
        payload.setdefault("created_by", actor)
        # The database owns the version number; sending one would race with
        # another admin saving the same profile.
        payload.pop("version", None)
        return self.query(UPSERT, {"object": payload})[f"insert_{TABLE}_one"]

    def set_active(self, profile_id, active, actor):
        if not self.writable:
            raise StoreError("changing a profile needs admin credentials")
        return self.query(SET_ACTIVE, {"id": profile_id, "active": active,
                                       "actor": actor})[f"update_{TABLE}_by_pk"]
