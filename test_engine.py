"""
test_engine.py -- pytest suite for the Phase-1 calculation engine
(handling_time.py, machine_time.py, allowance.py, smv_assembly.py).

Run with: pytest test_engine.py -v
"""
from __future__ import annotations

import math
import json

import pytest

import handling_time as ht
import machine_time as mt
import allowance as al
import smv_assembly as sa


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tax():
    return ht.load_taxonomy("element_taxonomy.json")


@pytest.fixture(scope="module")
def mcat():
    return mt.load_machine_catalog("machine_classes.csv")


@pytest.fixture(scope="module")
def pol():
    return al.load_allowance_policy("allowance_policy.json")


# --------------------------------------------------------------------------
# handling_time.py
# --------------------------------------------------------------------------

class TestHandlingTime:
    def test_all_elements_compute_without_error(self, tax):
        errors = []
        for code in tax.list_elements():
            try:
                tax.compute_element(code)
            except Exception as exc:
                errors.append((code, exc))
        assert not errors, f"elements failed to compute: {errors}"

    def test_hag_matches_hand_derivation(self, tax):
        """Independent hand-derivation of a simple point-grasp-point element."""
        r = tax.compute_element("HAG", distance_cm=25.0, precision_class="P1",
                                 fabric_class="REF_POPLIN", mass_g=60.0)
        el = tax.elements["HAG"]
        phases = el["phase_program"]
        ns = tax._eval_namespace(el, {"distance_cm": 25.0, "precision_class": "P1",
                                       "fabric_class": "REF_POPLIN", "mass_g": 60.0,
                                       **{p["name"]: p["default"] for p in el["parameters"]
                                          if p["name"] not in ("distance_cm", "precision_class",
                                                                "fabric_class", "mass_g")}})
        expected_total = 0.0
        for ph in phases:
            fn = tax._PHASE_FN[ph["type"]]
            expected_total += fn(tax, ph, ns)["t_s"]
        expected_basic = expected_total * tax.globals["Gamma_skill"]
        assert r["t_basic_s"] == pytest.approx(expected_basic, rel=1e-9)

    def test_fabric_difficulty_rectification(self, tax):
        """A fabric that is stiffer/grippier but bulkier than reference must not
        compute as FASTER than reference -- only pay the bulk penalty."""
        phi_ref = tax.PHI("point", "REF_POPLIN")
        # a hypothetical case: use an existing bulky-but-not-uniformly-worse class
        classes = [r["code"] for r in tax.class_tables["fabric_class"]["values"]]
        for code in classes:
            if code == "REF_POPLIN":
                continue
            phi = tax.PHI("point", code)
            assert phi["value"] >= tax.globals["Phi_min"], f"{code}: PHI below floor"
            # rectification: no descriptor term may be negative pre-clamp contribution
            assert phi["z_limp"] >= 0 and phi["z_slip"] >= 0 and phi["z_bulk"] >= 0

    def test_phi_clamps_at_ceiling(self, tax):
        tax2 = ht.load_taxonomy("element_taxonomy.json")
        tax2.class_tables["fabric_class"]["values"].append({
            "code": "TEST_EXTREME_UNIT", "name": "test", "B_uNm": 0.001, "MIU": 0.001, "t_mm": 50.0,
        })
        phi = tax2.PHI("point", "TEST_EXTREME_UNIT")
        assert phi["clamped"] is True
        assert phi["value"] == tax2.globals["Phi_max"]

    def test_bimanual_coupling_penalty_formula(self, tax):
        """HAM ('sum_then_bimanual'): the three simultaneous two-hand phases
        (reach, acquire, bring_to_work_point) are summed and then scaled by
        (1 + epsilon_bi) as a coordination-overhead penalty -- NOT reduced by
        parallel-hands savings -- and the sequential registration phase is
        added once, unscaled."""
        r = tax.compute_element("HAM", distance_cm=25.0, plies=2, match_precision="P2",
                                 fabric_class="REF_POPLIN")
        eps = tax.globals["epsilon_bi"]
        simultaneous_sum = sum(p["t_s"] for p in r["phases"][:3])
        sequential_sum = sum(p["t_s"] for p in r["phases"][3:])
        predicted = simultaneous_sum * (1 + eps) + sequential_sum
        assert r["combined_s"] == pytest.approx(predicted, rel=1e-9)
        assert r["combined_s"] > simultaneous_sum + sequential_sum  # penalty, not a discount
        assert r["limiting_hand"] is not None

    def test_reach_distance_monotonic(self, tax):
        times = [tax.compute_element("HAG", distance_cm=d, precision_class="P2")["t_basic_s"]
                 for d in (10, 20, 40, 80)]
        assert all(a < b for a, b in zip(times, times[1:]))

    def test_unknown_element_raises(self, tax):
        with pytest.raises(KeyError):
            tax.compute_element("NOPE")

    def test_out_of_domain_param_raises(self, tax):
        # HGD.tolerance_mm domain is [0.3, 20.0] mm
        with pytest.raises(ValueError):
            tax.compute_element("HGD", tolerance_mm=100.0)

    def test_unknown_param_raises(self, tax):
        with pytest.raises(ValueError):
            tax.compute_element("HAG", not_a_real_param=1.0)


# --------------------------------------------------------------------------
# machine_time.py
# --------------------------------------------------------------------------

class TestMachineTime:
    def test_catalog_loads(self, mcat):
        assert len(mcat.machines) > 0
        assert len(mcat.attachments) > 0

    def test_unknown_machine_raises(self, mcat):
        with pytest.raises(KeyError):
            mcat.get("NOPE")

    def test_attachment_used_as_machine_raises(self, mcat):
        att = next(iter(mcat.attachments))
        with pytest.raises(ValueError):
            mt.time_seam(mcat, att, path_length_mm=100, spi=12)

    def test_pivots_exceeding_segments_raises(self, mcat):
        machine = next(iter(mcat.machines))
        with pytest.raises(ValueError):
            mt.time_seam(mcat, machine, path_length_mm=[100, 100], spi=12,
                          curvature_class=["straight", "straight"], pivots=5)

    def test_long_seam_approaches_derated_cap(self, mcat):
        """achieved_avg_spm_sewing -> rated * eta_set * ply_derate as seam length -> inf."""
        r = mt.time_seam(mcat, "OL-3T", path_length_mm=20000, spi=8,
                          curvature_class="straight", guidance_class="mechanically_guided", plies=2)
        p = mt.es.MotionParams()
        theoretical_cap = 7000 * p.eta_set  # OL-3T rated 7000, plies=2 so no ply derate
        assert r["achieved_avg_spm_sewing"] / theoretical_cap > 0.97

    def test_pure_machine_time_no_greater_than_blended_when_guidance_binds(self, mcat):
        pure = mt.pure_machine_time_seam(mcat, "SNLS-TOP", path_length_mm=445.7, spi=14,
                                          plies=3, pivots=2)
        blended = mt.time_seam(mcat, "SNLS-TOP", path_length_mm=445.7, spi=14,
                                curvature_class="moderate", plies=3, pivots=2,
                                guidance_class="edgestitch_critical")
        assert pure["total_time_s"] < blended["total_time_s"]

    def test_pure_machine_time_equals_blended_when_machine_binds(self, mcat):
        pure = mt.pure_machine_time_seam(mcat, "SNLS-UBT", path_length_mm=445.7, spi=14,
                                          plies=2, pivots=2)
        blended = mt.time_seam(mcat, "SNLS-UBT", path_length_mm=445.7, spi=14,
                                curvature_class="moderate", plies=2, pivots=2)
        assert pure["total_time_s"] == pytest.approx(blended["total_time_s"], rel=1e-9)

    def test_cycle_time_no_guidance_term(self, mcat):
        r = mt.time_cycle(mcat, "BH-LS", stitches=88)
        assert r["status"].startswith("ASSUMPTION")
        assert r["total_time_s"] > 0


# --------------------------------------------------------------------------
# allowance.py
# --------------------------------------------------------------------------

class TestAllowance:
    def test_policy_loads(self, pol):
        assert len(pol.categories) == 12
        assert len(pol.profiles) == 3

    def test_machine_delay_never_applied_to_handling(self, pol):
        r = pol.resolve_element_allowance("HAM", "MANUAL_HANDLING", {"params": {}})
        codes = [c["code"] for c in r["categories"]]
        assert "MACHINE_DELAY" not in codes

    def test_machine_delay_applied_to_machine_station(self, pol):
        r = pol.resolve_element_allowance("MACHINE_TIME", "MACHINE_STATION", {"params": {}})
        codes = [c["code"] for c in r["categories"]]
        assert "MACHINE_DELAY" in codes

    def test_force_weight_scales_with_mass(self, pol):
        light = pol.resolve_element_allowance("HBM", "BUNDLE", {"params": {"mass_kg": 0.5}})
        heavy = pol.resolve_element_allowance("HBM", "BUNDLE", {"params": {"mass_kg": 5.0}})
        pct_light = next(c["percent"] for c in light["categories"] if c["code"] == "FORCE_WEIGHT")
        pct_heavy = next(c["percent"] for c in heavy["categories"] if c["code"] == "FORCE_WEIGHT")
        assert pct_heavy > pct_light

    def test_close_attention_precision_class_mapping(self, pol):
        result = {}
        for pc, expected in [("P0", 0.0), ("P1", 0.0), ("P2", 1.0), ("P3", 2.0), ("P4", 4.0)]:
            r = pol.resolve_element_allowance("HPF", "MACHINE_STATION", {"params": {"precision_class": pc}})
            pct = next((c["percent"] for c in r["categories"] if c["code"] == "CLOSE_ATTENTION"), 0.0)
            assert pct == expected, f"{pc}: expected {expected}, got {pct}"

    def test_close_attention_hgd_tolerance_mapping(self, pol):
        cases = [(5.0, 0.0), (3.0, 1.0), (1.5, 2.0), (0.5, 4.0)]
        for tol, expected in cases:
            r = pol.resolve_element_allowance("HGD", "MACHINE_STATION", {"params": {"tolerance_mm": tol}})
            pct = next((c["percent"] for c in r["categories"] if c["code"] == "CLOSE_ATTENTION"), 0.0)
            assert pct == expected, f"tol={tol}: expected {expected}, got {pct}"

    def test_awkward_position_requires_trunk_lean(self, pol):
        no_lean = {"params": {}, "phases": [{"lean_term_s": 0.0}]}
        with_lean = {"params": {}, "phases": [{"lean_term_s": 0.3}]}
        r1 = pol.resolve_element_allowance("HAG", "MANUAL_HANDLING", no_lean)
        r2 = pol.resolve_element_allowance("HAG", "MANUAL_HANDLING", with_lean)
        c1 = [c["code"] for c in r1["categories"]]
        c2 = [c["code"] for c in r2["categories"]]
        assert "AWKWARD_POSITION" not in c1
        assert "AWKWARD_POSITION" in c2

    def test_cap_exceeded_raises(self, pol, tmp_path):
        raw = json.loads(json.dumps(pol.raw))  # deep copy via round-trip
        raw["profiles"][0]["values_percent"]["PERSONAL"] = 50.0
        bad = al.AllowancePolicy(raw)
        with pytest.raises(al.AllowanceError):
            bad.resolve_element_allowance("HAG", "MANUAL_HANDLING", {"params": {}})

    def test_conventional_profile_guarded(self, pol):
        with pytest.raises(al.AllowanceError):
            pol.resolve_element_allowance("HAG", "MANUAL_HANDLING", {"params": {}},
                                           profile_code="APPAREL_CONVENTIONAL")

    def test_decomposed_reconciles_with_conventional_within_policy_tolerance(self, pol):
        """validation.self_test: decomposed vs conventional must land within a
        few percentage points on a reference (non-parametric, no-lean) op."""
        dec = pol.resolve_element_allowance("HAG", "MANUAL_HANDLING", {"params": {}})
        conv = pol.resolve_element_allowance_conventional("MANUAL_HANDLING")
        assert abs(dec["total_percent"] - conv["total_percent"]) <= 8.0


# --------------------------------------------------------------------------
# smv_assembly.py
# --------------------------------------------------------------------------

class TestSMVAssembly:
    def test_operation_assembles(self, tax, mcat, pol):
        op = sa.Operation(name="test", steps=[
            {"kind": "handling", "element": "HAG", "params": {"distance_cm": 25}},
        ])
        r = sa.assemble_operation(tax, mcat, pol, op)
        assert r["ST_op_s"] > r["BT_op_s"] > 0

    def test_seam_step_picks_correct_binding(self, tax, mcat, pol):
        op = sa.Operation(name="test", steps=[
            {"kind": "seam", "machine_class": "SNLS-TOP", "path_length_mm": 445.7, "spi": 14,
             "curvature_class": "moderate", "guidance_class": "edgestitch_critical", "plies": 3, "pivots": 2},
        ])
        r = sa.assemble_operation(tax, mcat, pol, op)
        assert r["steps"][0]["binding"] == "guide"

    def test_bundle_amortisation(self, tax, mcat, pol):
        op = sa.Operation(name="test", bundle_size=25, steps=[
            {"kind": "bundle", "element": "HBO", "params": {"mass_kg": 3.0}},
        ])
        r = sa.assemble_operation(tax, mcat, pol, op)
        step = r["steps"][0]
        assert step["t_basic_s"] == pytest.approx(step["t_basic_full_s"] / 25, rel=1e-9)

    def test_double_count_detected(self, tax, mcat, pol):
        op = sa.Operation(name="test", steps=[
            {"kind": "handling", "element": "HDS", "params": {"distance_cm": 30}},
            {"kind": "handling", "element": "HAG", "params": {"distance_cm": 90}},
        ])
        r = sa.assemble_operation(tax, mcat, pol, op)
        assert len(r["no_double_count_warnings"]) == 1

    def test_no_false_positive_double_count(self, tax, mcat, pol):
        op = sa.Operation(name="test", steps=[
            {"kind": "handling", "element": "HDS", "params": {"distance_cm": 90}},
            {"kind": "handling", "element": "HAG", "params": {"distance_cm": 30}},
        ])
        r = sa.assemble_operation(tax, mcat, pol, op)
        assert len(r["no_double_count_warnings"]) == 0

    def test_style_smv_sums_operations(self, tax, mcat, pol):
        ops = [
            sa.Operation(name="a", steps=[{"kind": "handling", "element": "HAG", "params": {}}]),
            sa.Operation(name="b", steps=[{"kind": "handling", "element": "HDS", "params": {}}]),
        ]
        style = sa.assemble_style(tax, mcat, pol, ops)
        assert style["ST_style_min"] == pytest.approx(
            sum(o["ST_op_min"] for o in style["operations"]), rel=1e-9)
        assert style["SMV_tmu"] == pytest.approx(style["SMV_min"] * sa.TMU_PER_MINUTE, rel=1e-9)

    def test_count_multiplies_step_time(self, tax, mcat, pol):
        op1 = sa.Operation(name="a", steps=[{"kind": "handling", "element": "HAG", "params": {}, "count": 1}])
        op2 = sa.Operation(name="a", steps=[{"kind": "handling", "element": "HAG", "params": {}, "count": 2}])
        r1 = sa.assemble_operation(tax, mcat, pol, op1)
        r2 = sa.assemble_operation(tax, mcat, pol, op2)
        assert r2["BT_op_s"] == pytest.approx(2 * r1["BT_op_s"], rel=1e-9)

    def test_unknown_step_kind_raises(self, tax, mcat, pol):
        op = sa.Operation(name="a", steps=[{"kind": "nope"}])
        with pytest.raises(ValueError):
            sa.assemble_operation(tax, mcat, pol, op)
