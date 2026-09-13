# Authentication and roles

## Mock credentials (MVP)

Authentication is mocked until the login API exists. These are the only two
accounts, and they are deliberately documented here rather than written into the
source. They are **not** production credentials and must not be reused anywhere.

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `extraa-admin` | admin |
| `support@example.com` | `extraa-support` | support |

Passwords are stored in `mock_users.json` as salted PBKDF2-SHA256 hashes
(200,000 iterations), never in plain text. To add or change a user:

```bash
python -m qrgen.auth "the new password"     # prints the hash
```

Paste the result into `mock_users.json`. `EXTRAA_QR_MOCK_USERS` overrides the
file location, which is how tests use their own list.

## Roles

| Permission | support | admin |
|---|:--:|:--:|
| `profile.view` | ✅ | ✅ |
| `batch.generate` | ✅ | ✅ |
| `profile.create` | — | ✅ |
| `profile.edit` | — | ✅ |
| `profile.deactivate` | — | ✅ |

`admin` maps to Hasura superadmin. `support` maps to the limited `qr_support`
Hasura role, which can read active profiles and nothing else.

Permissions are enforced in `qrgen/store`, not in the UI. Hiding a button is a
courtesy; refusing the call is the control. A support user's requests never
carry the admin secret **even on a machine where one is configured** — authority
comes from the role, not from what happens to be in a config file.

## Replacing the mock

When the login API lands, write a provider with the same shape:

```python
class ApiAuthProvider:
    def authenticate(self, email, password) -> User:
        ...  # POST to the login endpoint
        return User(email=..., name=..., role=..., token=access_token)
```

Then point `qrgen.auth.default_provider()` at it. Everything downstream already
carries `User.token`, so Hasura row-level permissions take over with no other
change. `User.token` is excluded from `repr()` so it cannot leak into a log or a
traceback.

Roles returned by that API must be `admin` or `support`; an unrecognised role is
refused at construction rather than silently downgraded.
