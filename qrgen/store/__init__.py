"""Where profiles come from.

One object the rest of the app talks to. It tries the shared store, falls back
to the last good cache, and falls back again to the profiles bundled with the
app, reporting which of the three it used so the UI can say so.

Reads degrade. Writes do not: saving a profile requires the real store, because
a queued write would silently overwrite another admin's change.
"""

import time

from qrgen import auth
from qrgen import config as app_config
from qrgen import profiles as builtin_profiles
from qrgen.profiles import Profile, ProfileError
from qrgen.store import cache
from qrgen.store.hasura import HasuraStore, StoreError

# Columns the API returns that are not part of the profile model.
_EXTRA = ("created_by", "updated_by", "created_at", "updated_at", "__typename")

LIVE, CACHED, BUILTIN = "live", "cached", "builtin"


def to_profile(record):
    """Turn one API row into a validated :class:`Profile`."""
    fields = {k: v for k, v in record.items() if k not in _EXTRA}
    return Profile.from_dict(fields)


class ProfileStore:
    """Profiles for one signed-in user.

    ``user`` decides what credential is presented. A support user's requests
    never carry the admin secret, even on a machine where one is configured --
    authority comes from the role, not from what happens to be in a config file.
    """

    def __init__(self, remote=None, settings=None, user=None):
        self.settings = app_config.load() if settings is None else settings
        self._remote = remote
        self.user = user
        self.source = None
        self.fetched_at = None
        self.error = None
        # Fetched once, then reused. Without this every call went to the
        # network -- eight requests to type a six-letter word into the profile
        # search box. Cleared by refresh().
        self._records = None

    @property
    def remote(self):
        if self._remote is None:
            admin = self.user is None or self.user.is_admin
            # A signed-in user's own token wins; otherwise fall back to one
            # configured for the machine. Either way it names its own role.
            token = (self.user.token if self.user and self.user.token
                     else self.settings.get("token"))
            self._remote = HasuraStore(
                self.settings.get("api_url"),
                admin_secret=self.settings.get("admin_secret") if admin else None,
                token=token,
                role=(auth.HASURA_ROLE.get(self.user.role) if self.user
                      else self.settings.get("role")))
        return self._remote

    @property
    def writable(self):
        if self.user is not None and not self.user.can("profile.edit"):
            return False
        try:
            return self.remote.writable
        except StoreError:
            return False

    def _authorise(self, permission):
        if self.user is None:
            raise auth.PermissionDenied(
                f"not signed in; {permission} requires an authenticated user")
        return self.user.require(permission)

    # --- reading ------------------------------------------------------------

    def refresh(self):
        """Forget what we have and ask the store again.

        The only thing that re-reads the network. Everything else works from
        what this last returned, so a profile edited elsewhere appears when
        somebody asks for it, not at a moment of the network's choosing.
        """
        self._records = None
        self.list()
        return self

    @property
    def age(self):
        """Seconds since the records in hand were fetched, if they are cached."""
        if self.source != CACHED or not self.fetched_at:
            return None
        return max(0.0, time.time() - self.fetched_at)

    def list(self, include_inactive=False):
        records = self._fetch()
        found = []
        for record in records:
            try:
                profile = to_profile(record)
            except ProfileError as exc:
                # One malformed row must not hide every other profile. It is
                # simply not offered, and the reason is kept for the UI.
                self.error = f"ignored profile {record.get('id')!r}: {exc}"
                continue
            if profile.active or include_inactive:
                found.append(profile)
        return sorted(found, key=lambda p: p.name)

    def get(self, profile_id):
        for profile in self.list(include_inactive=True):
            if profile.id == profile_id:
                return profile
        raise ProfileError(
            f"no profile with id {profile_id!r}; available: "
            f"{sorted(p.id for p in self.list(include_inactive=True))}")

    def _fetch(self):
        if self._records is not None:
            return self._records
        self._records = self._load()
        return self._records

    def _load(self):
        try:
            records = self.remote.list()
            cache.write(records)
            self.source, self.fetched_at, self.error = LIVE, None, None
            return records
        except StoreError as exc:
            self.error = str(exc)

        records, fetched_at = cache.read()
        if records is not None:
            self.source, self.fetched_at = CACHED, fetched_at
            return records

        self.source, self.fetched_at = BUILTIN, None
        return [p.to_dict() for p in builtin_profiles.load_builtin().values()]

    @property
    def status(self):
        if self.source == LIVE:
            return "Profiles up to date"
        if self.source == CACHED:
            return f"Offline · using profiles saved {_ago(self.age)}"
        if self.source == BUILTIN:
            return "Offline · using the profiles built into this app"
        return "Profiles not loaded yet"

    # --- writing ------------------------------------------------------------

    def _invalidate(self):
        """After a write, what we hold is stale."""
        self._records = None

    def save(self, profile, actor=None):
        """Create or update a profile. Admin only; requires the live store."""
        actor = self._actor(actor, "profile.edit")
        if not isinstance(profile, Profile):
            # Validated before anything is sent, and tolerant of an API-shaped
            # dict being handed straight back (created_by, __typename, ...).
            profile = to_profile(profile)
        record = self.remote.save(profile.to_dict(), actor)
        self._invalidate()
        self.source = LIVE
        return to_profile(record)

    def deactivate(self, profile_id, actor=None):
        actor = self._actor(actor, "profile.deactivate")
        record = self.remote.set_active(profile_id, False, actor)
        self._invalidate()
        return to_profile(record)

    def reactivate(self, profile_id, actor=None):
        actor = self._actor(actor, "profile.edit")
        record = self.remote.set_active(profile_id, True, actor)
        self._invalidate()
        return to_profile(record)

    def _actor(self, actor, permission):
        """Authorise the write and return the email recorded against it.

        Accepts a User, or a bare email when the store was constructed for a
        signed-in user. Either way the permission check happens here, in the
        service layer, where the UI cannot skip it.
        """
        if isinstance(actor, auth.User):
            actor.require(permission)
            if self.user is not None and actor.email != self.user.email:
                raise auth.PermissionDenied(
                    "cannot act on behalf of another user")
            return actor.email
        self._authorise(permission)
        return actor or self.user.email


def _ago(seconds):
    if seconds is None:
        return "earlier"
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"
