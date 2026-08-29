"""pytest suite for line_balancing.py, exercised against shirt_library's
own CLASSIC/SHORT_SLEEVE/BLOUSE_COLLARLESS variants across all 5 sizes."""
import itertools
import math

import pytest

import line_balancing as lb
import engine_loader as el


# --------------------------------------------------------------------------
# rpw_table
# --------------------------------------------------------------------------

def test_rpw_table_is_suffix_sum_and_descending(classic_m):
    _, style = classic_m
    table = lb.rpw_table(style)
    assert len(table) == len(style["operations"])
    # RPW must be non-increasing along build order (chain-precedence proof
    # in the module docstring: RPW_i = ST_i + RPW_(i+1))
    for a, b in zip(table, table[1:]):
        assert a["rpw_min"] >= b["rpw_min"] - 1e-9
    # last row's rpw == its own st_min; first row's rpw == total SMV
    assert table[-1]["rpw_min"] == pytest.approx(table[-1]["st_min"], rel=1e-9)
    assert table[0]["rpw_min"] == pytest.approx(style["SMV_min"], rel=1e-6)


def test_rpw_table_accepts_raw_op_time_list():
    op_times = [{"name": "a", "st_min": 1.0}, {"name": "b", "st_min": 2.0},
                {"name": "c", "st_min": 3.0}]
    table = lb.rpw_table(op_times)
    assert [r["rpw_min"] for r in table] == pytest.approx([6.0, 5.0, 3.0])


# --------------------------------------------------------------------------
# balance_line: conservation + correctness
# --------------------------------------------------------------------------

def test_balance_line_conserves_total_smv(classic_m):
    _, style = classic_m
    report = lb.balance_line(style, n_workstations=6)
    total_assigned = sum(w["load_min"] for w in report["workstations"])
    assert total_assigned == pytest.approx(style["SMV_min"], rel=1e-9)
    assert set(report["assignment"].keys()) == {o["operation"] for o in style["operations"]}


def test_balance_line_every_operation_assigned_exactly_once(classic_m):
    _, style = classic_m
    report = lb.balance_line(style, n_workstations=8)
    all_assigned = [op for w in report["workstations"] for op in w["operations"]]
    assert len(all_assigned) == len(style["operations"])
    assert len(set(all_assigned)) == len(all_assigned)


def test_balance_line_bottleneck_matches_max_station_load(classic_m):
    """bottleneck_smv_min must be EXACTLY the max realized station load, not
    merely close to it -- balance_line() derives one from the other (see its
    comment on why the two were previously allowed to drift by up to the
    binary search's 1e-7 convergence tolerance)."""
    _, style = classic_m
    report = lb.balance_line(style, n_workstations=5)
    assert report["bottleneck_smv_min"] == max(w["load_min"] for w in report["workstations"])


def test_balance_line_optimal_bottleneck_matches_bruteforce_small_n(classic_m):
    """Verify the binary-search partition against exhaustive search on a
    small prefix of real operation times (full brute force is infeasible
    for 27 ops, so this checks correctness of the underlying algorithm)."""
    _, style = classic_m
    times = [o["ST_op_min"] for o in style["operations"]][:9]
    for k in (2, 3, 4):
        bf = min(
            max(sum(times[b[i]:b[i + 1]]) for i in range(len(b) - 1))
            for b in (
                (0,) + cuts + (len(times),)
                for cuts in itertools.combinations(range(1, len(times)), k - 1)
            )
        )
        bs = lb._min_possible_bottleneck(times, k)
        assert bs == pytest.approx(bf, abs=1e-6)


def test_balance_line_more_stations_never_increases_bottleneck(classic_m):
    _, style = classic_m
    prev = None
    for n in (3, 5, 8, 12, 20):
        report = lb.balance_line(style, n_workstations=n)
        if prev is not None:
            assert report["bottleneck_smv_min"] <= prev + 1e-9
        prev = report["bottleneck_smv_min"]


def test_theoretical_efficiency_formula(classic_m):
    _, style = classic_m
    report = lb.balance_line(style, n_workstations=6)
    expected = style["SMV_min"] / (len(report["workstations"]) * report["bottleneck_smv_min"])
    assert report["theoretical_efficiency"] == pytest.approx(expected, rel=1e-9)
    assert 0 < report["theoretical_efficiency"] <= 1.0


def test_one_workstation_per_operation_is_perfectly_unbalanced_baseline(classic_m):
    _, style = classic_m
    n = len(style["operations"])
    report = lb.balance_line(style, n_workstations=n)
    # with >= n stations, bottleneck == the single longest operation
    assert report["bottleneck_smv_min"] == pytest.approx(
        max(o["ST_op_min"] for o in style["operations"]), rel=1e-9)


# --------------------------------------------------------------------------
# target-rate mode (type-1 balancing)
# --------------------------------------------------------------------------

def test_target_rate_mode_finds_minimum_feasible_stations(classic_m):
    _, style = classic_m
    longest = max(o["ST_op_min"] for o in style["operations"])
    # pick a realistic target rate whose cycle time comfortably exceeds the
    # single longest operation
    target_cycle = longest * 3
    target_rate = 60.0 / target_cycle
    report = lb.balance_line(style, target_rate_per_hour=target_rate)
    assert report["bottleneck_smv_min"] <= target_cycle + 1e-6
    # one fewer station must be infeasible at this cycle time (minimality)
    n = report["n_workstations_used"]
    if n > 1:
        smaller = lb.balance_line(style, n_workstations=n - 1)
        assert smaller["bottleneck_smv_min"] > target_cycle + 1e-9


def test_target_rate_infeasible_below_longest_operation_raises(classic_m):
    _, style = classic_m
    longest = max(o["ST_op_min"] for o in style["operations"])
    absurd_rate = 60.0 / (longest / 2)  # requires a cycle time shorter than one op
    with pytest.raises(ValueError):
        lb.balance_line(style, target_rate_per_hour=absurd_rate)


def test_combined_n_and_target_reports_meets_target_and_efficiency(classic_m):
    _, style = classic_m
    longest = max(o["ST_op_min"] for o in style["operations"])
    generous_rate = 60.0 / (longest * 5)
    report = lb.balance_line(style, n_workstations=10, target_rate_per_hour=generous_rate)
    assert "meets_target" in report
    assert "achievable_efficiency_at_target" in report
    assert 0 <= report["achievable_efficiency_at_target"] <= 1.0


def test_balance_line_requires_n_or_target(classic_m):
    _, style = classic_m
    with pytest.raises(ValueError):
        lb.balance_line(style)


# --------------------------------------------------------------------------
# Cross-variant / cross-size robustness (shirt_library fixtures)
# --------------------------------------------------------------------------

def test_balance_line_runs_for_all_variants_and_sizes(ctx, seam_geom, variant, size):
    ops, style = el.build_and_assemble_style(ctx, seam_geom, size, variant)
    report = lb.balance_line(style, n_workstations=6)
    assert report["n_operations"] == len(ops)
    assert report["total_smv_min"] == pytest.approx(style["SMV_min"], rel=1e-9)
