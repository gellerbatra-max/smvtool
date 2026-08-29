"""Auth enforcement: role-based access control."""
from __future__ import annotations


def test_login_success_and_failure(client):
    r = client.post("/auth/login", data={"username": "admin", "password": "admin-test-pw-123"})
    assert r.status_code == 200
    assert r.json()["role"] == "administrator"

    r = client.post("/auth/login", data={"username": "admin", "password": "wrong-password"})
    assert r.status_code == 401


def test_unauthenticated_request_rejected(client):
    r = client.get("/styles")
    assert r.status_code == 401


def test_viewer_cannot_create_style(client, viewer_headers):
    r = client.post("/styles", json={"name": "Should Fail"}, headers=viewer_headers)
    assert r.status_code == 403


def test_viewer_cannot_add_operation(client, engineer_headers, viewer_headers):
    r = client.post("/styles", json={"name": "Viewer RO Test"}, headers=engineer_headers)
    sid = r.json()["id"]
    r = client.post(f"/styles/{sid}/operations", json={
        "name": "op", "steps": [{"kind": "handling", "element": "HAG", "params": {"distance_cm": 10}}],
    }, headers=viewer_headers)
    assert r.status_code == 403


def test_viewer_can_read(client, engineer_headers, viewer_headers):
    r = client.post("/styles", json={"name": "Viewer Read Test"}, headers=engineer_headers)
    sid = r.json()["id"]
    r = client.get(f"/styles/{sid}", headers=viewer_headers)
    assert r.status_code == 200
    r = client.get("/styles", headers=viewer_headers)
    assert r.status_code == 200


def test_viewer_cannot_compute(client, engineer_headers, viewer_headers):
    r = client.post("/styles", json={
        "name": "Viewer Compute Test", "seed_from_library": True,
    }, headers=engineer_headers)
    sid = r.json()["id"]
    r = client.post(f"/styles/{sid}/compute", json={}, headers=viewer_headers)
    assert r.status_code == 403


def test_engineer_cannot_manage_users(client, engineer_headers):
    r = client.post("/users", json={
        "username": "rogue", "full_name": "Rogue", "role": "viewer", "password": "pw12345",
    }, headers=engineer_headers)
    assert r.status_code == 403


def test_admin_can_manage_users(client, admin_headers):
    r = client.post("/users", json={
        "username": "newuser", "full_name": "New User", "role": "ie_engineer", "password": "pw12345",
    }, headers=admin_headers)
    assert r.status_code == 201
    r = client.get("/users", headers=admin_headers)
    assert r.status_code == 200
    assert any(u["username"] == "newuser" for u in r.json())


def test_engineer_cannot_create_allowance_policy_version(client, engineer_headers):
    r = client.post("/allowance-policies", json={
        "policy_name": "wt-allowance-policy", "document": {"spec": {"id": "x", "version": "9.9.9"},
                                                             "categories": [], "profiles": [],
                                                             "validation": {}},
    }, headers=engineer_headers)
    assert r.status_code == 403
