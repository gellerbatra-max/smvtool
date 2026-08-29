"""Regression: SMVs computed via the API must match calling the engine
directly, for every size/variant combination in the seeded shirt library,
and for the module's own worked example fixture."""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smv_engine"))

import handling_time as ht
import machine_time as mt
import allowance as al
import smv_assembly as sa
import shirt_library as sl

from app import engine_bridge

_ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "smv_engine"))


def _direct_style_smv(size, variant, bundle_size=20):
    tax = ht.load_taxonomy(os.path.join(_ENGINE_DIR, "element_taxonomy.json"))
    mcat = mt.load_machine_catalog(os.path.join(_ENGINE_DIR, "machine_classes.csv"))
    pol = al.load_allowance_policy(os.path.join(_ENGINE_DIR, "allowance_policy.json"))
    seam_geom = engine_bridge.get_seam_geometry()
    ops = sl.build_style_operations(seam_geom, size, variant, bundle_size)
    return sa.assemble_style(tax, mcat, pol, ops, allowance_profile="WOVEN_TOPS_DECOMPOSED")


def test_api_seeded_compute_matches_direct_engine_call(client, engineer_headers):
    for size in ["S", "M", "L", "XL", "XXL"]:
        for variant in ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"]:
            r = client.post("/styles", json={
                "name": f"{variant} {size}", "variant": variant, "size": size,
                "seed_from_library": True,
            }, headers=engineer_headers)
            assert r.status_code == 201, r.text
            sid = r.json()["id"]

            r = client.post(f"/styles/{sid}/compute", json={}, headers=engineer_headers)
            assert r.status_code == 200, r.text
            api_smv = r.json()["smv_min"]

            direct = _direct_style_smv(size, variant)
            assert math.isclose(api_smv, direct["SMV_min"], rel_tol=1e-9), (
                f"{variant}/{size}: API={api_smv} direct={direct['SMV_min']}"
            )


def test_worked_example_armhole_seam_matches_direct_engine_and_report():
    """Regression-tests engine_bridge.compute_operation() against the
    engine's own worked_example.py fixture (armhole seam, size M) both by
    (a) reproducing worked_example.build_worked_example()'s exact operation
    through the bridge and checking the numbers match bit-for-bit, and
    (b) checking those numbers match the headline figures the handoff
    report/README quote: 76.75s = 1.279 min = 2131.9 TMU."""
    import worked_example as we

    # worked_example.build_worked_example() opens its JSON/CSV fixtures by a
    # bare relative filename (it's designed to be run with cwd=smv_engine/,
    # per README_HANDOFF.md's own run instructions) -- chdir there for the
    # duration of this call only.
    cwd = os.getcwd()
    os.chdir(_ENGINE_DIR)
    try:
        _, _, _, _, _, op, direct_result = we.build_worked_example()
    finally:
        os.chdir(cwd)

    bridge_result = engine_bridge.compute_operation(
        op.name, op.steps, op.bundle_size,
        engine_bridge.get_default_allowance_policy_document(), "WOVEN_TOPS_DECOMPOSED",
    )

    assert math.isclose(bridge_result["ST_op_s"], direct_result["ST_op_s"], rel_tol=1e-9)
    assert math.isclose(bridge_result["BT_op_s"], direct_result["BT_op_s"], rel_tol=1e-9)

    # Headline figures quoted in README_HANDOFF.md / engine_phase1_report.md
    assert math.isclose(direct_result["ST_op_s"], 76.75, abs_tol=0.05)
    assert math.isclose(direct_result["ST_op_min"], 1.279, abs_tol=0.001)
    assert math.isclose(direct_result["ST_op_min"] * sa.TMU_PER_MINUTE, 2131.9, abs_tol=1.0)


def test_api_compute_matches_worked_example_via_single_operation_style(client, engineer_headers):
    """End-to-end: post the worked-example operation through the REST API
    (create style -> add operation -> compute) and confirm the persisted
    smv_results row matches the direct engine call exactly."""
    import worked_example as we

    cwd = os.getcwd()
    os.chdir(_ENGINE_DIR)
    try:
        _, _, _, _, _, op, direct_result = we.build_worked_example()
    finally:
        os.chdir(cwd)

    r = client.post("/styles", json={"name": "Worked Example Style"}, headers=engineer_headers)
    sid = r.json()["id"]
    r = client.post(f"/styles/{sid}/operations", json={
        "name": op.name, "sequence": 0, "bundle_size": op.bundle_size, "steps": op.steps,
    }, headers=engineer_headers)
    assert r.status_code == 201, r.text

    r = client.post(f"/styles/{sid}/compute", json={}, headers=engineer_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert math.isclose(body["results"][0]["st_op_s"], direct_result["ST_op_s"], rel_tol=1e-9)
