"""pytest suite for what_if.py, exercised against shirt_library's CLASSIC
shirt (all three scenario kinds: machine swap, cycle-machine swap, handling
-method swap), plus cross-variant/size robustness for the convenience
wrapper."""
import copy

import pytest

import what_if as wi
import line_balancing as lb
import costing as ct


SIDE_SEAM = "side_seam: Close side seam (felled or safety-stitch) (size M)"
FRONT_PLACKET_BUTTONHOLE = "front_placket: Buttonhole, front placket (size M)"
CUFF_TOPSTITCH = "cuff: Topstitch cuff edge (size M)"
COLLAR_RUN = "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)"


# --------------------------------------------------------------------------
# apply_step_change (pure, no engine calls)
# --------------------------------------------------------------------------

def test_apply_step_change_does_not_mutate_original(classic_m):
    ops, _ = classic_m
    idx, op = wi._find_operation(ops, COLLAR_RUN)
    original_machine = [s["machine_class"] for s in op.steps if s["kind"] == "seam"][0]
    modified = wi.apply_step_change(op, {"machine_class": "SNLS-EDGE"}, step_kind="seam")
    assert original_machine == "SNLS-UBT"
    assert [s["machine_class"] for s in op.steps if s["kind"] == "seam"][0] == original_machine
    assert [s["machine_class"] for s in modified.steps if s["kind"] == "seam"][0] == "SNLS-EDGE"


def test_apply_step_change_merges_params_by_default(classic_m):
    ops, _ = classic_m
    _, op = wi._find_operation(ops, COLLAR_RUN)
    hag_before = next(s for s in op.steps if s.get("element") == "HAM")
    modified = wi.apply_step_change(op, {"params": {"distance_cm": 99.0}},
                                     step_kind="handling", element="HAM")
    hag_after = next(s for s in modified.steps if s.get("element") == "HAM")
    assert hag_after["params"]["distance_cm"] == 99.0
    # unrelated params preserved
    for k, v in hag_before["params"].items():
        if k != "distance_cm":
            assert hag_after["params"][k] == v


def test_apply_step_change_replaces_params_on_element_swap(classic_m):
    ops, _ = classic_m
    _, op = wi._find_operation(ops, CUFF_TOPSTITCH)
    modified = wi.apply_step_change(
        op, {"element": "HAM", "params": {"distance_cm": 15.0, "plies": 2,
                                           "match_precision": "P2", "fabric_class": "REF_POPLIN",
                                           "n_match_points": 2, "mass_g": 45.0}},
        step_kind="handling", element="HAG")
    ham_step = next(s for s in modified.steps if s.get("element") == "HAM")
    assert "precision_class" not in ham_step["params"]  # HAG-only param must not leak through


def test_find_operation_exact_and_contains_and_ambiguous(classic_m):
    ops, _ = classic_m
    idx, op = wi._find_operation(ops, COLLAR_RUN, match="exact")
    assert op.name == COLLAR_RUN
    idx2, op2 = wi._find_operation(ops, "Close side seam", match="contains")
    assert op2.name == SIDE_SEAM
    with pytest.raises(ValueError):
        wi._find_operation(ops, "nonexistent operation name", match="exact")
    with pytest.raises(ValueError):
        wi._find_operation(ops, "Buttonhole", match="contains")  # matches 4 operations


# --------------------------------------------------------------------------
# compare_operation / compare_style : the three scenario kinds
# --------------------------------------------------------------------------

def test_seam_machine_swap_recomputes_via_engine_not_lookup(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, SIDE_SEAM, changes={"machine_class": "OL-5T-SS"},
                               step_kind="seam")
    assert result["operation_delta"]["ST_op_delta_min"] != 0.0
    assert result["style_smv_delta_min"] == pytest.approx(
        result["operation_delta"]["ST_op_delta_min"], rel=1e-6)
    assert result["modified_style_smv_min"] == pytest.approx(
        result["base_style_smv_min"] + result["style_smv_delta_min"], rel=1e-9)


def test_cycle_machine_swap(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, FRONT_PLACKET_BUTTONHOLE,
                               changes={"machine_class": "BH-EYE"}, step_kind="cycle")
    # BH-EYE (rated 2200 spm) is slower than BH-LS (rated 4200 spm) -> time increases
    assert result["operation_delta"]["ST_op_delta_min"] > 0


def test_attachment_addition_changes_smv(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, COLLAR_RUN,
                               changes={"attachment": "ATT-EG", "guidance_class": "mechanically_guided"},
                               step_kind="seam")
    assert result["operation_delta"]["ST_op_delta_min"] < 0  # edge guide should reduce guided time


def test_handling_method_swap(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(
        ctx, ops, CUFF_TOPSTITCH,
        changes={"element": "HAM", "params": {"distance_cm": 15.0, "plies": 2,
                                               "match_precision": "P2", "fabric_class": "REF_POPLIN",
                                               "n_match_points": 2, "mass_g": 45.0}},
        step_kind="handling", element="HAG")
    assert result["operation_delta"]["ST_op_delta_min"] != 0.0


def test_no_change_is_a_no_op(ctx, classic_m):
    """Sanity: applying an identical value as the 'change' must leave SMV unchanged."""
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, SIDE_SEAM, changes={"machine_class": "FOA-401"},
                               step_kind="seam")
    assert result["style_smv_delta_min"] == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# line-balance / costing delta propagation
# --------------------------------------------------------------------------

def test_compare_style_includes_line_balance_deltas_when_requested(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, SIDE_SEAM, changes={"machine_class": "OL-5T-SS"},
                               step_kind="seam", n_workstations=8)
    assert "line_balance" in result
    assert "bottleneck_change" in result
    assert "efficiency_delta" in result
    base_lb = lb.balance_line(style, n_workstations=8)
    assert result["line_balance"]["base"]["bottleneck_smv_min"] == pytest.approx(
        base_lb["bottleneck_smv_min"], rel=1e-9)


def test_compare_style_includes_costing_deltas_when_requested(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, SIDE_SEAM, changes={"machine_class": "OL-5T-SS"},
                               step_kind="seam", labour_rate_per_hour=3.0, line_efficiency=0.8)
    assert "costing" in result
    assert "cost_delta_per_garment" in result
    base_cost = ct.cost_per_garment(style, 3.0, 0.8)
    assert result["costing"]["base"]["cost_per_garment"] == pytest.approx(base_cost, rel=1e-9)


def test_compare_style_omits_optional_sections_by_default(ctx, classic_m):
    ops, style = classic_m
    result = wi.compare_style(ctx, ops, SIDE_SEAM, changes={"machine_class": "OL-5T-SS"},
                               step_kind="seam")
    assert "line_balance" not in result
    assert "costing" not in result


# --------------------------------------------------------------------------
# run_shirt_scenario convenience wrapper + cross-variant/size robustness
# --------------------------------------------------------------------------

def test_run_shirt_scenario_matches_manual_compare_style(ctx, seam_geom):
    manual_ops = ctx.sl.build_style_operations(seam_geom, "M", "CLASSIC")
    manual = wi.compare_style(ctx, manual_ops, SIDE_SEAM, changes={"machine_class": "OL-5T-SS"},
                               step_kind="seam")
    via_wrapper = wi.run_shirt_scenario(ctx, seam_geom, "M", SIDE_SEAM,
                                        changes={"machine_class": "OL-5T-SS"}, step_kind="seam")
    assert via_wrapper["style_smv_delta_min"] == pytest.approx(manual["style_smv_delta_min"], rel=1e-9)


def test_run_shirt_scenario_runs_for_all_variants_and_sizes(ctx, seam_geom, variant, size):
    ops = ctx.sl.build_style_operations(seam_geom, size, variant)
    seam_ops = [op for op in ops if any(s["kind"] == "seam" for s in op.steps)]
    assert seam_ops, "expected at least one seam operation in every variant/size"
    target = seam_ops[0]
    original_machine = next(s["machine_class"] for s in target.steps if s["kind"] == "seam")
    alt_machine = "SNLS-EDGE" if original_machine != "SNLS-EDGE" else "SNLS-P"
    result = wi.run_shirt_scenario(ctx, seam_geom, size, target.name,
                                    changes={"machine_class": alt_machine}, step_kind="seam",
                                    variant=variant)
    assert "style_smv_delta_min" in result
