"""Tests for scripts/seed_demo_styles.py's seed() -- the part of the script
that talks to the API and can be exercised against the isolated per-test
database the `client`/`admin_headers` fixtures already provide. The CLI's
own httpx.Client(base_url=...) construction in main() is not covered here
(it needs a real bound port, which is what this script is for in the first
place); seed() takes any object with .get()/.post() methods matching
httpx.Client's sync interface, and TestClient satisfies that.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import seed_demo_styles as sds  # noqa: E402


def test_seed_creates_one_style_per_variant_and_size(client, admin_headers):
    client.headers.update(admin_headers)

    report = sds.seed(client)

    assert report.ok, report.failed
    assert len(report.created) == len(sds.VARIANTS) * len(sds.SIZES)
    assert len(report.computed) == len(report.created)
    assert report.skipped_existing == []

    styles = client.get("/styles").json()
    assert len(styles) == len(sds.VARIANTS) * len(sds.SIZES)
    assert {s["name"] for s in styles} == {
        f"{v} {sz}" for v in sds.VARIANTS for sz in sds.SIZES
    }


def test_seeded_styles_have_real_computed_bulletins(client, admin_headers):
    client.headers.update(admin_headers)
    sds.seed(client)

    styles = client.get("/styles").json()
    classic_m = next(s for s in styles if s["name"] == "CLASSIC M")

    bulletin = client.get(f"/styles/{classic_m['id']}/bulletin").json()
    assert bulletin["smv_min"] > 0
    assert len(bulletin["operations"]) > 0
    # every seeded operation should have actually been computed, not left
    # with a null latest_result
    assert all(op["latest_result"] is not None for op in bulletin["operations"])


def test_seed_is_idempotent_by_name(client, admin_headers):
    client.headers.update(admin_headers)

    first = sds.seed(client)
    assert len(first.created) == len(sds.VARIANTS) * len(sds.SIZES)

    second = sds.seed(client)
    assert second.created == []
    assert len(second.skipped_existing) == len(sds.VARIANTS) * len(sds.SIZES)

    # re-running must not create duplicate rows
    styles = client.get("/styles").json()
    assert len(styles) == len(sds.VARIANTS) * len(sds.SIZES)


def test_seed_reports_failure_without_raising(client, admin_headers, engineer_headers):
    # A viewer (no write access) should get a clean 403-reported failure
    # per style, not an unhandled exception bubbling out of seed().
    r = client.post(
        "/users",
        json={
            "username": "viewer1",
            "full_name": "Viewer One",
            "role": "viewer",
            "password": "viewer-pw-123",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", data={"username": "viewer1", "password": "viewer-pw-123"})
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

    report = sds.seed(client)

    assert not report.ok
    assert report.created == []
    assert len(report.failed) == len(sds.VARIANTS) * len(sds.SIZES)
    assert all(status == 403 for _, status, _ in report.failed)
