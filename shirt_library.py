"""
shirt_library.py -- woven-top operation library (Phase 2, "Operation library").

Builds a full operation bulletin (list of smv_assembly.Operation objects) for
a classic men's woven shirt, plus SHORT_SLEEVE and BLOUSE_COLLARLESS style
variants, from seam_geometry.json's already-sourced/derived seam and cycle
geometry (Phase 0). This module does NOT introduce any new proprietary or
fabricated timing data: every operation's MACHINE-side parameters come
straight from seam_geometry.json; every operation's HANDLING-side parameters
(which element, what distance/mass/precision) are assigned by an explicit,
documented rule (see HANDLING_RULE below), not by per-operation guesswork,
so the assignment is auditable and consistent across all 21+ operations.

STYLE VARIANTS -- what is and is not included here
----------------------------------------------------
SHORT_SLEEVE is fully geometry-derivable from Phase 0's own
points_of_measure_mm: a short-sleeve hem length is taken as the armhole
circumference (armhole_c) less a fixed underarm/seam-allowance offset -- the
same kind of explicit DERIVED_GEOMETRIC rule seam_geometry.json already uses
elsewhere (e.g. the collar run-stitch length rule). It drops every
cuff/sleeve-placket operation and buttonhole.

BLOUSE_COLLARLESS is a bound/faced (collarless) neckline variant built on
the SAME body pattern: it drops the two-piece collar+band assembly and
front-placket buttonhole-side band, replacing them with a single neckline-
facing operation whose length is derived from the existing collar_mm size
key (a close geometric proxy for neckline circumference, on the same
explicit-rule footing as the rest of this file).

A genuinely distinct blouse silhouette -- darted or princess-seamed body,
gathered cap sleeve, separate blouse-specific grading -- is NOT built here:
that needs its own Phase-0-style points-of-measure derivation (a blouse
sample or spec chart), which was not available this phase. Building it now
from unsourced assumptions would be exactly the kind of unverifiable filler
data this project has avoided throughout; see the Phase 2 report's
"Known limitations" section.

HANDLING_RULE (documented, not per-operation guesswork)
----------------------------------------------------------
 * Any seam operation whose name contains one of JOIN_KEYWORDS ("attach",
   "set", "join", "close") is a two-piece (or piece-to-body) matching
   action -> acquire element = HAM (acquire_and_match), bimanual.
 * Any seam operation whose name contains one of RESEAT_KEYWORDS
   ("topstitch", "edge-stitch", "hem", "stitch buttonhole-side") is a second
   pass over an already-assembled single piece -> acquire element = HAG
   (acquire_part), single-piece pickup.
 * "Form + stitch front placket" additionally gets an HFC (fold_or_crease)
   step before the seam, since placket forming is explicitly a folding
   operation.
 * Every seam operation gets one HPF (present_under_foot) before the seam
   step and one HTC (trim_thread_ends) + one HDS (dispose_and_stack) after
   it (dispose only after the LAST seam step of that operation's count).
 * Acquire distance/mass parameters come from a 3-tier SIZE_CLASS table
   (SMALL/MEDIUM/LARGE) keyed by component, reflecting how far the operator
   reaches and how heavy the assembly is at that point in the sequence --
   documented per component below, not fitted or sourced (status:
   ESTIMATE, same class as seam_geometry.json's own ESTIMATE-tier fields;
   these are exactly the kind of coefficient calibration_fit.py exists to
   correct once real time studies are available).
 * Cycle operations (buttonhole/button-sew/bartack) get one HPF + the cycle
   step (count = the per-size buttonhole/button/bartack count) + one HDS;
   when count > 1, an HRP (reposition_mid_seam) step with n_events=count-1
   represents moving from one buttonhole/button/bartack position to the
   next without releasing the fabric.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import handling_time as ht
import machine_time as mt
import allowance as al
import smv_assembly as sa

SIZES = ["S", "M", "L", "XL", "XXL"]

JOIN_KEYWORDS = ("attach", "set collar", "set pocket", "join", "close")
RESEAT_KEYWORDS = ("topstitch", "edge-stitch", "hem", "stitch buttonhole-side")

# ---- SIZE_CLASS table: component -> (distance_cm, mass_g) for acquire/dispose.
# status: ESTIMATE (engineering judgement, no source -- calibrate first, same
# provenance tier as seam_geometry.json's own ESTIMATE-tier notes fields).
SIZE_CLASS = {
    # SMALL: small cut pieces handled at arm's length from a stack
    "cuff": (15.0, 45.0), "collar_band": (15.0, 45.0),
    "sleeve_placket": (15.0, 40.0), "pocket": (16.0, 50.0),
    # MEDIUM: mid-size panels
    "collar": (22.0, 80.0), "front_placket": (22.0, 90.0),
    # LARGE: whole-body-scale panels/assemblies
    "back_yoke": (30.0, 150.0), "sleeve": (32.0, 180.0),
    "armhole": (34.0, 220.0), "side_seam": (34.0, 240.0),
    "bottom_hem": (34.0, 260.0),
}

DEFAULT_BUNDLE_SIZE = 20   # operator-station bundle size; a style/line parameter, not fitted


def _is_join(op_name: str) -> bool:
    name = op_name.lower()
    return any(k in name for k in JOIN_KEYWORDS)


def _is_reseat(op_name: str) -> bool:
    name = op_name.lower()
    return any(k in name for k in RESEAT_KEYWORDS)


def build_seam_operation(op_spec: dict, size: str, bundle_size: int = DEFAULT_BUNDLE_SIZE) -> sa.Operation:
    """One smv_assembly.Operation for a single seam_geometry.json seam_operations
    record, at the given size. HANDLING_RULE (module docstring) governs the
    acquire element choice and its parameters; MACHINE parameters are taken
    verbatim from op_spec."""
    name = op_spec["operation"]
    component = op_spec["component"]
    L = op_spec["path_length_mm"][size]
    count = op_spec["count"]
    dist_cm, mass_g = SIZE_CLASS.get(component, (25.0, 100.0))

    steps = []
    if name == "Form + stitch front placket (button side)":
        steps.append({"kind": "handling", "element": "HFC",
                      "params": {"fold_length_cm": dist_cm, "fold_depth_mm": 10.0,
                                 "n_folds": 1, "plies": op_spec["plies"] - 1}})

    if _is_join(name):
        steps.append({"kind": "handling", "element": "HAM",
                      "params": {"distance_cm": dist_cm, "plies": op_spec["plies"],
                                 "match_precision": "P2", "fabric_class": "REF_POPLIN",
                                 "n_match_points": 3 if component in ("armhole", "sleeve") else 2,
                                 "mass_g": mass_g}})
    else:
        steps.append({"kind": "handling", "element": "HAG",
                      "params": {"distance_cm": dist_cm, "precision_class": "P1",
                                 "fabric_class": "REF_POPLIN", "plies": min(op_spec["plies"], 2),
                                 "mass_g": mass_g}})

    steps.append({"kind": "handling", "element": "HPF",
                  "params": {"approach_cm": 10.0, "edge_tolerance_mm": 2.0,
                             "plies": op_spec["plies"], "fabric_class": "REF_POPLIN"}})
    steps.append({"kind": "seam", "machine_class": op_spec["machine_class"],
                  "path_length_mm": L, "spi": op_spec["spi"],
                  "curvature_class": op_spec["curvature_class"],
                  "guidance_class": op_spec["guidance_class"], "plies": op_spec["plies"],
                  "pivots": op_spec["pivots"], "count": count, "label": name})
    steps.append({"kind": "handling", "element": "HTC",
                  "params": {"n_ends": 2, "tool_class": "NIPPER", "reach_cm": 5.0,
                             "fabric_class": "REF_POPLIN"}, "count": count})
    steps.append({"kind": "handling", "element": "HDS",
                  "params": {"distance_cm": 30.0, "precision_class": "P0",
                             "mass_g": mass_g * 1.2, "fabric_class": "REF_POPLIN"}})

    return sa.Operation(name=f"{component}: {name} (size {size})", steps=steps, bundle_size=bundle_size)


def build_cycle_operation(op_spec: dict, size: str, bundle_size: int = DEFAULT_BUNDLE_SIZE) -> sa.Operation:
    """One smv_assembly.Operation for a seam_geometry.json cycle_operations
    record (buttonhole / button-sew / bartack) at the given size."""
    name = op_spec["operation"]
    component = op_spec["component"]
    count = op_spec["count"][size] if isinstance(op_spec["count"], dict) else op_spec["count"]
    dist_cm, mass_g = SIZE_CLASS.get(component, (20.0, 80.0))

    steps = [
        {"kind": "handling", "element": "HPF",
         "params": {"approach_cm": 8.0, "edge_tolerance_mm": 2.0, "plies": 2,
                    "fabric_class": "REF_POPLIN"}},
        {"kind": "cycle", "machine_class": op_spec["machine_class"],
         "stitches": op_spec["stitches_each"], "count": count},
    ]
    if count > 1:
        steps.append({"kind": "handling", "element": "HRP",
                      "params": {"shift_cm": 8.0, "tolerance_mm": 3.0, "plies": 2,
                                 "fabric_class": "REF_POPLIN", "n_events": count - 1}})
    steps.append({"kind": "handling", "element": "HDS",
                  "params": {"distance_cm": dist_cm, "precision_class": "P0",
                             "mass_g": mass_g, "fabric_class": "REF_POPLIN"}})

    return sa.Operation(name=f"{component}: {name} (size {size})", steps=steps, bundle_size=bundle_size)


# --------------------------------------------------------------------------
# Full-style operation bulletins (variant-aware)
# --------------------------------------------------------------------------

# operation names to EXCLUDE for the short-sleeve variant (cuff/gauntlet work
# no longer applies once the sleeve is short)
SHORT_SLEEVE_EXCLUDE_SEAM = {
    "Run-stitch cuff (3 sides)", "Topstitch cuff edge", "Attach cuff to sleeve",
    "Sleeve placket (gauntlet) set + topstitch",
}
SHORT_SLEEVE_EXCLUDE_CYCLE = {"Buttonhole, cuff (incl. adjustment)", "Buttonhole, gauntlet"}

# operation names to EXCLUDE for the collarless-blouse variant
BLOUSE_EXCLUDE_SEAM = {
    "Run-stitch collar (close top+under collar, 3 sides)",
    "Topstitch/edge-stitch collar outer edge",
    "Attach band to collar leaf + close band",
    "Attach collar band to neckline (set collar)",
    "Topstitch collar band",
    "Stitch buttonhole-side front edge / band",
}
BLOUSE_EXCLUDE_CYCLE = {"Buttonhole, collar band"}


def _short_sleeve_hem_spec(seam_geom: dict) -> dict:
    """DERIVED_GEOMETRIC: a short-sleeve hem length is the armhole
    circumference (already in points_of_measure_mm.armhole_c) less a fixed
    2x12mm underarm/seam-allowance offset, folded to a single hem pass --
    same explicit-rule convention as seam_geometry.json's own scaling_rule
    fields (e.g. the collar run-stitch length rule)."""
    armhole_c = seam_geom["points_of_measure_mm"]["armhole_c"]
    path = {sz: round(armhole_c[sz] - 24.0, 1) for sz in SIZES}
    return {
        "component": "sleeve", "operation": "Hem short sleeve (folder)",
        "machine_class": "SNLS-HEM", "path_length_mm": path, "count": 1,
        "spi": 12, "curvature_class": "gentle", "guidance_class": "mechanically_guided",
        "plies": 2, "pivots": 0,
        "scaling_rule": "= armhole_c - 24mm (underarm/seam-allowance offset)",
        "provenance": "DERIVED_GEOMETRIC",
        "notes": "Short-sleeve hem folded with a hem-folder attachment; replaces cuff assembly entirely.",
    }


def _blouse_neckline_facing_spec(seam_geom: dict) -> dict:
    """DERIVED_GEOMETRIC: a collarless neckline facing seam length is taken
    as the collar_mm size key (already in size_key) less a small 16mm
    front-opening allowance -- collar_mm is itself a close geometric proxy
    for neckline circumference on a shirt-collar-family pattern."""
    collar_mm = {sz: seam_geom["size_key"][sz]["collar_mm"] for sz in SIZES}
    path = {sz: round(collar_mm[sz] - 16.0, 1) for sz in SIZES}
    return {
        "component": "neckline", "operation": "Attach facing, bound/faced neckline (set collar)",
        "machine_class": "SNLS-UBT", "path_length_mm": path, "count": 1,
        "spi": 12, "curvature_class": "tight", "guidance_class": "seam_visible",
        "plies": 3, "pivots": 0,
        "scaling_rule": "= collar_mm - 16mm (front-opening allowance)",
        "provenance": "DERIVED_GEOMETRIC",
        "notes": "Bound/faced neckline replacing the two-piece collar+band assembly for a collarless blouse variant.",
    }


def build_style_operations(seam_geom: dict, size: str, variant: str = "CLASSIC",
                            bundle_size: int = DEFAULT_BUNDLE_SIZE) -> list[sa.Operation]:
    """variant in {"CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"}."""
    if variant not in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
        raise ValueError(f"unknown variant {variant!r}")

    seam_specs = list(seam_geom["seam_operations"])
    cycle_specs = list(seam_geom["cycle_operations"])

    if variant == "SHORT_SLEEVE":
        seam_specs = [s for s in seam_specs if s["operation"] not in SHORT_SLEEVE_EXCLUDE_SEAM]
        cycle_specs = [c for c in cycle_specs if c["operation"] not in SHORT_SLEEVE_EXCLUDE_CYCLE]
        seam_specs.append(_short_sleeve_hem_spec(seam_geom))
    elif variant == "BLOUSE_COLLARLESS":
        seam_specs = [s for s in seam_specs if s["operation"] not in BLOUSE_EXCLUDE_SEAM]
        cycle_specs = [c for c in cycle_specs if c["operation"] not in BLOUSE_EXCLUDE_CYCLE]
        seam_specs.append(_blouse_neckline_facing_spec(seam_geom))
        # front placket, collar-band and gauntlet buttonholes drop by 2 (band+collar);
        # button count is unaffected by this change (still front placket + cuffs)

    ops = [build_seam_operation(s, size, bundle_size) for s in seam_specs]
    ops += [build_cycle_operation(c, size, bundle_size) for c in cycle_specs]
    return ops


def style_smv(seam_geom: dict, size: str, variant: str = "CLASSIC",
              allowance_profile: str = "WOVEN_TOPS_DECOMPOSED",
              bundle_size: int = DEFAULT_BUNDLE_SIZE):
    tax = ht.load_taxonomy("element_taxonomy.json")
    mcat = mt.load_machine_catalog("machine_classes.csv")
    pol = al.load_allowance_policy("allowance_policy.json")
    ops = build_style_operations(seam_geom, size, variant, bundle_size)
    return sa.assemble_style(tax, mcat, pol, ops, allowance_profile=allowance_profile)


if __name__ == "__main__":
    seam_geom = json.load(open("seam_geometry.json"))
    for variant in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
        result = style_smv(seam_geom, "M", variant)
        n_ops = len(result["operations"])
        print(f"{variant:20s} size M: {n_ops:2d} operations, "
              f"SMV = {result['SMV_min']:.3f} min = {result['SMV_tmu']:.1f} TMU")
