"""seed_demo_styles.py -- populate demo Style records against a running
SMV backend instance.

The backend's `styles` table starts empty; every Style is created through
the app (login -> Styles -> New style). This script exercises the exact
same API a human would (POST /styles with seed_from_library=true, then
POST /styles/{id}/compute) to create one style per (variant, size)
combination from the seeded shirt_library.py catalog -- 3 variants x 5
sizes = 15 styles -- so the Styles List / Bulletin / Analytics screens have
realistic data to browse instead of an empty table.

Idempotent by name: re-running skips any variant/size combo whose exact
name already exists, so it's safe to run again after adding real styles
of your own (as long as you don't name them "CLASSIC S" etc.).

Usage (against a locally running backend, e.g. `uvicorn app.main:app` or
the Docker Compose stack):

    python backend/scripts/seed_demo_styles.py --base-url http://localhost:8000

Requires an administrator or ie_engineer account -- defaults to the
bootstrap admin credentials the backend seeds on first startup
(SMV_BOOTSTRAP_ADMIN_USER / SMV_BOOTSTRAP_ADMIN_PASSWORD env vars, or
admin/changeme123). Pass --username/--password for a different account.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import httpx

VARIANTS = ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"]
SIZES = ["S", "M", "L", "XL", "XXL"]

# Bundle size varies by size the way a real cutting/bundling plan would --
# smaller garments bundle more pieces per unit of handling time, not a
# fixed 20 across the board.
BUNDLE_SIZE_BY_SIZE = {"S": 24, "M": 20, "L": 20, "XL": 18, "XXL": 15}


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    computed: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    failed: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def seed(client: httpx.Client) -> SeedReport:
    """Runs the seed against an authenticated httpx.Client whose base_url
    (or ASGI transport, in tests) already points at the target backend."""
    report = SeedReport()
    existing_names = {s["name"] for s in client.get("/styles").json()}

    for variant in VARIANTS:
        for size in SIZES:
            name = f"{variant} {size}"
            if name in existing_names:
                report.skipped_existing.append(name)
                continue

            payload = {
                "name": name,
                "garment_type": "woven_shirt",
                "variant": variant,
                "size": size,
                "bundle_size": BUNDLE_SIZE_BY_SIZE[size],
                "seed_from_library": True,
            }
            create_resp = client.post("/styles", json=payload)
            if create_resp.status_code != 201:
                report.failed.append((name, create_resp.status_code, create_resp.text))
                continue
            report.created.append(name)

            style_id = create_resp.json()["id"]
            compute_resp = client.post(f"/styles/{style_id}/compute", json={})
            if compute_resp.status_code == 200:
                report.computed.append(name)
            else:
                report.failed.append((name, compute_resp.status_code, compute_resp.text))

    return report


def _authenticated_client(base_url: str, username: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=base_url, timeout=30.0)
    # /auth/login takes OAuth2PasswordRequestForm -- form-encoded, not JSON.
    login_resp = client.post("/auth/login", data={"username": username, "password": password})
    if login_resp.status_code != 200:
        raise SystemExit(
            f"login failed for {username!r} against {base_url}: "
            f"{login_resp.status_code} {login_resp.text}"
        )
    token = login_resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="changeme123")
    args = parser.parse_args()

    client = _authenticated_client(args.base_url, args.username, args.password)
    report = seed(client)

    print(
        f"created={len(report.created)} computed={len(report.computed)} "
        f"skipped(existing)={len(report.skipped_existing)} failed={len(report.failed)}"
    )
    for name, status, text in report.failed:
        print(f"  FAILED {name}: {status} {text[:200]}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
