"""cli.py -- command-line entry point for the demo-database seed.

    python scripts/seed_demo_database.py [--base-url URL] [--username U] [--password P]
        [--demo-password P] [--wait-for-backend SECONDS] [--reset-demo] [--manifest PATH]

Env fallbacks (a CLI flag always wins): SMV_SEED_BASE_URL; SMV_SEED_USERNAME
falls back to SMV_BOOTSTRAP_ADMIN_USER then "admin"; SMV_SEED_PASSWORD falls
back to SMV_BOOTSTRAP_ADMIN_PASSWORD then "changeme123"; SMV_SEED_DEMO_PASSWORD.

Exit codes: 0 = fully OK (or nothing new to do). 1 = logged in fine but at
least one item failed (see the FAILED lines). 2 = could not even log in
as --username, or the backend never became healthy under --wait-for-backend.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

from .dataset import DEMO_USER_PASSWORD_DEFAULT
from .seed import seed


def _env_default(*names: str, fallback: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return fallback


def wait_for_backend(base_url: str, seconds: int) -> bool:
    if seconds <= 0:
        return True
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=5.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError as e:
            last_error = e
        time.sleep(2.0)
    print(f"backend at {base_url} did not become healthy within {seconds}s "
          f"(last error: {last_error})", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate a running SMV Tool instance with a realistic demo dataset "
                     "(5 users, a second allowance-policy version, 12 styles with a mix of "
                     "computed/uncomputed/edited/multi-generation results). Safe to re-run.",
    )
    parser.add_argument("--base-url", default=_env_default("SMV_SEED_BASE_URL", fallback="http://localhost:8000"))
    parser.add_argument("--username", default=_env_default(
        "SMV_SEED_USERNAME", "SMV_BOOTSTRAP_ADMIN_USER", fallback="admin"))
    parser.add_argument("--password", default=_env_default(
        "SMV_SEED_PASSWORD", "SMV_BOOTSTRAP_ADMIN_PASSWORD", fallback="changeme123"))
    parser.add_argument("--demo-password", default=_env_default(
        "SMV_SEED_DEMO_PASSWORD", fallback=DEMO_USER_PASSWORD_DEFAULT),
        help="shared password for the 5 demo users this seeds (non-production)")
    parser.add_argument("--wait-for-backend", type=int, default=0, metavar="SECONDS",
                         help="poll GET /health until it responds or this many seconds pass")
    parser.add_argument("--reset-demo", action="store_true",
                         help="delete every previously-seeded demo style first, then reseed fresh")
    parser.add_argument("--manifest", metavar="PATH",
                         help="write the created/skipped id manifest as JSON to this path")
    args = parser.parse_args()

    if args.wait_for_backend and not wait_for_backend(args.base_url, args.wait_for_backend):
        return 2

    client = httpx.Client(base_url=args.base_url, timeout=30.0)
    try:
        report = seed(
            client,
            admin_username=args.username, admin_password=args.password,
            demo_password=args.demo_password, reset_demo=args.reset_demo,
        )
    finally:
        client.close()

    if report.login_failed:
        status, detail = (report.failed[0][1], report.failed[0][2]) if report.failed else ("?", "")
        print(f"FAILED to log in as {args.username!r} against {args.base_url}: {status} {detail[:300]}",
              file=sys.stderr)
        return 2

    print(f"users: created={len(report.users_created)} skipped={len(report.users_skipped)} "
          f"disabled={len(report.users_disabled)}")
    print(f"policy v2: {report.policy_v2}")
    print(f"styles: created={len(report.styles_created)} skipped={len(report.styles_skipped)} "
          f"deleted={len(report.styles_deleted)}")
    print(f"computes: {len(report.computes)}  edits: {len(report.edits)}")
    for w in report.warnings:
        print(f"  WARNING: {w}")
    for context, status, detail in report.failed:
        print(f"  FAILED {context}: {status} {detail[:200]}")

    if args.manifest:
        with open(args.manifest, "w") as fh:
            json.dump(report.manifest, fh, indent=2)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
