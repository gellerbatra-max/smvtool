"""
smv_assembly.py -- SMV assembly (Pillar 4): handling + machine + bundle ->
operation standard time -> style SMV, with a full audit trail.

Implements element_taxonomy.json's assembly_rules exactly:
  * BT_op = sum(non-overlapping handling) + sum(MAX(t_machine, t_guide)
            per seam segment) + sum(bundle t / bundle_size)
  * ST_op = sum over elements of BT_e * (1 + sum of applicable allowance
            fractions); allowances applied PER ELEMENT, never as one lump
  * SMV_style = sum(ST_op), reported in minutes and TMU
  * machine_overlap: per seam step, t_machine comes from the machine-time
    pillar ALONE (machine_time.pure_machine_time_seam -- no guidance term)
    and t_guide comes from the HGD handling element (handling_time.py);
    whichever is larger binds, and that choice is recorded and used to pick
    the element's allowance component (MACHINE_STATION vs MANUAL_HANDLING)
  * bundle_amortisation: BUNDLE-profile step times divided by bundle_size,
    a style/line parameter recorded in the audit trail, not an element param
  * no_double_count: flags an HDS step immediately followed by an
    HAG/HAM/HAB step whose distance_cm exceeds the HDS's own distance_cm

Public API
----------
    Operation(name, steps, bundle_size=1)     -- steps: list of step dicts
    assemble_operation(tax, mcat, pol, op, allowance_profile=...) -> dict
    assemble_style(tax, mcat, pol, operations, allowance_profile=...) -> dict

Step dict shapes
----------------
    {"kind": "handling", "element": "HAG", "params": {...}}
    {"kind": "bundle",   "element": "HBO", "params": {...}}
    {"kind": "seam", "machine_class": "SNLS-UBT", "path_length_mm": ...,
     "spi": ..., "curvature_class": "moderate", "guidance_class": "seam_hidden",
     "plies": 2, "pivots": 0, "attachment": None, "guided_by": "HAND",
     "fabric_class": "REF_POPLIN", "count": 1}
    {"kind": "cycle", "machine_class": "BH-LS", "stitches": 88, "count": 1}

`count` (default 1) repeats a step's basic time that many times within the
operation (e.g. "attach cuff to sleeve" x2 for two cuffs) before allowances.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import handling_time as ht
import machine_time as mt
import allowance as al


TMU_PER_MINUTE = 1666.6667


@dataclass
class Operation:
    name: str
    steps: list
    bundle_size: int = 1


# --------------------------------------------------------------------------
# No-double-count validator (assembly_rules.no_double_count)
# --------------------------------------------------------------------------

def check_no_double_count(steps: list) -> list[str]:
    warnings = []
    for i in range(len(steps) - 1):
        s, nxt = steps[i], steps[i + 1]
        if s.get("kind") == "handling" and s.get("element") == "HDS":
            hds_dist = s.get("params", {}).get("distance_cm",
                        ht_default_distance("HDS"))
            if nxt.get("kind") == "handling" and nxt.get("element") in ("HAG", "HAM", "HAB"):
                nxt_dist = nxt.get("params", {}).get("distance_cm",
                            ht_default_distance(nxt["element"]))
                if nxt_dist > hds_dist:
                    warnings.append(
                        f"possible double-count of hand-return travel: step {i} "
                        f"(HDS, distance_cm={hds_dist}) immediately followed by "
                        f"step {i+1} ({nxt['element']}, distance_cm={nxt_dist} > HDS distance)"
                    )
    return warnings


_HT_DEFAULT_CACHE: dict = {}


def ht_default_distance(element_code: str, tax: "ht.Taxonomy | None" = None) -> float:
    """Best-effort lookup of an element's default distance_cm, for the
    no-double-count heuristic when a step doesn't explicitly supply one."""
    if tax is not None:
        el = tax.elements.get(element_code, {})
        for p in el.get("parameters", []):
            if p["name"] == "distance_cm":
                return p.get("default", 0.0)
    return _HT_DEFAULT_CACHE.get(element_code, 0.0)


# --------------------------------------------------------------------------
# Per-step assembly
# --------------------------------------------------------------------------

def _assemble_handling_step(tax, pol, step, allowance_profile) -> dict:
    code = step["element"]
    params = dict(step.get("params", {}))
    count = step.get("count", 1)
    result = tax.compute_element(code, **params)
    element_profile = result["allowance_profile"]
    result["params"] = params  # ensure allowance.py sees raw params, not just resolved
    t_basic = result["t_basic_s"] * count
    alw = pol.resolve_element_allowance(code, element_profile, result, allowance_profile)
    t_standard = t_basic * (1.0 + alw["total_percent"] / 100.0)
    return {
        "kind": "handling", "element": code, "count": count,
        "element_profile": element_profile,
        "t_basic_s": t_basic, "t_standard_s": t_standard,
        "allowance": alw, "audit": result,
    }


def _assemble_bundle_step(tax, pol, step, allowance_profile, bundle_size) -> dict:
    code = step["element"]
    params = dict(step.get("params", {}))
    count = step.get("count", 1)
    result = tax.compute_element(code, **params)
    t_basic_full = result["t_basic_s"] * count
    t_basic_amortised = t_basic_full / bundle_size
    result["params"] = params
    alw = pol.resolve_element_allowance(code, "BUNDLE", result, allowance_profile)
    t_standard = t_basic_amortised * (1.0 + alw["total_percent"] / 100.0)
    return {
        "kind": "bundle", "element": code, "count": count,
        "bundle_size": bundle_size,
        "t_basic_full_s": t_basic_full, "t_basic_s": t_basic_amortised,
        "t_standard_s": t_standard,
        "allowance": alw, "audit": result,
    }


def _assemble_seam_step(tax, mcat, pol, step, allowance_profile) -> dict:
    count = step.get("count", 1)
    guidance_class = step.get("guidance_class", "seam_hidden")
    fabric_class = step.get("fabric_class", "REF_POPLIN")
    guided_by = step.get("guided_by", "HAND")

    t_machine_rec = mt.pure_machine_time_seam(
        mcat, step["machine_class"], path_length_mm=step["path_length_mm"],
        spi=step["spi"], plies=step.get("plies", 2), pivots=step.get("pivots", 0),
        attachment=step.get("attachment"), label=step.get("label", ""),
    )

    tol_mm_raw = mt.es.GUIDANCE_TOLERANCE_MM[guidance_class]
    # KNOWN SPEC CONFLICT (flagged, not silently absorbed): effective_spm.py's
    # GUIDANCE_TOLERANCE_MM["edgestitch_critical"] = 0.25 mm, but HGD's own
    # declared parameter domain in element_taxonomy.json floors tolerance_mm
    # at 0.3 mm. Until the two source files are reconciled upstream, clamp to
    # HGD's domain floor (its steering-law fit is only asserted valid down to
    # 0.3 mm) and record the clamp in the audit trail, mirroring how the
    # taxonomy's own PHI ceiling clamp is surfaced rather than hidden.
    tol_clamped = tol_mm_raw < 0.3
    tol_mm = max(tol_mm_raw, 0.3)
    curvature_class = step.get("curvature_class", "straight")
    R_mm = mt.es.CURVATURE_CLASSES_MM[curvature_class]
    guide_rec = tax.compute_element(
        "HGD", path_cm=step["path_length_mm"] / 10.0, tolerance_mm=tol_mm,
        radius_cm=(None if R_mm == float("inf") else R_mm / 10.0),
        plies=step.get("plies", 2), fabric_class=fabric_class, guided_by=guided_by,
    )
    guide_rec["tolerance_mm_clamped"] = tol_clamped
    guide_rec["tolerance_mm_raw"] = tol_mm_raw

    t_machine = t_machine_rec["total_time_s"] * count
    t_guide = guide_rec["t_basic_s"] * count
    binding = "machine" if t_machine >= t_guide else "guide"
    t_basic = max(t_machine, t_guide)
    # AR2 / component_assignment: which side binds determines the allowance
    # COMPONENT (machine-delay only ever applies to actually-machine-bound
    # time), but CLOSE_ATTENTION is keyed to the seam's own tolerance
    # regardless of which side happens to be the pace-setter -- the operator
    # is still watching the seam even when the machine sets the pace. Always
    # resolve categories against "HGD" (so the tolerance-based trigger_rule
    # fires) and the tolerance-carrying audit record; effective_profile alone
    # controls which categories (notably MACHINE_DELAY) are eligible.
    guide_rec["params"] = {"tolerance_mm": tol_mm}
    effective_profile = "MACHINE_STATION" if binding == "machine" else "MANUAL_HANDLING"
    alw = pol.resolve_element_allowance("HGD", effective_profile, guide_rec, allowance_profile)
    t_standard = t_basic * (1.0 + alw["total_percent"] / 100.0)

    return {
        "kind": "seam", "machine_class": step["machine_class"], "count": count,
        "binding": binding, "t_machine_s": t_machine, "t_guide_s": t_guide,
        "t_basic_s": t_basic, "t_standard_s": t_standard,
        "element_profile": effective_profile,
        "allowance": alw,
        "audit": {"machine": t_machine_rec, "guide": guide_rec},
    }


def _assemble_cycle_step(mcat, pol, step, allowance_profile) -> dict:
    count = step.get("count", 1)
    result = mt.time_cycle(mcat, step["machine_class"], stitches=step["stitches"])
    t_basic = result["total_time_s"] * count
    alw = pol.resolve_element_allowance("CYCLE_TIME", "MACHINE_STATION", {"params": {}}, allowance_profile)
    t_standard = t_basic * (1.0 + alw["total_percent"] / 100.0)
    return {
        "kind": "cycle", "machine_class": step["machine_class"], "count": count,
        "t_basic_s": t_basic, "t_standard_s": t_standard,
        "allowance": alw, "audit": result,
    }


# --------------------------------------------------------------------------
# Operation / style assembly
# --------------------------------------------------------------------------

def assemble_operation(tax, mcat, pol, op: Operation, allowance_profile: str = "WOVEN_TOPS_DECOMPOSED") -> dict:
    dup_warnings = check_no_double_count(op.steps)
    step_records = []
    for step in op.steps:
        kind = step["kind"]
        if kind == "handling":
            rec = _assemble_handling_step(tax, pol, step, allowance_profile)
        elif kind == "bundle":
            rec = _assemble_bundle_step(tax, pol, step, allowance_profile, op.bundle_size)
        elif kind == "seam":
            rec = _assemble_seam_step(tax, mcat, pol, step, allowance_profile)
        elif kind == "cycle":
            rec = _assemble_cycle_step(mcat, pol, step, allowance_profile)
        else:
            raise ValueError(f"unknown step kind {kind!r}")
        step_records.append(rec)

    BT_op = sum(r["t_basic_s"] for r in step_records)
    ST_op = sum(r["t_standard_s"] for r in step_records)

    return {
        "operation": op.name,
        "bundle_size": op.bundle_size,
        "allowance_profile": allowance_profile,
        "steps": step_records,
        "BT_op_s": BT_op,
        "ST_op_s": ST_op,
        "BT_op_min": BT_op / 60.0,
        "ST_op_min": ST_op / 60.0,
        "no_double_count_warnings": dup_warnings,
    }


def assemble_style(tax, mcat, pol, operations: list[Operation],
                    allowance_profile: str = "WOVEN_TOPS_DECOMPOSED") -> dict:
    op_results = [assemble_operation(tax, mcat, pol, op, allowance_profile) for op in operations]
    ST_style_min = sum(o["ST_op_min"] for o in op_results)
    BT_style_min = sum(o["BT_op_min"] for o in op_results)
    return {
        "allowance_profile": allowance_profile,
        "operations": op_results,
        "BT_style_min": BT_style_min,
        "ST_style_min": ST_style_min,
        "SMV_min": ST_style_min,
        "SMV_tmu": ST_style_min * TMU_PER_MINUTE,
        "all_warnings": [w for o in op_results for w in o["no_double_count_warnings"]],
    }


if __name__ == "__main__":
    tax = ht.load_taxonomy("element_taxonomy.json")
    mcat = mt.load_machine_catalog("machine_classes.csv")
    pol = al.load_allowance_policy("allowance_policy.json")

    op = Operation(
        name="Set pocket to front (3 sides + point)",
        steps=[
            {"kind": "handling", "element": "HAG", "params": {"distance_cm": 30, "precision_class": "P1"}},
            {"kind": "seam", "machine_class": "SNLS-UBT", "path_length_mm": 260, "spi": 10,
             "curvature_class": "tight", "guidance_class": "seam_visible", "plies": 3, "pivots": 3},
            {"kind": "handling", "element": "HDS", "params": {"distance_cm": 20}},
        ],
    )
    r = assemble_operation(tax, mcat, pol, op)
    print(f"{op.name}: BT={r['BT_op_s']:.3f}s ST={r['ST_op_s']:.3f}s "
          f"({r['ST_op_min']*TMU_PER_MINUTE:.1f} TMU)")
