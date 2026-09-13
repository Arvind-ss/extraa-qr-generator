# Profile store — setup

## The Extraa backend

| | |
|---|---|
| Endpoint | `https://backend.extraa.in/v1/graphql` |
| Table | **`ec_qr_profiles`** |
| Read role | **`guest`** — select on every column |

The table name is not hardcoded: `EXTRAA_QR_TABLE` overrides it, and the read
role comes from `EXTRAA_QR_READ_ROLE`. Defaults are the two above.

### ⚠️ `guest` is currently unreachable from the app

Measured against the live endpoint on 2026-09-13:

```
anonymous request              -> query_root exposes one field: no_queries_available
anonymous + x-hasura-role: guest -> identical
```

**Hasura only honours `x-hasura-role` on an *authenticated* request.** The header
is ignored otherwise, and the request falls back to
`HASURA_GRAPHQL_UNAUTHORIZED_ROLE`, which on this instance grants nothing. The
`guest` role and its permissions are correct — nothing can reach them.

Three ways to open it, in the order I would pick them:

1. **`HASURA_GRAPHQL_UNAUTHORIZED_ROLE=guest`** on the instance. Anonymous
   requests become `guest`, the desktop app ships no secret at all, and reads
   work immediately. Instance-wide, so check that `guest` has permissions on
   `ec_qr_profiles` and on nothing else first.
2. **The login API you are building.** It returns a JWT carrying
   `x-hasura-role`, Hasura validates it, and the header is honoured. This is the
   right long-term answer and needs no change here — `User.token` already exists
   and flows through.
3. **Admin secret on admin machines only.** Works today, but it is god-mode over
   the whole database and must never reach a support laptop.

Check any of them with:

```bash
EXTRAA_QR_API_URL=https://backend.extraa.in/v1/graphql .venv/bin/python cli.py store
```

It reports what the endpoint accepts as a support user and, if an admin secret
is configured, as an admin. Add `EXTRAA_QR_ADMIN_SECRET=...` in front to test
the write path — the secret is read from the environment and never logged.

---


## The SQL files

`ec_qr_profiles` already exists on the Extraa backend with every column this
application needs, including the six printed-text ones — confirmed against the
live schema. **So none of the SQL below is needed there.** It is kept for a
fresh deployment, and as the written record of what the table should contain.

```bash
psql "$DATABASE_URL" -f server/schema.sql                    # fresh install
psql "$DATABASE_URL" -f server/migration_001_printed_text.sql  # older install
psql "$DATABASE_URL" -f server/seed_extraa_cards.sql         # the one profile
```

`schema.sql` creates the table as `qr_profiles`; the Extraa deployment calls it
`ec_qr_profiles` and the client follows via `EXTRAA_QR_TABLE`. If you run the
schema fresh somewhere, either rename the table or set that variable.

Do **not** track `qr_profile_versions` in Hasura unless you want the audit log
queryable over the API; the trigger writes to it either way.

Nothing in this repository connects to your database on its own. The app talks
to Hasura over HTTPS and to nothing else.

---

## The credential problem — read this before granting anything

**Anything shipped inside a desktop application is public.** A support user can
open the bundle and read any secret in it. So the question is not "how do we
hide the credential" but "what can the credential reach if it leaks".

Hasura's only shared-secret authentication is `HASURA_GRAPHQL_ADMIN_SECRET`,
which is **god-mode over the entire database** — cards, users, phone numbers,
everything in `scriptcodes/.env`. Putting that in an app installed on support
laptops would be the single worst decision in this project.

So the read path and the write path are separated.

### Reads (every support user) — no credential at all

Set Hasura's unauthorized role and give it exactly one permission:

```
HASURA_GRAPHQL_UNAUTHORIZED_ROLE=guest
```

The `guest` role already has select on every column of `ec_qr_profiles`. Two
things worth tightening while you are there:

| Operation | Setting |
|---|---|
| select | Row filter: `{"active": {"_eq": true}}` — the app asks for inactive profiles only in the admin screen, which uses the admin path |
| | Columns: everything **except** `created_by` and `updated_by`, which are internal email addresses |
| insert / update / delete | none |

A request with no `x-hasura-admin-secret` header now returns active profiles and
can reach nothing else. The desktop app ships with no secret because it needs
none.

⚠️ **`HASURA_GRAPHQL_UNAUTHORIZED_ROLE` is instance-wide.** Every unauthenticated
request to `backend.extraa.in` would get this role. That is safe only if `guest`
has permissions on `ec_qr_profiles` and on **no other table** — and this is a
production backend, so check its full permission list before setting it. That
single caveat is the reason option 2, the login API, is the better answer.

### Writes (admins only) — credential supplied at runtime, never bundled

For the MVP an admin saving a profile supplies the Hasura admin secret at
runtime. It is read from the environment or a `0600` config file on that admin's
machine and is never written into the app bundle, the repository, or a log.

This is defensible because an admin/support lead is someone who already has
database access — it grants them nothing they did not have. It is **not**
defensible for anyone else, which is why support users never see it.

```bash
export EXTRAA_QR_API_URL="https://<your-hasura>/v1/graphql"
export EXTRAA_QR_ADMIN_SECRET="..."      # admin machines only
```

Or `~/.config/extraa-qr/config.json` (macOS: `~/Library/Application Support/...`),
created with mode `0600`:

```json
{"api_url": "https://<your-hasura>/v1/graphql", "admin_secret": "..."}
```

The app refuses to read a config file that is group- or world-readable.

### Replacing this properly

The above is an interim arrangement tied to mock authentication. The real fix is
Hasura in JWT mode: each user authenticates, gets a token carrying
`x-hasura-role: guest` (or an admin role), and no shared secret exists anywhere.
`qrgen/store/hasura.py` already sends whatever headers it is configured with, so
switching is a configuration change plus a real identity provider — no rewrite.

The Postgres roles created by `schema.sql` (`qr_profile_reader`,
`qr_profile_writer`) are there for that future, and for anything connecting
directly rather than through Hasura.

---

## What the app does when the store is unreachable

1. Ask Hasura.
2. On any failure, use the profiles cached on disk from the last successful
   fetch, and say so in the UI.
3. If there is no cache, fall back to the profiles bundled in `profiles/`.

Generation therefore keeps working on a bad connection. Editing does not —
saving a profile requires the store to be reachable, because a queued write
would silently overwrite somebody else's change.

## Deletion

There is no `DELETE` grant for anyone. Profiles are deactivated. A batch
generated last year has to stay explicable, and the version history exists for
exactly that reason.
