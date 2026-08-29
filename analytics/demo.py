"""
demo.py -- end-to-end demonstration of the analytics layer against the
CLASSIC woven shirt, size M: line balance, costing, and one what-if
scenario (machine-class swap). Run with:

    SMV_ENGINE_DIR=/path/to/smv_engine_bundle python demo.py

Writes: demo_line_balance.csv, demo_workstation_loads.csv, demo_costing.csv,
demo_what_if.csv, demo_report.md -- all real numbers computed by calling
into the engine (smv_assembly.assemble_style / assemble_operation), never
hardcoded.
"""
from __future__ import annotations

import csv
import json
import os
import sys

# Make this file importable as a script regardless of PYTHONSAFEPATH /
# invocation style (`python demo.py` from another cwd, `python -m demo`,
# etc.) -- explicit, rather than relying on Python's (increasingly
# opt-out-by-default) automatic script-directory sys.path insertion.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine_loader as el
import line_balancing as lb
import costing as ct
import what_if as wi


def _engine_dir() -> str:
    env = os.environ.get("SMV_ENGINE_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("../engine/smv_engine_bundle", "../smv_engine_bundle", "./smv_engine_bundle", "."):
        cand = os.path.abspath(os.path.join(here, rel))
        if os.path.isfile(os.path.join(cand, "element_taxonomy.json")):
            return cand
    raise RuntimeError("Set SMV_ENGINE_DIR to the engine bundle directory")


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    engine_dir = _engine_dir()
    ctx = el.load_engine_context(engine_dir)
    with open(os.path.join(engine_dir, "seam_geometry.json")) as fh:
        seam_geom = json.load(fh)

    SIZE, VARIANT = "M", "CLASSIC"
    LABOUR_RATE_PER_HOUR = 3.20     # USD/hour, illustrative
    LINE_EFFICIENCY = 0.80          # 80%, typical for a running woven-shirt line
    N_WORKSTATIONS = 10
    TARGET_RATE_PER_HOUR = 45.0     # garments/hour

    ops, style = el.build_and_assemble_style(ctx, seam_geom, SIZE, VARIANT)

    print(f"=== {VARIANT} shirt, size {SIZE} ===")
    print(f"{len(ops)} operations, style SMV = {style['SMV_min']:.4f} min "
          f"= {style['SMV_tmu']:.1f} TMU")

    # ---------------------------------------------------------------- STEP 1
    lb_report = lb.balance_line(style, n_workstations=N_WORKSTATIONS,
                                 target_rate_per_hour=TARGET_RATE_PER_HOUR)
    print(f"\n--- Line balance ({N_WORKSTATIONS} workstations, "
          f"target {TARGET_RATE_PER_HOUR:.0f}/hr) ---")
    print(f"Bottleneck: workstation {lb_report['bottleneck_workstation']} "
          f"at {lb_report['bottleneck_smv_min']:.4f} min")
    print(f"Theoretical efficiency: {lb_report['theoretical_efficiency']*100:.2f}%")
    print(f"Achievable output: {lb_report['achievable_output_per_hour']:.2f} garments/hour "
          f"(target {lb_report['target_rate_per_hour']:.1f}/hour, "
          f"meets_target={lb_report['meets_target']}, "
          f"efficiency_at_target={lb_report['achievable_efficiency_at_target']*100:.2f}%)")

    ws_rows = [{"workstation": w["workstation"], "operations": "; ".join(w["operations"]),
                "n_operations": len(w["operations"]), "load_min": round(w["load_min"], 4),
                "idle_min": round(w["idle_min"], 4)}
               for w in lb_report["workstations"]]
    write_csv("demo_workstation_loads.csv", ws_rows,
              ["workstation", "operations", "n_operations", "load_min", "idle_min"])

    assignment_rows = [{"operation": name, "workstation": station}
                        for name, station in sorted(lb_report["assignment"].items(),
                                                      key=lambda kv: kv[1])]
    write_csv("demo_line_balance.csv", assignment_rows, ["operation", "workstation"])

    # ---------------------------------------------------------------- STEP 2
    cost_report = ct.full_costing_report(
        style, labour_rate_per_hour=LABOUR_RATE_PER_HOUR, efficiency=LINE_EFFICIENCY,
        n_operators=N_WORKSTATIONS, target_output_per_hour=TARGET_RATE_PER_HOUR)
    print(f"\n--- Costing (labour rate {LABOUR_RATE_PER_HOUR:.2f}/hr, "
          f"{LINE_EFFICIENCY*100:.0f}% efficiency) ---")
    print(f"Cost of make per garment: {cost_report['cost_per_garment']:.4f}")
    print(f"Output at {N_WORKSTATIONS} operators: "
          f"{cost_report['production_at_n_operators']['output_per_hour']:.2f}/hour, "
          f"{cost_report['production_at_n_operators']['output_per_shift']:.1f}/8h-shift")
    print(f"Operators required for {TARGET_RATE_PER_HOUR:.0f}/hour target: "
          f"{cost_report['required_operators_for_target']['operators_required']} "
          f"(raw {cost_report['required_operators_for_target']['operators_required_raw']:.2f})")

    cost_rows = [
        {"metric": "smv_min", "value": round(cost_report["smv_min"], 4)},
        {"metric": "labour_rate_per_hour", "value": LABOUR_RATE_PER_HOUR},
        {"metric": "efficiency", "value": LINE_EFFICIENCY},
        {"metric": "cost_per_garment", "value": round(cost_report["cost_per_garment"], 4)},
        {"metric": "output_per_hour_at_n_operators", "value":
            round(cost_report["production_at_n_operators"]["output_per_hour"], 2)},
        {"metric": "output_per_shift_at_n_operators", "value":
            round(cost_report["production_at_n_operators"]["output_per_shift"], 1)},
        {"metric": "daily_labour_cost_at_n_operators", "value":
            round(cost_report["daily_labour_cost_at_n_operators"], 2)},
        {"metric": "operators_required_for_target", "value":
            cost_report["required_operators_for_target"]["operators_required"]},
        {"metric": "operators_required_for_target_raw", "value":
            round(cost_report["required_operators_for_target"]["operators_required_raw"], 3)},
    ]
    write_csv("demo_costing.csv", cost_rows, ["metric", "value"])

    # ---------------------------------------------------------------- STEP 3
    # What-if: replace the felled/safety-stitch side-seam machine (FOA-401,
    # feed-off-arm chainstitch lapseamer) with a 5-thread safety-stitch
    # machine (OL-5T-SS) -- a real method decision a line planner would face.
    scenario_op = "side_seam: Close side seam (felled or safety-stitch) (size M)"
    scenario = wi.compare_style(
        ctx, ops, scenario_op, changes={"machine_class": "OL-5T-SS"}, step_kind="seam",
        n_workstations=N_WORKSTATIONS, target_rate_per_hour=TARGET_RATE_PER_HOUR,
        labour_rate_per_hour=LABOUR_RATE_PER_HOUR, line_efficiency=LINE_EFFICIENCY)

    print(f"\n--- What-if: '{scenario_op}' machine FOA-401 -> OL-5T-SS ---")
    print(f"Operation SMV: {scenario['operation_delta']['ST_op_delta_min']:+.4f} min "
          f"({scenario['operation_delta']['ST_op_delta_pct']:+.2f}%)")
    print(f"Style SMV: {scenario['base_style_smv_min']:.4f} -> "
          f"{scenario['modified_style_smv_min']:.4f} min "
          f"({scenario['style_smv_delta_min']:+.4f} min, "
          f"{scenario['style_smv_delta_pct']:+.2f}%)")
    print(f"Bottleneck workstation: {scenario['bottleneck_change']['base_bottleneck_workstation']} "
          f"-> {scenario['bottleneck_change']['modified_bottleneck_workstation']} "
          f"({scenario['bottleneck_change']['bottleneck_smv_delta_min']:+.4f} min)")
    print(f"Theoretical efficiency: "
          f"{scenario['efficiency_delta']['base_theoretical_efficiency']*100:.2f}% -> "
          f"{scenario['efficiency_delta']['modified_theoretical_efficiency']*100:.2f}% "
          f"({scenario['efficiency_delta']['delta']*100:+.3f} pp)")
    print(f"Cost per garment: {scenario['costing']['base']['cost_per_garment']:.4f} -> "
          f"{scenario['costing']['modified']['cost_per_garment']:.4f} "
          f"({scenario['cost_delta_per_garment']:+.4f})")

    whatif_rows = [
        {"metric": "operation_ST_delta_min", "value": round(scenario["operation_delta"]["ST_op_delta_min"], 5)},
        {"metric": "operation_ST_delta_pct", "value": round(scenario["operation_delta"]["ST_op_delta_pct"], 3)},
        {"metric": "base_style_smv_min", "value": round(scenario["base_style_smv_min"], 4)},
        {"metric": "modified_style_smv_min", "value": round(scenario["modified_style_smv_min"], 4)},
        {"metric": "style_smv_delta_min", "value": round(scenario["style_smv_delta_min"], 5)},
        {"metric": "style_smv_delta_pct", "value": round(scenario["style_smv_delta_pct"], 3)},
        {"metric": "base_bottleneck_workstation", "value": scenario["bottleneck_change"]["base_bottleneck_workstation"]},
        {"metric": "modified_bottleneck_workstation", "value": scenario["bottleneck_change"]["modified_bottleneck_workstation"]},
        {"metric": "bottleneck_smv_delta_min", "value": round(scenario["bottleneck_change"]["bottleneck_smv_delta_min"], 5)},
        {"metric": "base_theoretical_efficiency", "value": round(scenario["efficiency_delta"]["base_theoretical_efficiency"], 5)},
        {"metric": "modified_theoretical_efficiency", "value": round(scenario["efficiency_delta"]["modified_theoretical_efficiency"], 5)},
        {"metric": "base_cost_per_garment", "value": round(scenario["costing"]["base"]["cost_per_garment"], 4)},
        {"metric": "modified_cost_per_garment", "value": round(scenario["costing"]["modified"]["cost_per_garment"], 4)},
        {"metric": "cost_delta_per_garment", "value": round(scenario["cost_delta_per_garment"], 5)},
    ]
    write_csv("demo_what_if.csv", whatif_rows, ["metric", "value"])

    # ---------------------------------------------------------------- REPORT
    report_lines = [
        f"# Analytics demo -- {VARIANT} shirt, size {SIZE}",
        "",
        f"Style SMV: **{style['SMV_min']:.4f} min** = {style['SMV_tmu']:.1f} TMU, "
        f"across {len(ops)} operations (computed by "
        "`smv_assembly.assemble_style()` via `shirt_library.build_style_operations()` "
        "-- no numbers below are hardcoded; every one is a fresh engine call).",
        "",
        "## 1. Line balance (RPW, chain precedence -- see line_balancing.py docstring)",
        f"- Requested workstations: {N_WORKSTATIONS}; used: {lb_report['n_workstations_used']}",
        f"- Bottleneck: workstation {lb_report['bottleneck_workstation']} "
        f"at {lb_report['bottleneck_smv_min']:.4f} min",
        f"- Theoretical efficiency (sum SMV / (N x bottleneck)): "
        f"{lb_report['theoretical_efficiency']*100:.2f}%",
        f"- Achievable output: {lb_report['achievable_output_per_hour']:.2f} garments/hour "
        f"vs. target {lb_report['target_rate_per_hour']:.1f}/hour "
        f"(meets target: {lb_report['meets_target']}; "
        f"efficiency at target: {lb_report['achievable_efficiency_at_target']*100:.2f}%)",
        f"- Total idle time across stations: {lb_report['total_idle_min']:.4f} min",
        "- Per-workstation detail: see demo_workstation_loads.csv; "
        "operation->workstation assignment: demo_line_balance.csv",
        "",
        "## 2. Costing and production targets",
        f"- Labour rate: {LABOUR_RATE_PER_HOUR:.2f}/hour, line efficiency: {LINE_EFFICIENCY*100:.0f}%",
        f"- Cost of make per garment (SAM x labour_rate/60 / efficiency): "
        f"**{cost_report['cost_per_garment']:.4f}**",
        f"- Output at {N_WORKSTATIONS} operators: "
        f"{cost_report['production_at_n_operators']['output_per_hour']:.2f}/hour, "
        f"{cost_report['production_at_n_operators']['output_per_shift']:.1f} per 8h shift",
        f"- Daily labour cost at {N_WORKSTATIONS} operators: "
        f"{cost_report['daily_labour_cost_at_n_operators']:.2f}",
        f"- Operators required to hit {TARGET_RATE_PER_HOUR:.0f}/hour target: "
        f"**{cost_report['required_operators_for_target']['operators_required']}** "
        f"(raw {cost_report['required_operators_for_target']['operators_required_raw']:.2f})",
        "- Full detail: demo_costing.csv",
        "",
        f"## 3. What-if scenario: '{scenario_op}'",
        "Proposed change: swap the side-seam machine from FOA-401 (feed-off-arm "
        "chainstitch lapseamer) to OL-5T-SS (5-thread safety stitch) -- a real "
        "method-planning decision, recomputed by the engine, not looked up.",
        "",
        f"- Operation SMV: {scenario['operation_delta']['ST_op_delta_min']:+.4f} min "
        f"({scenario['operation_delta']['ST_op_delta_pct']:+.2f}%)",
        f"- Style SMV: {scenario['base_style_smv_min']:.4f} -> "
        f"{scenario['modified_style_smv_min']:.4f} min "
        f"({scenario['style_smv_delta_min']:+.4f} min, {scenario['style_smv_delta_pct']:+.2f}%)",
        f"- Bottleneck workstation: {scenario['bottleneck_change']['base_bottleneck_workstation']} -> "
        f"{scenario['bottleneck_change']['modified_bottleneck_workstation']} "
        f"({scenario['bottleneck_change']['bottleneck_smv_delta_min']:+.4f} min)",
        f"- Theoretical efficiency: "
        f"{scenario['efficiency_delta']['base_theoretical_efficiency']*100:.2f}% -> "
        f"{scenario['efficiency_delta']['modified_theoretical_efficiency']*100:.2f}% "
        f"({scenario['efficiency_delta']['delta']*100:+.3f} pp)",
        f"- Cost per garment: {scenario['costing']['base']['cost_per_garment']:.4f} -> "
        f"{scenario['costing']['modified']['cost_per_garment']:.4f} "
        f"({scenario['cost_delta_per_garment']:+.4f})",
        "- Full detail: demo_what_if.csv",
        "",
    ]
    with open("demo_report.md", "w") as fh:
        fh.write("\n".join(report_lines))

    print("\nWrote: demo_line_balance.csv, demo_workstation_loads.csv, "
          "demo_costing.csv, demo_what_if.csv, demo_report.md")


if __name__ == "__main__":
    main()
