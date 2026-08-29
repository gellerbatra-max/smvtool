"""pytest suite for costing.py, exercised against shirt_library fixtures."""
import math

import pytest

import costing as ct
import engine_loader as el


# --------------------------------------------------------------------------
# cost_per_garment
# --------------------------------------------------------------------------

def test_cost_per_garment_matches_formula(classic_m):
    _, style = classic_m
    cost = ct.cost_per_garment(style, labour_rate_per_hour=4.0, efficiency=0.8)
    expected = style["SMV_min"] * (4.0 / 60.0) / 0.8
    assert cost == pytest.approx(expected, rel=1e-9)


def test_cost_per_garment_accepts_raw_smv():
    cost = ct.cost_per_garment(10.0, labour_rate_per_hour=6.0, efficiency=1.0)
    assert cost == pytest.approx(10.0 * (6.0 / 60.0))


def test_cost_per_garment_decreases_with_efficiency():
    lo_eff = ct.cost_per_garment(10.0, 6.0, efficiency=0.5)
    hi_eff = ct.cost_per_garment(10.0, 6.0, efficiency=1.0)
    assert hi_eff < lo_eff


@pytest.mark.parametrize("bad_eff", [0, -0.1, 1.5])
def test_cost_per_garment_rejects_invalid_efficiency(bad_eff):
    with pytest.raises(ValueError):
        ct.cost_per_garment(10.0, 6.0, efficiency=bad_eff)


# --------------------------------------------------------------------------
# production_rate
# --------------------------------------------------------------------------

def test_production_rate_matches_formula(classic_m):
    _, style = classic_m
    rate = ct.production_rate(n_operators=20, style_or_smv_min=style, efficiency=0.85,
                               shift_hours=9.0)
    expected_per_hour = (20 * 60.0 * 0.85) / style["SMV_min"]
    assert rate["output_per_hour"] == pytest.approx(expected_per_hour, rel=1e-9)
    assert rate["output_per_shift"] == pytest.approx(expected_per_hour * 9.0, rel=1e-9)


# --------------------------------------------------------------------------
# required_operators : algebraic inverse of production_rate
# --------------------------------------------------------------------------

def test_required_operators_is_inverse_of_production_rate(classic_m):
    _, style = classic_m
    n = 15.0
    eff = 0.78
    rate = ct.production_rate(n, style, eff)
    back = ct.required_operators(rate["output_per_hour"], style, eff)
    assert back["operators_required_raw"] == pytest.approx(n, rel=1e-6)


def test_required_operators_ceils_to_staffable_headcount(classic_m):
    _, style = classic_m
    req = ct.required_operators(target_output_per_hour=50, style_or_smv_min=style, efficiency=0.8)
    assert req["operators_required"] == math.ceil(req["operators_required_raw"] - 1e-9)
    assert req["operators_required"] >= req["operators_required_raw"]


# --------------------------------------------------------------------------
# full_costing_report
# --------------------------------------------------------------------------

def test_full_costing_report_all_sections_present_and_consistent(classic_m):
    _, style = classic_m
    report = ct.full_costing_report(style, labour_rate_per_hour=3.5, efficiency=0.82,
                                     n_operators=25, target_output_per_hour=60)
    assert report["cost_per_garment"] == pytest.approx(
        ct.cost_per_garment(style, 3.5, 0.82), rel=1e-9)
    assert report["production_at_n_operators"]["n_operators"] == 25
    assert report["required_operators_for_target"]["target_output_per_hour"] == 60
    assert report["daily_labour_cost_at_n_operators"] == pytest.approx(25 * 3.5 * 8.0)


def test_full_costing_report_target_per_day_converts_via_shift_hours(classic_m):
    _, style = classic_m
    report = ct.full_costing_report(style, labour_rate_per_hour=3.0, efficiency=0.8,
                                     target_output_per_day=400, shift_hours=10.0)
    assert report["target_output_per_hour"] == pytest.approx(40.0)


def test_full_costing_report_omits_optional_sections_when_not_requested(classic_m):
    _, style = classic_m
    report = ct.full_costing_report(style, labour_rate_per_hour=3.0, efficiency=0.8)
    assert "production_at_n_operators" not in report
    assert "required_operators_for_target" not in report
    assert "cost_per_garment" in report


# --------------------------------------------------------------------------
# Cross-variant / cross-size robustness
# --------------------------------------------------------------------------

def test_costing_runs_for_all_variants_and_sizes(ctx, seam_geom, variant, size):
    _, style = el.build_and_assemble_style(ctx, seam_geom, size, variant)
    report = ct.full_costing_report(style, labour_rate_per_hour=3.0, efficiency=0.8,
                                     n_operators=20, target_output_per_hour=40)
    assert report["cost_per_garment"] > 0
    assert report["production_at_n_operators"]["output_per_hour"] > 0
