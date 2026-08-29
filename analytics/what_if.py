"""
what_if.py -- method/machine/attachment scenario comparison ("what-if"
analysis) on top of the SMV engine.

This is the capability that differentiates a *computed* SMV engine from a
static GSD/MTM lookup table: instead of looking up a fixed time for
"single-needle lockstitch" vs. "single-needle lockstitch + edge guide", the
engine is re-run with the changed machine class / attachment / handling
method and produces a genuinely different, physically-derived time. This
module NEVER stores or hardcodes any such time itself -- every number in its
output comes from a fresh call into `smv_assembly.assemble_operation()` /
`assemble_style()` against the caller-supplied engine context (taxonomy,
machine catalog, allowance policy), exactly as `shirt_library.style_smv()`
does for the unmodified style.

WHAT CAN BE CHANGED
--------------------
A scenario targets ONE step within ONE named operation (a garment's
operation bulletin, e.g. `shirt_library.build_style_operations()`'s output),
selected by step `kind` (`"seam"`, `"cycle"`, `"handling"`, `"bundle"`) and
optionally by `element` code, or by explicit index. Within that step, any
field the engine's step-dict schema accepts may be overridden -- most
commonly:
  * `machine_class`   -- swap machine (e.g. "SNLS-UBT" -> "SNLS-EDGE")
  * `attachment`       -- add/change/remove a machine attachment
                          (e.g. None -> "ATT-EG", per machine_classes.csv)
  * `element`           -- swap the handling method itself (e.g. HAG -> HAM,
                          acquire-single-piece vs. acquire-and-match)
  * any `params` sub-field (distance_cm, mass_g, plies, spi, curvature_class,
    guidance_class, ...)
`changes["params"]` is MERGED into the existing params dict (only the named
keys change); every other field is a plain override.

Public API
----------
    apply_step_change(operation, changes, step_kind=None, element=None,
                       step_index=None) -> sa.Operation      -- pure, no I/O
    compare_operation(ctx, operations, operation_name, changes, ...) -> dict
    compare_style(ctx, operations, operation_name, changes, ...) -> dict
    run_shirt_scenario(ctx, seam_geom, size, variant, operation_name,
                        changes, ...) -> dict                -- convenience
"""
from __future__ import annotations

import copy
from typing import Any, Optional

import line_balancing as lb
import costing as ct
from engine_loader import EngineContext, build_and_assemble_style


# --------------------------------------------------------------------------
# Step selection / mutation (pure functions, no engine calls)
# --------------------------------------------------------------------------

def _find_step_index(steps: list[dict], step_kind: Optional[str] = None,
                      element: Optional[str] = None,
                      step_index: Optional[int] = None) -> int:
    if step_index is not None:
        return step_index
    for i, s in enumerate(steps):
        if step_kind is not None and s.get("kind") != step_kind:
            continue
        if element is not None and s.get("element") != element:
            continue
        return i
    raise ValueError(
        f"no step matched selector (kind={step_kind!r}, element={element!r}) "
        f"among {len(steps)} steps")


def apply_step_change(operation, changes: dict, step_kind: Optional[str] = None,
                       element: Optional[str] = None,
                       step_index: Optional[int] = None):
    """Return a DEEP-COPIED `smv_assembly.Operation` with one step modified.

    `changes` keys are applied as plain field overrides on the step dict,
    EXCEPT `"params"`, which is merged (dict.update) into the step's
    existing `params` sub-dict so unrelated params are preserved.

    If no selector (`step_kind`/`element`/`step_index`) is given, the first
    `"seam"` step is targeted, falling back to the first `"cycle"` step --
    these are the two step kinds a machine/method swap normally targets.
    """
    new_op = copy.deepcopy(operation)
    if step_kind is None and element is None and step_index is None:
        kinds_present = {s.get("kind") for s in new_op.steps}
        step_kind = "seam" if "seam" in kinds_present else "cycle"
    idx = _find_step_index(new_op.steps, step_kind, element, step_index)
    step = new_op.steps[idx]
    # A genuine handling-METHOD swap (a different `element` code) almost
    # always carries a different parameter schema (e.g. HAG's precision_class
    # is not a valid HAM parameter) -- so when `element` is being changed,
    # `changes["params"]` REPLACES the step's params wholesale rather than
    # merging into the old element's (now largely invalid) param set. For a
    # same-element change (the common machine/attachment-swap case),
    # `params` merges as usual so unrelated params are preserved.
    element_changing = "element" in changes and changes["element"] != step.get("element")
    for k, v in changes.items():
        if k == "params" and isinstance(v, dict):
            if element_changing:
                step["params"] = dict(v)
            else:
                step.setdefault("params", {}).update(v)
        else:
            step[k] = v
    return new_op


def _find_operation(operations: list, operation_name: str, match: str = "exact"):
    if match == "exact":
        for i, op in enumerate(operations):
            if op.name == operation_name:
                return i, op
        raise ValueError(f"no operation named {operation_name!r} (exact match); "
                          f"available: {[op.name for op in operations]}")
    elif match == "contains":
        hits = [(i, op) for i, op in enumerate(operations) if operation_name in op.name]
        if not hits:
            raise ValueError(f"no operation name contains {operation_name!r}; "
                              f"available: {[op.name for op in operations]}")
        if len(hits) > 1:
            raise ValueError(f"ambiguous match for {operation_name!r}: "
                              f"{[op.name for _, op in hits]}")
        return hits[0]
    raise ValueError(f"unknown match mode {match!r}")


# --------------------------------------------------------------------------
# Operation-level comparison
# --------------------------------------------------------------------------

def compare_operation(ctx: EngineContext, operations: list, operation_name: str,
                       changes: dict, step_kind: Optional[str] = None,
                       element: Optional[str] = None, step_index: Optional[int] = None,
                       allowance_profile: str = "WOVEN_TOPS_DECOMPOSED",
                       match: str = "exact") -> dict:
    """Recompute ONE operation's SMV under a proposed step change.

    Returns `{"operation_name", "change", "base": assemble_operation() dict,
    "modified": assemble_operation() dict, "delta": {...}}`. Does not touch
    the rest of the style -- see `compare_style()` for the full-garment
    propagation.
    """
    idx, base_op = _find_operation(operations, operation_name, match=match)
    modified_op = apply_step_change(base_op, changes, step_kind, element, step_index)

    base_result = ctx.sa.assemble_operation(ctx.tax, ctx.mcat, ctx.pol, base_op,
                                             allowance_profile=allowance_profile)
    modified_result = ctx.sa.assemble_operation(ctx.tax, ctx.mcat, ctx.pol, modified_op,
                                                 allowance_profile=allowance_profile)
    delta_min = modified_result["ST_op_min"] - base_result["ST_op_min"]
    return {
        "operation_name": base_op.name,
        "operation_index": idx,
        "change": changes,
        "base": base_result,
        "modified": modified_result,
        "modified_operation": modified_op,
        "delta": {
            "ST_op_delta_min": delta_min,
            "ST_op_delta_pct": (delta_min / base_result["ST_op_min"] * 100.0
                                 if base_result["ST_op_min"] else float("nan")),
        },
    }


# --------------------------------------------------------------------------
# Full-style (garment) propagation + line-balance/costing deltas
# --------------------------------------------------------------------------

def compare_style(ctx: EngineContext, operations: list, operation_name: str,
                   changes: dict, step_kind: Optional[str] = None,
                   element: Optional[str] = None, step_index: Optional[int] = None,
                   allowance_profile: str = "WOVEN_TOPS_DECOMPOSED",
                   match: str = "exact",
                   n_workstations: Optional[int] = None,
                   target_rate_per_hour: Optional[float] = None,
                   labour_rate_per_hour: Optional[float] = None,
                   line_efficiency: float = 0.85) -> dict:
    """Full what-if scenario: recompute one operation's SMV, propagate to
    the garment total, and (optionally) the line balance and cost, reporting
    deltas throughout.

    Parameters beyond `compare_operation()`:
        n_workstations / target_rate_per_hour : passed straight to
            `line_balancing.balance_line()` for BOTH the base and modified
            style, if either is given (line balance is otherwise skipped).
        labour_rate_per_hour : if given, `costing.full_costing_report()` is
            run for both styles at `line_efficiency` (otherwise costing is
            skipped).
    """
    op_cmp = compare_operation(ctx, operations, operation_name, changes,
                                step_kind, element, step_index,
                                allowance_profile, match)
    idx = op_cmp["operation_index"]

    modified_operations = list(operations)
    modified_operations[idx] = op_cmp["modified_operation"]

    base_style = ctx.sa.assemble_style(ctx.tax, ctx.mcat, ctx.pol, operations,
                                        allowance_profile=allowance_profile)
    modified_style = ctx.sa.assemble_style(ctx.tax, ctx.mcat, ctx.pol, modified_operations,
                                            allowance_profile=allowance_profile)

    smv_delta = modified_style["SMV_min"] - base_style["SMV_min"]
    result = {
        "operation_name": op_cmp["operation_name"],
        "change": changes,
        "operation_delta": op_cmp["delta"],
        "base_style_smv_min": base_style["SMV_min"],
        "modified_style_smv_min": modified_style["SMV_min"],
        "style_smv_delta_min": smv_delta,
        "style_smv_delta_pct": (smv_delta / base_style["SMV_min"] * 100.0
                                 if base_style["SMV_min"] else float("nan")),
    }

    if n_workstations is not None or target_rate_per_hour is not None:
        base_lb = lb.balance_line(base_style, n_workstations=n_workstations,
                                   target_rate_per_hour=target_rate_per_hour)
        mod_lb = lb.balance_line(modified_style, n_workstations=n_workstations,
                                  target_rate_per_hour=target_rate_per_hour)
        result["line_balance"] = {"base": base_lb, "modified": mod_lb}
        result["bottleneck_change"] = {
            "base_bottleneck_workstation": base_lb["bottleneck_workstation"],
            "modified_bottleneck_workstation": mod_lb["bottleneck_workstation"],
            "base_bottleneck_smv_min": base_lb["bottleneck_smv_min"],
            "modified_bottleneck_smv_min": mod_lb["bottleneck_smv_min"],
            "bottleneck_smv_delta_min": mod_lb["bottleneck_smv_min"] - base_lb["bottleneck_smv_min"],
            "bottleneck_operation_changed": (
                op_cmp["operation_name"] in
                {n for n, ws in base_lb["assignment"].items() if ws == base_lb["bottleneck_workstation"]}
                or op_cmp["operation_name"] in
                {n for n, ws in mod_lb["assignment"].items() if ws == mod_lb["bottleneck_workstation"]}
            ),
        }
        result["efficiency_delta"] = {
            "base_theoretical_efficiency": base_lb["theoretical_efficiency"],
            "modified_theoretical_efficiency": mod_lb["theoretical_efficiency"],
            "delta": mod_lb["theoretical_efficiency"] - base_lb["theoretical_efficiency"],
        }

    if labour_rate_per_hour is not None:
        base_cost = ct.full_costing_report(base_style, labour_rate_per_hour, line_efficiency)
        mod_cost = ct.full_costing_report(modified_style, labour_rate_per_hour, line_efficiency)
        result["costing"] = {"base": base_cost, "modified": mod_cost}
        result["cost_delta_per_garment"] = (mod_cost["cost_per_garment"]
                                             - base_cost["cost_per_garment"])

    return result


# --------------------------------------------------------------------------
# Convenience wrapper: run a scenario directly against shirt_library
# --------------------------------------------------------------------------

def run_shirt_scenario(ctx: EngineContext, seam_geom: dict, size: str,
                        operation_name: str, changes: dict,
                        variant: str = "CLASSIC",
                        step_kind: Optional[str] = None,
                        element: Optional[str] = None,
                        step_index: Optional[int] = None,
                        allowance_profile: str = "WOVEN_TOPS_DECOMPOSED",
                        match: str = "exact",
                        bundle_size: Optional[int] = None,
                        n_workstations: Optional[int] = None,
                        target_rate_per_hour: Optional[float] = None,
                        labour_rate_per_hour: Optional[float] = None,
                        line_efficiency: float = 0.85) -> dict:
    """Build a `shirt_library` style bulletin from `seam_geom`/`size`/
    `variant` and run `compare_style()` against it in one call -- the shape
    a backend endpoint like `POST /styles/{id}/what-if` would call directly."""
    kwargs = {}
    if bundle_size is not None:
        kwargs["bundle_size"] = bundle_size
    operations = ctx.sl.build_style_operations(seam_geom, size, variant, **kwargs)
    return compare_style(ctx, operations, operation_name, changes,
                          step_kind=step_kind, element=element, step_index=step_index,
                          allowance_profile=allowance_profile, match=match,
                          n_workstations=n_workstations,
                          target_rate_per_hour=target_rate_per_hour,
                          labour_rate_per_hour=labour_rate_per_hour,
                          line_efficiency=line_efficiency)
