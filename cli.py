#!/usr/bin/env python3
"""Development harness for the generation engine.

Runs the whole pipeline without the desktop UI, which is what you want when
debugging a 50,000-row job:

    python cli.py profiles
    python cli.py validate -p extraa_cards -i Brigade.csv
    python cli.py sample   -p extraa_cards -i Brigade.csv -o sample.png
    python cli.py generate -p extraa_cards -i Brigade.csv -o cards.zip

Not part of the support workflow. The desktop app calls the same engine.
"""

import argparse
import getpass
import multiprocessing
import os
import sys

from qrgen import auth, engine, profiles, rows
from qrgen.store import ProfileStore
from qrgen.store.hasura import StoreError


def _bar(done, total, width=28):
    filled = 0 if not total else int(width * done / total)
    return "█" * filled + "░" * (width - filled)


def _progress(done, total, successful, failed):
    sys.stdout.write(
        f"\r  {_bar(done, total)}  {done:,} / {total:,}"
        f"   ok {successful:,}   failed {failed:,} ")
    sys.stdout.flush()


def cmd_login(args):
    """Check a mock login and show what that account may do."""
    password = args.password or getpass.getpass("Password: ")
    provider = auth.default_provider()
    user = provider.authenticate(args.email, password)
    print(f"Provider:    {type(provider).__name__}")
    print(f"Signed in:   {user.name} <{user.email}>")
    print(f"Role:        {user.role}")
    print(f"Permissions: {', '.join(sorted(user.permissions))}")
    store = ProfileStore(user=user)
    found = store.list()
    print(f"Profiles:    {len(found)} visible - {store.status}")
    print(f"Can edit:    {'yes' if store.writable else 'no - no admin credentials configured'}"
          if user.can("profile.edit") else "Can edit:    no - not permitted by role")
    return 0


def cmd_store(args):
    """Diagnose the connection to the shared profile store."""
    from qrgen import config as app_config
    from qrgen.store.hasura import TABLE, HasuraStore

    settings = app_config.load()
    url = settings.get("api_url")
    print(f"URL         {url or '(not configured — set EXTRAA_QR_API_URL)'}")
    print(f"Table       {TABLE}")
    creds = [name for name in ("token", "admin_secret") if settings.get(name)]
    print(f"Credential  {', '.join(creds) if creds else 'none'}")
    if not url:
        return 1

    for label, secret, token in (
            ("as a support user", None, settings.get("token")),
            ("as an admin", settings.get("admin_secret"), None)):
        if label.endswith("admin") and not settings.get("admin_secret"):
            print(f"\n{label}: skipped, no admin secret configured")
            continue
        remote = HasuraStore(url, admin_secret=secret, token=token)
        try:
            rows = remote.list()
        except StoreError as exc:
            print(f"\n{label}: FAILED\n  {exc}")
            if "not found in type" in str(exc):
                print(f"  The {TABLE} table is not visible to the role this "
                      f"request resolved to.\n"
                      f"  Hasura only honours x-hasura-role on an authenticated "
                      f"request, so an\n  unauthenticated call falls back to "
                      f"HASURA_GRAPHQL_UNAUTHORIZED_ROLE.")
            continue
        print(f"\n{label}: OK — {len(rows)} profile(s)")
        for row in rows:
            print(f"  {row['id']:<16} {row['name']:<20} v{row['version']}  "
                  f"{'active' if row['active'] else 'inactive'}  "
                  f"{row.get('name_font')} {row.get('name_size')}/"
                  f"{row.get('code_size')}")
    return 0


def _store(args):
    """Local mode skips the shared store -- useful when debugging offline."""
    if args.local:
        return None
    return ProfileStore()


def _profile(args):
    store = _store(args)
    if store is None:
        return profiles.get(args.profile)
    profile = store.get(args.profile)
    if store.source != "live":
        print(f"note: {store.status}", file=sys.stderr)
    return profile


def cmd_profiles(args):
    store = _store(args)
    if store is None:
        found = sorted(profiles.load_builtin().values(), key=lambda p: p.name)
        print("source: bundled profiles (--local)")
    else:
        found = store.list(include_inactive=True)
        print(f"source: {store.status}"
              f"{'  [admin credentials present]' if store.writable else ''}")
    for profile in found:
        state = "active" if profile.active else "inactive"
        print(f"{profile.id:<16} {profile.name:<20} {state:<9} "
              f"v{profile.version}  renderer={profile.renderer}")
        print(f"{'':<16} columns: {', '.join(profile.required_columns)}")
        print(f"{'':<16} qr:      {profile.qr_content}")
        print(f"{'':<16} file:    {profile.filename}")
    return 0


def cmd_validate(args):
    profile = _profile(args)
    report = engine.validate_input(profile, args.input)
    print(f"{os.path.basename(args.input)}: {report.summary}")
    for error in report.errors[:args.max_errors]:
        print(f"  row {error.row_number}: {error.error}")
    if len(report.errors) > args.max_errors:
        print(f"  ... and {len(report.errors) - args.max_errors} more")
    return 0 if report.ok else 1


def cmd_sample(args):
    profile = _profile(args)
    sample = engine.render_sample(profile, engine.first_row(args.input))
    print(f"Profile:      {profile.name}")
    print(f"Name:         {sample.fields['top_text']}")
    print(f"QR Code:      {sample.fields['bottom_text']}")
    print(f"Expected URL: {sample.fields['qr_content']}")
    print(f"Filename:     {sample.fields['filename']}")
    with open(args.out, "wb") as fh:
        fh.write(sample.image)
    print(f"Written:      {args.out} ({len(sample.image):,} bytes)")
    return 0


def cmd_generate(args):
    profile = _profile(args)

    report = engine.validate_input(profile, args.input)
    print(f"Validation: {report.summary}")
    if not report.ok:
        for error in report.errors[:args.max_errors]:
            print(f"  row {error.row_number}: {error.error}")
        print("Refusing to start: fix the input first.")
        return 1

    samples = engine.render_samples(profile, args.input)
    sample = samples[0]
    print("\nSamples")
    for item in samples:
        print(f"  row {item.row_number:>6}  {item.fields['bottom_text']:<12} "
              f"{item.fields['qr_content']}")

    if not args.yes:
        preview = os.path.join(os.path.dirname(os.path.abspath(args.out)),
                               "sample_preview.png")
        with open(preview, "wb") as fh:
            fh.write(sample.image)
        print(f"  Preview:      {preview}")
        answer = input("\nApprove & Generate? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 1

    print()
    result = engine.generate_batch(profile, args.input, args.out,
                                   on_progress=_progress,
                                   workers=args.workers)
    print(f"\n\n{result.summary}")
    if result.zip_path:
        size = os.path.getsize(result.zip_path)
        print(f"ZIP:          {result.zip_path} ({size / 1e6:.1f} MB)")
    if result.error_report:
        print(f"Errors:       {result.error_report}")
        for failure in result.failures[:args.max_errors]:
            print(f"  row {failure.row_number}: {failure.error}")
    return 0 if not result.failures else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p, needs_input=True):
        p.add_argument("-p", "--profile", required=True, help="profile id")
        if needs_input:
            p.add_argument("-i", "--input", required=True, help="CSV or JSON file")
        p.add_argument("--max-errors", type=int, default=20,
                       help="how many errors to print (default 20)")
        p.add_argument("--local", action="store_true",
                       help="use the bundled profiles, never the shared store")

    p = sub.add_parser("profiles", help="list available profiles")
    p.add_argument("--local", action="store_true",
                   help="use the bundled profiles, never the shared store")
    p.set_defaults(func=cmd_profiles, max_errors=20)

    p = sub.add_parser("store", help="diagnose the shared profile store")
    p.set_defaults(func=cmd_store, max_errors=20, local=False)

    p = sub.add_parser("login", help="verify a mock login and show its role")
    p.add_argument("-u", "--email", required=True,
                   metavar="EMAIL_OR_USERNAME")
    p.add_argument("--password", help="prompted for if omitted")
    p.set_defaults(func=cmd_login, max_errors=20, local=False)

    p = sub.add_parser("validate", help="check an input file, generate nothing")
    add_common(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("sample", help="render the first row only")
    add_common(p)
    p.add_argument("-o", "--out", default="sample.png")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("generate", help="validate, sample, approve, then batch")
    add_common(p)
    p.add_argument("-o", "--out", required=True, help="destination ZIP")
    p.add_argument("-y", "--yes", action="store_true",
                   help="skip the approval prompt (scripted runs only)")
    p.add_argument("-w", "--workers", type=int, default=None, metavar="N",
                   help=f"worker processes (default {engine.default_workers()}; "
                        f"1 runs in-process, which is what you want under a "
                        f"debugger)")
    p.set_defaults(func=cmd_generate)

    args = parser.parse_args(argv)
    engine.sweep_stale()
    try:
        return args.func(args)
    except (profiles.ProfileError, rows.InputError, StoreError,
            auth.AuthError, auth.PermissionDenied) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    # Required before any pool is created when frozen by PyInstaller: the
    # spawned children re-run this executable, and without this they would
    # re-run the CLI instead of starting as workers.
    multiprocessing.freeze_support()
    sys.exit(main())
