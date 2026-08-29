"""
costing.py -- apparel costing and production-target calculation from a
computed style SMV.

FORMULAS (standard apparel-industrial-engineering identities, cited plainly
-- nothing here is fitted or hidden behind an unexplained coefficient)
--------------------------------------------------------------------------
1. Cost of make (CM) per garment:

       CM = SAM x (labour_rate_per_hour / 60) / efficiency

   SAM ("Standard Allowed Minutes", = SMV = the engine's `ST_style_min`) is
   the paid time per garment at 100% efficiency; dividing by the line's
   actual efficiency inflates that to the REAL paid minutes consumed per
   garment once idle time/imbalance/stoppages are accounted for. This is
   the textbook apparel costing identity (e.g. Kunz & Glock,
   *Apparel Manufacturing*; any standard apparel-costing/IE reference) --
   `cost_per_garment()` implements it directly and nothing else.

2. Production capacity (pieces per hour) for a line of N operators running
   at a given efficiency on a style of the given SAM:

       output_per_hour = (N x 60 x efficiency) / SAM

   This is the standard line-capacity identity: total paid operator-minutes
   available per hour (N x 60) x how much of that is actually productive
   (efficiency), divided by how many minutes one garment consumes (SAM).
   It is independent of the specific line-balance assignment (that's
   `line_balancing.py`'s job); it is the standard target-setting formula
   used for costing/planning purposes.

3. Required headcount to hit a target output rate at a given efficiency
   (the algebraic inverse of #2):

       operators_required = (target_output_per_hour x SAM) / (60 x efficiency)

Public API
----------
    cost_per_garment(smv_min, labour_rate_per_hour, efficiency) -> float
    production_rate(n_operators, smv_min, efficiency, shift_hours=8.0) -> dict
    required_operators(target_output_per_hour, smv_min, efficiency) -> dict
    full_costing_report(smv_min, labour_rate_per_hour, efficiency, ...) -> dict
"""
from __future__ import annotations

import math


def _smv_from(style_or_smv_min) -> float:
    """Accept either a raw SMV in minutes, or an
    `smv_assembly.assemble_style()` result dict."""
    if isinstance(style_or_smv_min, dict):
        return float(style_or_smv_min["SMV_min"])
    return float(style_or_smv_min)


def cost_per_garment(style_or_smv_min, labour_rate_per_hour: float,
                      efficiency: float) -> float:
    """Cost of make per garment = SAM x (labour_rate/60) / efficiency.

    `efficiency` is a fraction in (0, 1] (e.g. 0.85 for 85% line efficiency).
    """
    if not (0 < efficiency <= 1.0):
        raise ValueError(f"efficiency must be in (0, 1], got {efficiency!r}")
    smv_min = _smv_from(style_or_smv_min)
    labour_rate_per_min = labour_rate_per_hour / 60.0
    return smv_min * labour_rate_per_min / efficiency


def production_rate(n_operators: float, style_or_smv_min, efficiency: float,
                     shift_hours: float = 8.0) -> dict:
    """Achievable output at a given headcount/efficiency:
    output_per_hour = (n_operators x 60 x efficiency) / SAM."""
    if not (0 < efficiency <= 1.0):
        raise ValueError(f"efficiency must be in (0, 1], got {efficiency!r}")
    smv_min = _smv_from(style_or_smv_min)
    per_hour = (n_operators * 60.0 * efficiency) / smv_min
    return {
        "smv_min": smv_min,
        "n_operators": n_operators,
        "efficiency": efficiency,
        "output_per_hour": per_hour,
        "output_per_shift": per_hour * shift_hours,
        "output_per_day": per_hour * shift_hours,
    }


def required_operators(target_output_per_hour: float, style_or_smv_min,
                        efficiency: float) -> dict:
    """Headcount needed to hit `target_output_per_hour` at `efficiency`:
    operators_required = (target_output_per_hour x SAM) / (60 x efficiency).
    Returns both the raw (fractional) and ceil'd (actually staffable)
    headcount."""
    if not (0 < efficiency <= 1.0):
        raise ValueError(f"efficiency must be in (0, 1], got {efficiency!r}")
    smv_min = _smv_from(style_or_smv_min)
    raw = (target_output_per_hour * smv_min) / (60.0 * efficiency)
    return {
        "smv_min": smv_min,
        "target_output_per_hour": target_output_per_hour,
        "efficiency": efficiency,
        "operators_required_raw": raw,
        "operators_required": math.ceil(raw - 1e-9),
    }


def full_costing_report(style_or_smv_min, labour_rate_per_hour: float,
                         efficiency: float, n_operators: "float | None" = None,
                         target_output_per_hour: "float | None" = None,
                         target_output_per_day: "float | None" = None,
                         shift_hours: float = 8.0) -> dict:
    """One-call costing report combining cost-of-make, achievable
    production (if `n_operators` given) and required headcount (if a
    target output rate is given). All three use the same `smv_min` and
    `efficiency` so the numbers are mutually consistent.

    Parameters
    ----------
    style_or_smv_min : an `assemble_style()`/`style_smv()` result dict, or a
        raw SMV in minutes.
    labour_rate_per_hour : currency per operator-hour (any currency; the
        caller's unit passes straight through, unconverted).
    efficiency : fraction in (0, 1], the line's assumed/measured efficiency.
    n_operators : if given, also reports achievable output at that headcount.
    target_output_per_hour / target_output_per_day : if given (per_day is
        converted via `shift_hours`), also reports the headcount required to
        hit that rate.
    """
    smv_min = _smv_from(style_or_smv_min)
    report = {
        "smv_min": smv_min,
        "labour_rate_per_hour": labour_rate_per_hour,
        "efficiency": efficiency,
        "cost_per_garment": cost_per_garment(smv_min, labour_rate_per_hour, efficiency),
    }
    if n_operators is not None:
        report["production_at_n_operators"] = production_rate(
            n_operators, smv_min, efficiency, shift_hours)
        report["daily_labour_cost_at_n_operators"] = n_operators * labour_rate_per_hour * shift_hours

    target_per_hour = target_output_per_hour
    if target_per_hour is None and target_output_per_day is not None:
        target_per_hour = target_output_per_day / shift_hours
    if target_per_hour is not None:
        report["required_operators_for_target"] = required_operators(
            target_per_hour, smv_min, efficiency)
        report["target_output_per_hour"] = target_per_hour
        report["target_output_per_day"] = target_per_hour * shift_hours

    return report
