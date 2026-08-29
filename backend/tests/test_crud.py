"""CRUD correctness for styles and operations."""
from __future__ import annotations


def test_create_get_update_delete_style(client, engineer_headers):
    r = client.post("/styles", json={
        "name": "Basic Tee", "garment_type": "woven_shirt", "variant": "CLASSIC", "size": "M",
    }, headers=engineer_headers)
    assert r.status_code == 201, r.text
    style = r.json()
    sid = style["id"]
    assert style["name"] == "Basic Tee"
    assert style["operations"] == []

    r = client.get(f"/styles/{sid}", headers=engineer_headers)
    assert r.status_code == 200
    assert r.json()["id"] == sid

    r = client.get("/styles", headers=engineer_headers)
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())

    r = client.put(f"/styles/{sid}", json={"name": "Basic Tee v2", "size": "L"}, headers=engineer_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Basic Tee v2"
    assert r.json()["size"] == "L"

    r = client.delete(f"/styles/{sid}", headers=engineer_headers)
    assert r.status_code == 204

    r = client.get(f"/styles/{sid}", headers=engineer_headers)
    assert r.status_code == 404


def test_add_edit_delete_operation(client, engineer_headers):
    r = client.post("/styles", json={"name": "Pocket Tee"}, headers=engineer_headers)
    sid = r.json()["id"]

    op_payload = {
        "name": "Set pocket to front", "sequence": 0, "bundle_size": 20,
        "steps": [
            {"kind": "handling", "element": "HAG", "params": {"distance_cm": 30, "precision_class": "P1"}},
            {"kind": "seam", "machine_class": "SNLS-UBT", "path_length_mm": 260, "spi": 10,
             "curvature_class": "tight", "guidance_class": "seam_visible", "plies": 3, "pivots": 3},
            {"kind": "handling", "element": "HDS", "params": {"distance_cm": 20}},
        ],
    }
    r = client.post(f"/styles/{sid}/operations", json=op_payload, headers=engineer_headers)
    assert r.status_code == 201, r.text
    op = r.json()
    oid = op["id"]
    assert op["name"] == "Set pocket to front"
    assert len(op["steps"]) == 3

    op_payload["name"] = "Set pocket to front (revised)"
    r = client.put(f"/styles/{sid}/operations/{oid}", json=op_payload, headers=engineer_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Set pocket to front (revised)"

    r = client.delete(f"/styles/{sid}/operations/{oid}", headers=engineer_headers)
    assert r.status_code == 204

    r = client.get(f"/styles/{sid}", headers=engineer_headers)
    assert r.json()["operations"] == []


def test_seed_from_library(client, engineer_headers):
    r = client.post("/styles", json={
        "name": "Classic Shirt M", "variant": "CLASSIC", "size": "M", "seed_from_library": True,
    }, headers=engineer_headers)
    assert r.status_code == 201, r.text
    style = r.json()
    assert len(style["operations"]) > 20  # CLASSIC/M has 27 operations per the engine bulletin


def test_library_browse_and_bulletin(client, engineer_headers):
    r = client.get("/library", headers=engineer_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body["variants"]) == {"CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"}
    assert "M" in body["sizes"]

    r = client.get("/library/bulletin", params={"size": "M", "variant": "CLASSIC"}, headers=engineer_headers)
    assert r.status_code == 200
    assert r.json()["smv_min"] > 0
