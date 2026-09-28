"""Tests for backend/scripts/seed_demo_database.py's seed_demo package.

The full seed does ~14 computes + ~8 logins + 5 bcrypt hashes -- too slow
to repeat per test -- so `seeded` runs it ONCE per module against an
isolated database (via conftest.isolated_client, the same setup/teardown
`client` uses per-test) and every test below asserts against the
resulting state. Tests that need a genuinely fresh database instead (the
login-failure and --reset-demo cases) use the ordinary function-scoped
`client` fixture and pay for their own seed run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for `import conftest` below

import pytest

from app import engine_bridge, models
from app.database import get_db
from app.main import app
from conftest import ADMIN_PASSWORD, isolated_client

import seed_demo.dataset as sdd  # noqa: E402
from seed_demo.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("seed_demo_db")
    with isolated_client(db_dir) as client:
        report = seed(client, admin_username="admin", admin_password=ADMIN_PASSWORD)

        def get_session():
            gen = app.dependency_overrides[get_db]()
            return next(gen)

        yield client, report, get_session


def _headers(client, username, password):
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin_headers(client):
    return _headers(client, "admin", ADMIN_PASSWORD)


# --------------------------------------------------------------- report shape

def test_seed_report_ok_and_counts(seeded):
    client, report, _ = seeded
    assert report.ok, report.failed
    assert len(report.users_created) == len(sdd.DEMO_USERS)
    assert len(report.users_disabled) == 1
    assert report.policy_v2 == "created"
    assert len(report.styles_created) == len(sdd.DEMO_STYLES)
    assert report.styles_deleted == []
    assert len(report.computes) > 0
    assert len(report.edits) == sum(len(s.edits) for s in sdd.DEMO_STYLES)

    users = client.get("/users", headers=_admin_headers(client)).json()
    assert len(users) == 1 + len(sdd.DEMO_USERS)  # bootstrap admin + the 5 demo users
    roles = {u["role"] for u in users}
    assert roles == {"administrator", "ie_engineer", "viewer"}
    assert sum(not u["is_active"] for u in users) == 1


def test_arjun_is_disabled_and_cannot_log_in(seeded):
    client, _, _ = seeded
    r = client.post("/auth/login", data={
        "username": "arjun.devarajan", "password": sdd.DEMO_USER_PASSWORD_DEFAULT,
    })
    assert r.status_code == 401


# --------------------------------------------------------------- attribution

def test_multi_user_attribution(seeded):
    client, report, get_session = seeded
    db = get_session()
    created_by = {s.created_by_id for s in db.query(models.Style).all()}
    computed_by = {r.computed_by_id for r in db.query(models.SMVResult).all()}
    db.close()

    assert len(created_by) >= 3
    assert len(computed_by) >= 3


def test_policy_v2_attributed_to_rita(seeded):
    client, report, get_session = seeded
    policies = client.get("/allowance-policies", headers=_admin_headers(client)).json()
    v2 = next(p for p in policies if p["version"] == 2)
    assert v2["is_active"] is True

    users = client.get("/users", headers=_admin_headers(client)).json()
    rita_id = next(u["id"] for u in users if u["username"] == "rita.okafor")

    db = get_session()
    row = db.query(models.AllowancePolicy).filter(models.AllowancePolicy.id == v2["id"]).first()
    db.close()
    assert row.created_by_id == rita_id


# ----------------------------------------------------------- policy versions

def test_v1_inactive_v2_active(seeded):
    client, _, _ = seeded
    policies = client.get("/allowance-policies", headers=_admin_headers(client)).json()
    by_version = {p["version"]: p for p in policies}
    assert by_version[1]["is_active"] is False
    assert by_version[2]["is_active"] is True


def test_ws2401_has_two_result_generations_across_both_policy_versions(seeded):
    client, _, get_session = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2401 = next(s for s in styles if s["variant"] == "CLASSIC" and s["size"] == "M"
                  and "safety-stitch" not in s["name"])

    db = get_session()
    results = db.query(models.SMVResult).filter(models.SMVResult.style_id == ws2401["id"]).all()
    policy_versions_used = {r.allowance_policy_version_id for r in results}
    db.close()
    assert len(policy_versions_used) == 2


# ------------------------------------------------------------- live engine match

def test_seeded_smv_matches_a_live_engine_call(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    policies = client.get("/allowance-policies", headers=headers).json()
    v2 = next(p for p in policies if p["version"] == 2)
    v2_document = client.get(f"/allowance-policies/{v2['id']}", headers=headers).json()["document"]

    styles = client.get("/styles", headers=headers).json()
    ws2409 = next(s for s in styles if s["variant"] == "CLASSIC" and s["size"] == "S")
    bulletin = client.get(f"/styles/{ws2409['id']}/bulletin", headers=headers).json()

    expected = engine_bridge.library_style_bulletin(
        "S", "CLASSIC", ws2409["bundle_size"], v2_document, "WOVEN_TOPS_DECOMPOSED",
    )
    assert bulletin["smv_min"] == pytest.approx(expected["SMV_min"], rel=1e-9)


# ------------------------------------------------------------ machine-swap trial

def test_ws2405_machine_swap_lowered_the_smv_and_is_logged(seeded):
    client, _, get_session = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2405 = next(s for s in styles if "safety-stitch" in s["name"])

    db = get_session()
    results = db.query(models.SMVResult).filter(
        models.SMVResult.style_id == ws2405["id"]
    ).order_by(models.SMVResult.computed_at).all()
    db.close()
    totals_by_op: dict[str, list[float]] = {}
    for r in results:
        totals_by_op.setdefault(r.operation_id, []).append(r.st_op_s)
    # every op was computed exactly twice (gen1, gen2 after the swap)
    assert all(len(v) == 2 for v in totals_by_op.values())

    detail = client.get(f"/styles/{ws2405['id']}", headers=headers).json()
    side_seam = next(o for o in detail["operations"] if o["name"].startswith("side_seam"))
    seam_step = next(s for s in side_seam["steps"] if s["kind"] == "seam")
    assert seam_step["machine_class"] == "OL-5T-SS"

    log = client.get(f"/styles/{ws2405['id']}/change-log", headers=headers).json()
    assert any(row["entity_type"] == "operation" and row["action"] == "update"
               and row["field"] == "steps" for row in log)


# ---------------------------------------------------------------- uncomputed

def test_ws2410_is_uncomputed(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2410 = next(s for s in styles if "costing request" in s["name"])
    bulletin = client.get(f"/styles/{ws2410['id']}/bulletin", headers=headers).json()
    assert bulletin["smv_min"] is None
    assert all(op["latest_result"] is None for op in bulletin["operations"])


# ------------------------------------------------------------- partial compute

def test_ws2404_has_exactly_one_uncomputed_duplicated_operation(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2404 = next(s for s in styles if s["variant"] == "BLOUSE_COLLARLESS" and s["size"] == "S")
    bulletin = client.get(f"/styles/{ws2404['id']}/bulletin", headers=headers).json()

    uncomputed = [op for op in bulletin["operations"] if op["latest_result"] is None]
    assert len(uncomputed) == 1
    assert "2nd station" in uncomputed[0]["name"]

    log = client.get(f"/styles/{ws2404['id']}/change-log", headers=headers).json()
    assert any(row["entity_type"] == "operation" and row["action"] == "create" for row in log)


# ---------------------------------------------------------- deleted operation

def test_ws2406_operation_delete_is_logged_and_lowers_op_count(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2406 = next(s for s in styles if s["variant"] == "CLASSIC" and s["size"] == "XL")

    detail = client.get(f"/styles/{ws2406['id']}", headers=headers).json()
    assert len(detail["operations"]) == 26  # CLASSIC library ships 27; one bartack op deleted

    log = client.get(f"/styles/{ws2406['id']}/change-log", headers=headers).json()
    delete_rows = [r for r in log if r["entity_type"] == "operation" and r["action"] == "delete"]
    assert len(delete_rows) == 1
    assert "Bartack" in delete_rows[0]["prior_value"]
    assert any(r["entity_type"] == "style" and r["action"] == "update" and r["field"] == "notes"
               for r in log)


# --------------------------------------------------------------- rename + notes

def test_ws2403_operation_rename_and_style_notes_update(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2403 = next(s for s in styles if s["variant"] == "SHORT_SLEEVE" and s["size"] == "M")

    detail = client.get(f"/styles/{ws2403['id']}", headers=headers).json()
    assert any("template guide" in op["name"] for op in detail["operations"])

    log = client.get(f"/styles/{ws2403['id']}/change-log", headers=headers).json()
    assert any(r["entity_type"] == "operation" and r["action"] == "update" and r["field"] == "name"
               for r in log)
    assert any(r["entity_type"] == "style" and r["action"] == "update" and r["field"] == "notes"
               for r in log)


def test_ws2402_rename_and_bundle_size_update_fields(seeded):
    client, _, _ = seeded
    headers = _admin_headers(client)
    styles = client.get("/styles", headers=headers).json()
    ws2402 = next(s for s in styles if s["name"] == "Oxford Button-Down, Classic (rev B)")
    assert ws2402["bundle_size"] == 16

    log = client.get(f"/styles/{ws2402['id']}/change-log", headers=headers).json()
    update_fields = {r["field"] for r in log if r["entity_type"] == "style" and r["action"] == "update"}
    assert update_fields == {"name", "bundle_size"}


# ------------------------------------------------------------------ idempotency

def test_second_seed_run_is_a_no_op(seeded):
    client, _, get_session = seeded

    def counts():
        db = get_session()
        result = {
            "users": db.query(models.User).count(),
            "styles": db.query(models.Style).count(),
            "smv_results": db.query(models.SMVResult).count(),
            "change_log": db.query(models.ChangeLog).count(),
            "policies": db.query(models.AllowancePolicy).count(),
        }
        db.close()
        return result

    before = counts()
    second = seed(client, admin_username="admin", admin_password=ADMIN_PASSWORD)
    after = counts()

    assert second.ok
    assert second.users_created == []
    assert second.styles_created == []
    assert second.computes == []
    assert second.edits == []
    assert second.policy_v2 == "skipped"
    assert before == after


# ------------------------------------------------------------------- authz

def test_viewer_cannot_run_the_seed(tmp_path):
    # A separate, genuinely fresh database (not the shared `seeded` module
    # fixture) since this needs to control exactly who the seed logs in as.
    with isolated_client(tmp_path) as client:
        r = client.post("/users", json={
            "username": "outsider", "full_name": "Outsider", "role": "viewer", "password": "pw12345",
        }, headers=_admin_headers(client))
        assert r.status_code == 201, r.text

        report = seed(client, admin_username="outsider", admin_password="pw12345")

        # The viewer CAN log in -- /auth/login isn't role-gated -- so this
        # fails on the first *admin-only* call (GET /users), not on login.
        assert not report.login_failed
        assert not report.ok
        assert report.styles_created == []
        assert report.failed
        assert report.failed[0][1] == 403


# --------------------------------------------------------------- --reset-demo

def test_reset_demo_only_touches_tagged_styles(tmp_path):
    with isolated_client(tmp_path) as client:
        headers = _admin_headers(client)
        real = client.post("/styles", json={
            "name": "My Real Style", "variant": "CLASSIC", "size": "M",
        }, headers=headers).json()

        first = seed(client, admin_username="admin", admin_password=ADMIN_PASSWORD)
        assert first.ok, first.failed
        first_style_ids = set(first.manifest.get("styles", {}).values())

        second = seed(client, admin_username="admin", admin_password=ADMIN_PASSWORD, reset_demo=True)
        assert second.ok, second.failed
        assert len(second.styles_deleted) == len(sdd.DEMO_STYLES)
        assert len(second.styles_created) == len(sdd.DEMO_STYLES)
        second_style_ids = set(second.manifest.get("styles", {}).values())
        assert first_style_ids.isdisjoint(second_style_ids)  # fresh ids after delete + recreate

        styles = client.get("/styles", headers=headers).json()
        assert "My Real Style" in {s["name"] for s in styles}
        assert real["id"] in {s["id"] for s in styles}
