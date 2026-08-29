"""
worked_example.py -- End-to-end SMV breakdown for one shirt operation,
computed from the taxonomy engine with a full audit trail.

Operation: "Close armhole seam (felling/topstitch), size M" -- taken directly
from seam_geometry.json's armhole seam-operation record (path length, ply
count, curvature/guidance class, machine class, pivots, count=2 for both
scye sides). Handling steps around the seam are constructed from the element
taxonomy to represent a realistic operator cycle:

  1. HAM  acquire_and_match  -- reach for the sleeve, match it to the body
                                 armhole at 3 points, bring to work point (bimanual)
  2. HPF  present_under_foot -- set the assembled plies under the presser foot
  3. seam SNLS-TOP x2        -- sew both sides of the armhole seam; per-side
                                 time is MAX(pure machine cap, HGD guide time)
  4. HTC  trim_thread_ends   -- snip thread ends after each side (count=2)
  5. HDS  dispose_and_stack  -- move the finished garment to the output stack

Run directly to reproduce the audit trail and the machine-vs-guide
cross-check printed at the bottom.
"""
import json

import handling_time as ht
import machine_time as mt
import allowance as al
import smv_assembly as sa


def build_worked_example():
    tax = ht.load_taxonomy("element_taxonomy.json")
    mcat = mt.load_machine_catalog("machine_classes.csv")
    pol = al.load_allowance_policy("allowance_policy.json")
    seam_geom = json.load(open("seam_geometry.json"))

    armhole = next(op for op in seam_geom["seam_operations"] if op["component"] == "armhole")
    size = "M"
    L = armhole["path_length_mm"][size]

    op = sa.Operation(
        name="Close armhole seam (felling/topstitch), size M",
        bundle_size=20,
        steps=[
            {"kind": "handling", "element": "HAM",
             "params": {"distance_cm": 30.0, "plies": 4, "match_precision": "P2",
                        "fabric_class": "REF_POPLIN", "n_match_points": 3, "mass_g": 180.0}},
            {"kind": "handling", "element": "HPF",
             "params": {"approach_cm": 10.0, "edge_tolerance_mm": 2.0, "plies": 4,
                        "fabric_class": "REF_POPLIN"}},
            {"kind": "seam", "machine_class": armhole["machine_class"], "path_length_mm": L,
             "spi": armhole["spi"], "curvature_class": armhole["curvature_class"],
             "guidance_class": armhole["guidance_class"], "plies": armhole["plies"],
             "pivots": armhole["pivots"], "count": armhole["count"],
             "label": "armhole close/topstitch"},
            {"kind": "handling", "element": "HTC",
             "params": {"n_ends": 2, "tool_class": "NIPPER", "reach_cm": 5.0,
                        "fabric_class": "REF_POPLIN"},
             "count": armhole["count"]},
            {"kind": "handling", "element": "HDS",
             "params": {"distance_cm": 35.0, "precision_class": "P1", "mass_g": 400.0,
                        "fabric_class": "REF_POPLIN"}},
        ],
    )
    result = sa.assemble_operation(tax, mcat, pol, op)
    return tax, mcat, pol, seam_geom, armhole, op, result


def crosscheck(tax, mcat, seam_geom, armhole, result):
    """Independent hand-derivation of the seam step's MAX(machine,guide) time,
    bypassing smv_assembly.py entirely, to confirm the engine's output."""
    size = "M"
    L = armhole["path_length_mm"][size]
    pure = mt.pure_machine_time_seam(mcat, armhole["machine_class"], path_length_mm=L,
                                      spi=armhole["spi"], plies=armhole["plies"],
                                      pivots=armhole["pivots"])
    tol_raw = mt.es.GUIDANCE_TOLERANCE_MM[armhole["guidance_class"]]
    tol = max(tol_raw, 0.3)  # HGD domain floor -- see smv_assembly.py note
    R_mm = mt.es.CURVATURE_CLASSES_MM[armhole["curvature_class"]]
    guide = tax.compute_element(
        "HGD", path_cm=L / 10.0, tolerance_mm=tol,
        radius_cm=(R_mm / 10.0 if R_mm != float("inf") else None),
        plies=armhole["plies"], fabric_class="REF_POPLIN", guided_by="HAND",
    )
    count = armhole["count"]
    t_machine = pure["total_time_s"] * count
    t_guide = guide["t_basic_s"] * count
    engine_t_basic = result["steps"][2]["t_basic_s"]
    assert abs(max(t_machine, t_guide) - engine_t_basic) < 1e-6, (
        f"crosscheck mismatch: hand={max(t_machine, t_guide):.4f} "
        f"engine={engine_t_basic:.4f}"
    )
    return t_machine, t_guide, engine_t_basic


if __name__ == "__main__":
    tax, mcat, pol, seam_geom, armhole, op, result = build_worked_example()

    print(f"Operation: {op.name}")
    print(f"BT_op = {result['BT_op_s']:.4f} s   "
          f"ST_op = {result['ST_op_s']:.4f} s = {result['ST_op_min']:.5f} min "
          f"= {result['ST_op_min']*sa.TMU_PER_MINUTE:.2f} TMU")
    print("no_double_count warnings:", result["no_double_count_warnings"])
    print()
    for s in result["steps"]:
        label = s.get("element", s.get("machine_class"))
        binding = f" [{s['binding']} binds]" if "binding" in s else ""
        print(f"  {s['kind']:9s} {label:10s} t_basic={s['t_basic_s']:.4f}s "
              f" t_std={s['t_standard_s']:.4f}s  allowance={s['allowance']['total_percent']:.1f}%{binding}")

    print()
    t_machine, t_guide, engine_t_basic = crosscheck(tax, mcat, seam_geom, armhole, result)
    print(f"Independent crosscheck -- machine-only: {t_machine:.4f}s, "
          f"HGD guide-only: {t_guide:.4f}s, MAX selected: {engine_t_basic:.4f}s -- MATCH")
