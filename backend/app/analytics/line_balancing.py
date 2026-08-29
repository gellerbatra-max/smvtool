"""
line_balancing.py -- assembly-line balancing for a garment operation
bulletin, using Ranked Positional Weight (RPW).

METHOD (cited, not invented here)
----------------------------------
Ranked Positional Weight is the standard heuristic line-balancing procedure
introduced by Helgeson & Birnie (1961), "Assembly Line Balancing Using the
Ranked Positional Weight Technique", *Journal of Industrial Engineering*
12(6), and taught as the apparel-industrial-engineering-standard method for
progressive-bundle sewing lines (e.g. Groover, *Work Systems and the Methods,
Measurement, and Management of Work*, ch. on line balancing). RPW ranks each
task by its own time plus the time of every task that must follow it
(its "positional weight"), then assigns tasks to workstations in descending
RPW order, packing each station up to a target cycle time before opening the
next one.

PRECEDENCE ASSUMPTION (explicit, load-bearing)
------------------------------------------------
A real assembly-line balancing problem needs a precedence graph (which
operations must finish before which others can start). The engine's
operation bulletins (`shirt_library.build_style_operations()`) do not carry
an explicit precedence graph -- they carry a single ordered list reflecting
the garment's production build sequence (collar before collar-to-body
attach, before topstitch, etc.), which for a single-piece-flow / progressive
-bundle sewing line (the standard apparel line topology) *is* the precedence
constraint: operation i cannot be done before operation i-1 on the same
garment. Under a strictly linear (chain) precedence graph, the RPW of
operation i is

    RPW_i = ST_i + ST_(i+1) + ... + ST_n

which is monotonically non-increasing in i (each successive task drops the
now-completed ST_i from the running sum). RPW-descending order is therefore
*identical* to build-sequence order for a chain -- there is no separate
"RPW table" to compute beyond a suffix sum -- and station assignment reduces
to: walk the bulletin in build order, closing a station and opening the next
whenever the running load would exceed the target cycle time. This module
implements exactly that (see `rpw_table()` for the explicit weights, and
`balance_line()` for the assignment), and states this assumption plainly
rather than fabricating a branching precedence graph the source data does
not support. If/when a real precedence graph (parallel operations, e.g. two
sleeves prepared simultaneously) becomes available, only `rpw_table()`'s
successor-sum needs generalising to a DAG; `balance_line()`'s station-packing
logic is unchanged.

STATION-COUNT / BOTTLENECK TRADE-OFF
--------------------------------------
Given a *fixed* number of workstations N, minimising the bottleneck
(makespan) over CONTIGUOUS build-order groups is the classical "partition
into k contiguous groups minimising the maximum group sum" problem, solved
here by binary search on the candidate bottleneck value plus a greedy
left-to-right feasibility check (`_min_possible_bottleneck`) -- an
established, optimal technique for this exact problem (as used e.g. for
"split array largest sum"), not a heuristic guess. Because precedence is a
chain, only contiguous groupings are feasible, so this binary search finds
the true optimal (minimum-bottleneck) assignment for the requested N, not
merely an approximation.

Public API
----------
    rpw_table(op_times) -> list[dict]                       -- RPW ranking
    balance_line(op_times, n_workstations=None,
                 target_rate_per_hour=None, target_rate_per_day=None,
                 shift_hours=8.0) -> dict                    -- full report
"""
from __future__ import annotations

import math
from typing import Any


# --------------------------------------------------------------------------
# Input normalisation
# --------------------------------------------------------------------------

def _op_times_from_style(style_or_op_times) -> list[dict]:
    """Accept either a raw list of {"name": str, "st_min": float} dicts, or
    an `smv_assembly.assemble_style()` result dict, and return the
    normalised op_times list in build-sequence order."""
    if isinstance(style_or_op_times, dict) and "operations" in style_or_op_times:
        return [{"name": o["operation"], "st_min": o["ST_op_min"]}
                for o in style_or_op_times["operations"]]
    op_times = []
    for o in style_or_op_times:
        if "st_min" in o:
            op_times.append({"name": o["name"], "st_min": float(o["st_min"])})
        else:  # tolerate an assemble_operation()-shaped record
            op_times.append({"name": o.get("name", o.get("operation")),
                              "st_min": float(o["ST_op_min"])})
    return op_times


# --------------------------------------------------------------------------
# RPW ranking (chain precedence -> suffix sum, see module docstring)
# --------------------------------------------------------------------------

def rpw_table(style_or_op_times) -> list[dict]:
    """Ranked Positional Weight table for a build-ordered operation list.

    Returns one row per operation, in RPW-descending order (== build order,
    for the chain-precedence assumption stated in the module docstring):
    `{"name", "st_min", "sequence_index", "rpw_min"}`.
    """
    op_times = _op_times_from_style(style_or_op_times)
    n = len(op_times)
    suffix = [0.0] * n
    running = 0.0
    for i in range(n - 1, -1, -1):
        running += op_times[i]["st_min"]
        suffix[i] = running
    return [
        {"name": op_times[i]["name"], "st_min": op_times[i]["st_min"],
         "sequence_index": i, "rpw_min": suffix[i]}
        for i in range(n)
    ]


# --------------------------------------------------------------------------
# Contiguous min-bottleneck partition for a fixed station count
# --------------------------------------------------------------------------

def _groups_needed(times: list[float], cap: float) -> int:
    """Greedy left-to-right count of contiguous groups needed so that no
    group's sum exceeds `cap` (feasibility check for the binary search)."""
    groups = 1
    load = 0.0
    for t in times:
        if load + t > cap + 1e-9 and load > 0:
            groups += 1
            load = t
        else:
            load += t
    return groups


def _min_possible_bottleneck(times: list[float], n_workstations: int) -> float:
    """Minimum achievable max-group-sum when splitting `times` (in order)
    into at most `n_workstations` contiguous groups. Binary search on the
    answer over [max(single task), total sum]."""
    lo = max(times) if times else 0.0
    hi = sum(times)
    if n_workstations >= len(times):
        return lo  # one task per station is always feasible
    while hi - lo > 1e-7:
        mid = (lo + hi) / 2.0
        if _groups_needed(times, mid) <= n_workstations:
            hi = mid
        else:
            lo = mid
    return hi


def _partition_at_cap(op_times: list[dict], cap: float) -> list[list[dict]]:
    """Construct the actual contiguous grouping for a feasible cap value."""
    groups: list[list[dict]] = [[]]
    load = 0.0
    for op in op_times:
        t = op["st_min"]
        if load + t > cap + 1e-9 and load > 0:
            groups.append([])
            load = 0.0
        groups[-1].append(op)
        load += t
    return groups


def _min_workstations_for_cycle_time(op_times: list[dict], cycle_time_min: float) -> int:
    """Minimum number of stations needed so no station's load exceeds
    `cycle_time_min` (classical RPW type-1 balancing: cycle time given,
    minimise stations). Raises if a single task already exceeds the cycle
    time (physically infeasible without splitting that task)."""
    times = [o["st_min"] for o in op_times]
    longest = max(times) if times else 0.0
    if longest > cycle_time_min + 1e-9:
        raise ValueError(
            f"target cycle time {cycle_time_min:.4f} min is shorter than the "
            f"longest single operation ({longest:.4f} min) -- infeasible "
            "without splitting that operation across stations/operators.")
    return _groups_needed(times, cycle_time_min)


# --------------------------------------------------------------------------
# Public: full line-balance report
# --------------------------------------------------------------------------

def balance_line(style_or_op_times, n_workstations: "int | None" = None,
                  target_rate_per_hour: "float | None" = None,
                  target_rate_per_day: "float | None" = None,
                  shift_hours: float = 8.0) -> dict:
    """Assign a build-ordered operation bulletin to workstations by RPW
    (see module docstring for the chain-precedence assumption and the
    binary-search partitioning method) and report the resulting balance.

    Parameters
    ----------
    style_or_op_times : the dict returned by `smv_assembly.assemble_style()`
        / `shirt_library.style_smv()`, OR a plain list of
        `{"name": str, "st_min": float}` dicts in build-sequence order.
    n_workstations : if given, operations are packed into exactly this many
        contiguous stations, minimising the bottleneck (line-balancing
        "type 2": fixed headcount, minimise cycle time).
    target_rate_per_hour / target_rate_per_day : if `n_workstations` is NOT
        given, the minimum number of stations needed to hit this output
        rate is computed instead (line-balancing "type 1": fixed cycle
        time, minimise headcount). `target_rate_per_day` is converted via
        `shift_hours`. If `n_workstations` IS also given, the target rate is
        only used to report `achievable_efficiency_at_target` (whether the
        requested headcount can actually reach the requested rate).

    Returns
    -------
    dict with: `assignment` (operation -> workstation index), `workstations`
    (per-station op list + load), `bottleneck_workstation`,
    `bottleneck_smv_min`, `n_workstations_used`, `total_smv_min`,
    `theoretical_efficiency` (= total_smv / (n_workstations * bottleneck),
    the standard line-balance-efficiency identity), `total_idle_min`,
    `achievable_output_per_hour` (= 60 / bottleneck_smv_min), and, if a
    target rate was supplied, `achievable_efficiency_at_target` (achievable
    rate / target rate, capped at 1.0) plus `meets_target`.
    """
    op_times = _op_times_from_style(style_or_op_times)
    if not op_times:
        raise ValueError("no operations to balance")
    total_smv = sum(o["st_min"] for o in op_times)
    times = [o["st_min"] for o in op_times]

    target_cycle_time_min = None
    if target_rate_per_hour is not None:
        target_cycle_time_min = 60.0 / target_rate_per_hour
    elif target_rate_per_day is not None:
        target_cycle_time_min = (60.0 * shift_hours) / target_rate_per_day

    if n_workstations is None:
        if target_cycle_time_min is None:
            raise ValueError("must supply either n_workstations or a target rate "
                              "(target_rate_per_hour / target_rate_per_day)")
        n_workstations = _min_workstations_for_cycle_time(op_times, target_cycle_time_min)
        bottleneck = _min_possible_bottleneck(times, n_workstations)
    else:
        bottleneck = _min_possible_bottleneck(times, n_workstations)

    groups = _partition_at_cap(op_times, bottleneck)
    # binary search can return a bottleneck value that yields fewer groups
    # than n_workstations were requested (excess capacity headroom) -- pad
    # with empty trailing stations so the report reflects the paid headcount.
    while len(groups) < n_workstations:
        groups.append([])

    workstations = []
    assignment = {}
    for idx, grp in enumerate(groups, start=1):
        load = sum(op["st_min"] for op in grp)
        for op in grp:
            assignment[op["name"]] = idx
        workstations.append({
            "workstation": idx,
            "operations": [op["name"] for op in grp],
            "load_min": load,
            "idle_min": bottleneck - load,
        })

    n_used = sum(1 for w in workstations if w["operations"])
    bottleneck_ws = max(workstations, key=lambda w: w["load_min"])
    # Report the ACTUAL realized max station load, not the raw binary-search
    # cap (`bottleneck`) used to build the partition: _min_possible_bottleneck
    # converges to within a 1e-7 tolerance and _partition_at_cap's greedy
    # packing can realize a max load a hair below that cap, so the two values
    # are not guaranteed bit-identical. Using the actual max load here makes
    # `bottleneck_smv_min`, `theoretical_efficiency`, and
    # `achievable_output_per_hour` self-consistent by construction (every
    # idle_min above is already computed against this same value, since
    # idle_min was computed against `bottleneck` -- recomputed below too).
    bottleneck = bottleneck_ws["load_min"]
    for w in workstations:
        w["idle_min"] = bottleneck - w["load_min"]
    total_idle = sum(w["idle_min"] for w in workstations)
    theoretical_efficiency = total_smv / (len(workstations) * bottleneck) if bottleneck > 0 else 0.0
    achievable_output_per_hour = 60.0 / bottleneck if bottleneck > 0 else float("inf")

    report = {
        "method": "RPW (Ranked Positional Weight, Helgeson & Birnie 1961) "
                  "under chain (build-sequence) precedence",
        "n_operations": len(op_times),
        "total_smv_min": total_smv,
        "n_workstations_requested": n_workstations,
        "n_workstations_used": n_used,
        "assignment": assignment,
        "workstations": workstations,
        "bottleneck_workstation": bottleneck_ws["workstation"],
        "bottleneck_smv_min": bottleneck,
        "theoretical_efficiency": theoretical_efficiency,
        "total_idle_min": total_idle,
        "achievable_output_per_hour": achievable_output_per_hour,
        "achievable_output_per_shift": achievable_output_per_hour * shift_hours,
    }

    if target_cycle_time_min is not None:
        target_rate_per_hour_eff = (target_rate_per_hour if target_rate_per_hour is not None
                                     else target_rate_per_day / shift_hours)
        eff_at_target = min(achievable_output_per_hour / target_rate_per_hour_eff, 1.0)
        report["target_rate_per_hour"] = target_rate_per_hour_eff
        report["target_cycle_time_min"] = target_cycle_time_min
        report["achievable_efficiency_at_target"] = eff_at_target
        report["meets_target"] = achievable_output_per_hour >= target_rate_per_hour_eff - 1e-9

    return report
