"""PATCH /users/{id} and GET /allowance-policies/{id} -- two small additive
endpoints added so the demo-database seed script (backend/scripts/seed_demo_database.py)
can be entirely API-driven: it needs to disable a demo user and to read an
existing policy's document to derive a v2 from it. See backend/README.md's
"Demo data" section."""
from __future__ import annotations


def _create_user(client, headers, username="dana", role="viewer"):
    r = client.post("/users", json={
        "username": username, "full_name": "Dana Demo", "role": role, "password": "pw12345",
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------- PATCH /users/{id}

def test_admin_can_patch_full_name_and_role(client, admin_headers):
    user_id = _create_user(client, admin_headers, role="viewer")

    r = client.patch(f"/users/{user_id}", json={
        "full_name": "Dana Updated", "role": "ie_engineer",
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Dana Updated"
    assert body["role"] == "ie_engineer"

    r = client.get("/users", headers=admin_headers)
    updated = next(u for u in r.json() if u["id"] == user_id)
    assert updated["full_name"] == "Dana Updated"
    assert updated["role"] == "ie_engineer"


def test_patch_deactivating_a_user_then_blocks_their_login(client, admin_headers):
    user_id = _create_user(client, admin_headers, username="offboarded")

    login = client.post("/auth/login", data={"username": "offboarded", "password": "pw12345"})
    assert login.status_code == 200

    r = client.patch(f"/users/{user_id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    login = client.post("/auth/login", data={"username": "offboarded", "password": "pw12345"})
    assert login.status_code == 401


def test_patch_can_update_multiple_fields_at_once(client, admin_headers):
    # change_log itself is exercised directly via audit.diff_and_log in
    # test_audit.py; there's no GET endpoint scoped to a user's own history
    # to assert against here (change_log rows for entity_type="user" have
    # style_id=None, and the only change-log route filters by style_id).
    user_id = _create_user(client, admin_headers)

    r = client.patch(f"/users/{user_id}", json={
        "full_name": "Dana Renamed", "is_active": False,
    }, headers=admin_headers)
    assert r.status_code == 200

    r = client.get("/users", headers=admin_headers)
    updated = next(u for u in r.json() if u["id"] == user_id)
    assert updated["full_name"] == "Dana Renamed"
    assert updated["is_active"] is False


def test_patch_noop_update_is_a_valid_no_op(client, admin_headers):
    user_id = _create_user(client, admin_headers)
    r = client.patch(f"/users/{user_id}", json={}, headers=admin_headers)
    assert r.status_code == 200


def test_admin_cannot_deactivate_their_own_account(client, admin_headers):
    r = client.get("/auth/me", headers=admin_headers)
    self_id = r.json()["id"]
    r = client.patch(f"/users/{self_id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 400


def test_patch_rejects_invalid_role(client, admin_headers):
    user_id = _create_user(client, admin_headers)
    r = client.patch(f"/users/{user_id}", json={"role": "superuser"}, headers=admin_headers)
    assert r.status_code == 400


def test_patch_unknown_user_404s(client, admin_headers):
    r = client.patch("/users/does-not-exist", json={"full_name": "x"}, headers=admin_headers)
    assert r.status_code == 404


def test_engineer_cannot_patch_users(client, admin_headers, engineer_headers):
    user_id = _create_user(client, admin_headers)
    r = client.patch(f"/users/{user_id}", json={"full_name": "x"}, headers=engineer_headers)
    assert r.status_code == 403


# --------------------------------------------------- GET /allowance-policies/{id}

def test_get_allowance_policy_by_id_returns_the_document(client, engineer_headers):
    policies = client.get("/allowance-policies", headers=engineer_headers).json()
    v1 = next(p for p in policies if p["policy_name"] == "wt-allowance-policy")

    r = client.get(f"/allowance-policies/{v1['id']}", headers=engineer_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == v1["id"]
    assert body["version"] == v1["version"]
    assert "document" in body
    assert body["document"]["spec"]["id"] == "wt-allowance-policy"
    # the list endpoint deliberately omits the document
    assert "document" not in v1


def test_get_allowance_policy_by_id_404_for_unknown(client, engineer_headers):
    r = client.get("/allowance-policies/does-not-exist", headers=engineer_headers)
    assert r.status_code == 404


def test_viewer_can_read_a_policy_document(client, viewer_headers, engineer_headers):
    policies = client.get("/allowance-policies", headers=engineer_headers).json()
    v1 = next(p for p in policies if p["policy_name"] == "wt-allowance-policy")
    r = client.get(f"/allowance-policies/{v1['id']}", headers=viewer_headers)
    assert r.status_code == 200


# ------------------------------------------- allowance_policy_version_id exposure

def test_compute_and_bulletin_expose_allowance_policy_version_id(client, engineer_headers):
    active = client.get("/allowance-policies/active", headers=engineer_headers).json()

    r = client.post("/styles", json={
        "name": "Policy Version Exposure Test", "variant": "CLASSIC", "size": "M",
        "seed_from_library": True,
    }, headers=engineer_headers)
    style_id = r.json()["id"]

    compute = client.post(f"/styles/{style_id}/compute", json={}, headers=engineer_headers)
    assert compute.status_code == 200, compute.text
    results = compute.json()["results"]
    assert results
    assert all(row["allowance_policy_version_id"] == active["id"] for row in results)

    bulletin = client.get(f"/styles/{style_id}/bulletin", headers=engineer_headers).json()
    computed_ops = [op for op in bulletin["operations"] if op["latest_result"]]
    assert computed_ops
    assert all(
        op["latest_result"]["allowance_policy_version_id"] == active["id"] for op in computed_ops
    )
