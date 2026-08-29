"""
engine_bridge.py -- the ONLY module in this application that imports the SMV
calculation engine. Every route handler that needs a computed SMV goes
through the functions here, never touches handling_time/machine_time/
allowance/smv_assembly/shirt_library directly, and NEVER hardcodes a timing
constant, lookup table, or SMV number -- everything numeric returned by this
module is the live output of the vendored engine (backend/smv_engine/,
copied byte-for-byte from the handoff bundle; see smv_engine/README_HANDOFF.md).

Taxonomy / machine catalog are loaded once from the vendored engine's own
shipped JSON/CSV (element_taxonomy.json, machine_classes.csv) -- these are
the engine's physical-model definitions, not factory-editable policy, so
they are not versioned in the database the way allowance policy is.
Allowance policy IS factory-editable and IS versioned (see models.AllowancePolicy);
callers pass a policy *document* (dict) loaded from the DB, and we build an
al.AllowancePolicy directly from that dict so a computed SMV is always tied
to the exact policy version that was active when it was computed.
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache

_ENGINE_DIR = os.path.join(os.path.dirname(__file__), "..", "smv_engine")
_ENGINE_DIR = os.path.abspath(_ENGINE_DIR)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

import handling_time as ht          # noqa: E402
import machine_time as mt           # noqa: E402
import allowance as al              # noqa: E402
import smv_assembly as sa           # noqa: E402
import shirt_library as sl          # noqa: E402
import calibration_fit as cf        # noqa: E402

ENGINE_VERSION = "smv_engine_bundle@handoff_v2"  # stamped onto every smv_results row


@lru_cache(maxsize=1)
def get_taxonomy() -> "ht.Taxonomy":
    return ht.load_taxonomy(os.path.join(_ENGINE_DIR, "element_taxonomy.json"))


@lru_cache(maxsize=1)
def get_machine_catalog() -> "mt.MachineCatalog":
    return mt.load_machine_catalog(os.path.join(_ENGINE_DIR, "machine_classes.csv"))


@lru_cache(maxsize=1)
def get_default_allowance_policy_document() -> dict:
    """The shipped allowance_policy.json, used to seed allowance_policies
    (version 1) the first time the app starts against an empty database."""
    with open(os.path.join(_ENGINE_DIR, "allowance_policy.json")) as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def get_seam_geometry() -> dict:
    with open(os.path.join(_ENGINE_DIR, "seam_geometry.json")) as fh:
        return json.load(fh)


def build_allowance_policy(document: dict) -> "al.AllowancePolicy":
    return al.AllowancePolicy(document)


def _sanitize_json(obj):
    """Recursively replace non-finite floats (inf/-inf/nan) with None.

    The engine legitimately produces +inf for the curvature radius of a
    straight seam (R_mm = infinity is the correct value for zero curvature,
    per motion_model.md's Fitts-law steering term) -- physically correct,
    but not valid JSON (strict encoders, and Postgres JSONB, both reject
    it). We sanitize at the API boundary only; nothing about the engine's
    own math or audit trail is altered, only how it's serialized for
    storage/transport. `None` is the natural JSON encoding of "no finite
    curvature radius applies here".
    """
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):  # obj != obj catches NaN
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize_json(v) for v in obj)
    return obj


def compute_operation(name: str, steps: list, bundle_size: int,
                       allowance_document: dict, allowance_profile: str) -> dict:
    """Run smv_assembly.assemble_operation() on a single operation's step
    list. `steps` must be shaped exactly like smv_assembly.py's step-dict
    grammar (handling/bundle/seam/cycle) -- see models.Operation.steps."""
    tax = get_taxonomy()
    mcat = get_machine_catalog()
    pol = build_allowance_policy(allowance_document)
    op = sa.Operation(name=name, steps=steps, bundle_size=bundle_size)
    return _sanitize_json(sa.assemble_operation(tax, mcat, pol, op, allowance_profile=allowance_profile))


def compute_style(operations: list[dict], allowance_document: dict,
                   allowance_profile: str) -> dict:
    """operations: list of {"name":..., "steps":..., "bundle_size":...} dicts
    (as stored in the operations table, in sequence order)."""
    tax = get_taxonomy()
    mcat = get_machine_catalog()
    pol = build_allowance_policy(allowance_document)
    ops = [sa.Operation(name=o["name"], steps=o["steps"], bundle_size=o.get("bundle_size", 1))
           for o in operations]
    return _sanitize_json(sa.assemble_style(tax, mcat, pol, ops, allowance_profile=allowance_profile))


def library_style_bulletin(size: str, variant: str, bundle_size: int,
                            allowance_document: dict, allowance_profile: str) -> dict:
    """Wraps shirt_library.build_style_operations() + smv_assembly.assemble_style()
    for the seeded woven-shirt library (used by /styles/{id}/compute when a
    style is flagged as library-seeded, and by GET /library)."""
    tax = get_taxonomy()
    mcat = get_machine_catalog()
    pol = build_allowance_policy(allowance_document)
    seam_geom = get_seam_geometry()
    ops = sl.build_style_operations(seam_geom, size, variant, bundle_size)
    return _sanitize_json(sa.assemble_style(tax, mcat, pol, ops, allowance_profile=allowance_profile))


def library_style_operations_raw(size: str, variant: str, bundle_size: int) -> list[dict]:
    """Returns the library's operations in the plain {name, steps, bundle_size}
    shape used to SEED an operations table row-set for a new style, without
    computing SMVs yet (that happens on /styles/{id}/compute)."""
    seam_geom = get_seam_geometry()
    ops = sl.build_style_operations(seam_geom, size, variant, bundle_size)
    return [{"name": o.name, "steps": o.steps, "bundle_size": o.bundle_size} for o in ops]


def library_catalog() -> dict:
    """Browse metadata for GET /library: available variants, sizes, and the
    raw seam/cycle operation names sourced from seam_geometry.json (no SMV
    numbers computed here -- this is a menu, not a bulletin)."""
    seam_geom = get_seam_geometry()
    return {
        "variants": ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"],
        "sizes": sl.SIZES,
        "default_bundle_size": sl.DEFAULT_BUNDLE_SIZE,
        "seam_operations": [s["operation"] for s in seam_geom["seam_operations"]],
        "cycle_operations": [c["operation"] for c in seam_geom["cycle_operations"]],
    }


def calibration_status_report() -> dict:
    """Honest data-quality surface for GET /calibration/status: which engine
    symbols are calibration-pending (shipped-default physics/behavioral
    constants awaiting real factory time-study data) vs literature-grounded,
    read straight off the vendored taxonomy -- never fabricated. Does not
    run a real calibration fit (no factory time-study data exists yet in
    this application's database); if/when time_study rows exist, wire them
    through calibration_fit.calibrate_all()/coverage_report() here instead
    of the static per-symbol listing.
    """
    tax = get_taxonomy()
    raw = tax.raw
    symbols = []
    for gp in raw["global_parameters"]:
        symbols.append({
            "scope": "global_parameter", "symbol": gp["symbol"], "name": gp.get("name"),
            "units": gp.get("units"), "default": gp.get("default"), "status": gp.get("status"),
            "source": gp.get("source"),
        })
    for ec in raw["engine_constants"]:
        symbols.append({
            "scope": "engine_constant", "symbol": ec["symbol"], "name": ec.get("meaning"),
            "units": ec.get("units"), "default": ec.get("default"), "status": ec.get("status"),
            "source": ec.get("source"),
        })
    n_pending = sum(1 for s in symbols if s["status"] == "calibration-pending")
    n_grounded = sum(1 for s in symbols if s["status"] != "calibration-pending")
    return {
        "engine_version": ENGINE_VERSION,
        "taxonomy_version": tax.version,
        "n_symbols": len(symbols),
        "n_calibration_pending": n_pending,
        "n_literature_grounded_or_fitted": n_grounded,
        "symbols": symbols,
        "real_factory_calibration_run": False,
        "note": (
            "No real factory time-study data has been loaded into this application "
            "yet, so calibration_fit.calibrate_all() has not been run against real "
            "data (per engine_phase1_report.md, the engine's own calibration module "
            "has only been demonstrated on a SYNTHETIC data generator). The listing "
            "above reflects the shipped taxonomy defaults' own status field "
            "(calibration-pending vs literature-grounded), which is the honest "
            "data-quality signal available until a real time-study campaign is run."
        ),
    }
