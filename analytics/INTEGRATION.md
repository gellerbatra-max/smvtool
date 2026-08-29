# Analytics layer -- backend integration guide

This package is the **Analytics track** of the SMV application: line
balancing, costing/target calculation, and what-if scenario comparison. It
is pure Python (stdlib only; no database, no web framework) and operates
entirely on the dicts already returned by the calculation engine
(`smv_assembly.assemble_style()` / `shirt_library.style_smv()`). It has no
knowledge of FastAPI, PostgreSQL, or HTTP, and should stay that way -- a
router calls these functions directly and persists/serialises whatever it
gets back.

**IP constraint carried through from the engine**: nothing in this package
stores or hardcodes an SMV, machine-speed, or allowance value. Every number
in every function below is produced by a fresh call into the engine
(`smv_assembly.assemble_operation/assemble_style`) for the exact inputs
given; if you don't see an engine call in a code path, that path does not
produce a garment-time number.

## Files

| File | Purpose |
|---|---|
| `engine_loader.py` | Bootstraps the flat, unpackaged engine modules onto `sys.path` and loads the taxonomy/machine-catalog/allowance-policy once. |
| `line_balancing.py` | RPW-based workstation assignment (Step 1). |
| `costing.py` | Cost-of-make and production-target formulas (Step 2). |
| `what_if.py` | Method/machine/attachment scenario comparison (Step 3). |
| `tests/` | pytest suite, fixtures built from `shirt_library.py`'s own CLASSIC/SHORT_SLEEVE/BLOUSE_COLLARLESS variants x 5 sizes. |
| `demo.py` | Standalone script producing `demo_*.csv` / `demo_report.md` for the CLASSIC shirt, size M. |

## 0. Wiring the engine bundle into the backend process

The engine bundle (`handling_time.py`, `machine_time.py`, `allowance.py`,
`smv_assembly.py`, `shirt_library.py`, plus their JSON/CSV source-data
files) is a set of flat modules that import each other by bare name and is
not published as an installable package. **Nothing in this analytics layer
changes that** -- it works around it via `engine_loader.py`, which:

1. Adds the engine bundle directory to `sys.path` once
   (`ensure_engine_on_path(engine_dir)`), so `import smv_assembly` etc.
   resolve regardless of the backend process's cwd.
2. Loads the taxonomy/machine-catalog/allowance-policy ONCE via explicit
   paths (`load_engine_context(engine_dir) -> EngineContext`), rather than
   through `shirt_library.style_smv()`'s own loader (which hardcodes bare
   filenames resolved against the **process's current working directory**,
   not the module's location -- a pre-existing engine constraint, not
   something to patch here).

A FastAPI app should call `load_engine_context(ENGINE_BUNDLE_DIR)` once at
startup (e.g. in a lifespan handler or a cached dependency) and reuse the
returned `EngineContext` for every request -- it is stateless and read-only
after loading, so it is safe to share across requests/threads.

```python
from engine_loader import load_engine_context, build_and_assemble_style

ENGINE_BUNDLE_DIR = "/opt/smv-engine/smv_engine_bundle"  # wherever it's deployed
ctx = load_engine_context(ENGINE_BUNDLE_DIR)   # do this once, at startup
```

## 1. Line balancing -- `line_balancing.py`

```python
def balance_line(style_or_op_times, n_workstations=None,
                  target_rate_per_hour=None, target_rate_per_day=None,
                  shift_hours=8.0) -> dict
```

**Input**: either the dict `smv_assembly.assemble_style()` /
`shirt_library.style_smv()` returns, or a plain
`[{"name": str, "st_min": float}, ...]` list in build-sequence order (useful
if the backend has already cached just the operation list/times). Supply
`n_workstations` (fixed headcount, minimise bottleneck) and/or
`target_rate_per_hour`/`target_rate_per_day` (fixed cycle time, minimise
headcount if `n_workstations` is omitted; otherwise used only to report
whether the given headcount meets it).

**Output** (all keys always present unless noted):
```python
{
  "method": str,                          # cites RPW + the precedence assumption
  "n_operations": int,
  "total_smv_min": float,
  "n_workstations_requested": int,
  "n_workstations_used": int,             # may be < requested if excess capacity
  "assignment": {operation_name: workstation_index, ...},
  "workstations": [
      {"workstation": int, "operations": [name, ...],
       "load_min": float, "idle_min": float}, ...
  ],
  "bottleneck_workstation": int,
  "bottleneck_smv_min": float,
  "theoretical_efficiency": float,        # sum(SMV) / (n_workstations * bottleneck)
  "total_idle_min": float,
  "achievable_output_per_hour": float,    # 60 / bottleneck_smv_min
  "achievable_output_per_shift": float,
  # present only if a target rate was supplied:
  "target_rate_per_hour": float,
  "target_cycle_time_min": float,
  "achievable_efficiency_at_target": float,  # capped at 1.0
  "meets_target": bool,
}
```

`balance_line()` raises `ValueError` if neither `n_workstations` nor a
target rate is given, or if the target cycle time is shorter than the
single longest operation (physically infeasible without splitting that
operation). A backend router should catch `ValueError` and turn it into a
4xx with the message passed through -- it is already a plain, user-facing
explanation, not an internal detail.

**What a router persists**: typically the whole result dict as JSON against
the style+scenario+parameters that produced it (style id, size, variant,
n_workstations, target_rate, timestamp) -- this is small (`O(n_operations)`)
and cheap to regenerate, so persisting for audit/history is the main reason
to store it rather than recomputing on read.

Also exposed: `rpw_table(style_or_op_times) -> list[dict]` (the explicit
RPW ranking table, `{"name", "st_min", "sequence_index", "rpw_min"}` per
operation) if the UI wants to show the ranking itself, not just the
resulting assignment.

## 2. Costing -- `costing.py`

```python
def full_costing_report(style_or_smv_min, labour_rate_per_hour, efficiency,
                         n_operators=None, target_output_per_hour=None,
                         target_output_per_day=None, shift_hours=8.0) -> dict
```

**Input**: `style_or_smv_min` is either the assembled-style dict or a raw
SMV in minutes (float). `labour_rate_per_hour` is currency/hour in
whatever currency the caller uses (passed straight through, unconverted).
`efficiency` is a fraction in `(0, 1]`; raises `ValueError` outside that
range. `n_operators` and/or `target_output_per_hour`/`_per_day` are
optional -- each turns on one extra section of the report.

**Output**:
```python
{
  "smv_min": float, "labour_rate_per_hour": float, "efficiency": float,
  "cost_per_garment": float,                 # SAM x (rate/60) / efficiency
  # present only if n_operators given:
  "production_at_n_operators": {
      "smv_min", "n_operators", "efficiency",
      "output_per_hour", "output_per_shift", "output_per_day"
  },
  "daily_labour_cost_at_n_operators": float,
  # present only if a target output was given:
  "required_operators_for_target": {
      "smv_min", "target_output_per_hour", "efficiency",
      "operators_required_raw", "operators_required"   # ceil'd, staffable
  },
  "target_output_per_hour": float, "target_output_per_day": float,
}
```

Also exposed individually for finer-grained calls:
`cost_per_garment(style_or_smv_min, labour_rate_per_hour, efficiency) -> float`,
`production_rate(n_operators, style_or_smv_min, efficiency, shift_hours=8.0) -> dict`,
`required_operators(target_output_per_hour, style_or_smv_min, efficiency) -> dict`.

**What a router persists**: the cost-of-make figure is normally the one
value that gets written back onto the style record (`styles.cost_per_garment`,
plus the `labour_rate_per_hour`/`efficiency` it was computed at, so a later
rate change doesn't silently invalidate a stored cost without an audit
trail of what changed).

## 3. What-if scenario comparison -- `what_if.py`

Two entry points, depending on what the caller already has in hand:

```python
def compare_style(ctx, operations, operation_name, changes,
                   step_kind=None, element=None, step_index=None,
                   allowance_profile="WOVEN_TOPS_DECOMPOSED", match="exact",
                   n_workstations=None, target_rate_per_hour=None,
                   labour_rate_per_hour=None, line_efficiency=0.85) -> dict

def run_shirt_scenario(ctx, seam_geom, size, operation_name, changes,
                        variant="CLASSIC", step_kind=None, element=None,
                        step_index=None, allowance_profile=..., match="exact",
                        bundle_size=None, n_workstations=None,
                        target_rate_per_hour=None, labour_rate_per_hour=None,
                        line_efficiency=0.85) -> dict
```

`run_shirt_scenario()` is the one a `POST /styles/{id}/what-if` endpoint
calls directly if the backend only stores `(seam_geom, size, variant)` for
a style, not the raw `Operation` list -- it rebuilds the operation bulletin
itself via `shirt_library.build_style_operations()` before comparing.
`compare_style()` is the lower-level entry point for any operation bulletin
(not just `shirt_library`'s), e.g. once a real garment-CAD ingestion path
exists beyond woven shirts.

**`operation_name`** selects the target operation by its `Operation.name`
(exact match by default; pass `match="contains"` for a unique substring
match, e.g. `"Close side seam"`).

**`changes`** is a dict of field overrides applied to ONE step within that
operation (selected by `step_kind`/`element`/`step_index`; defaults to the
operation's `"seam"` step, falling back to `"cycle"`). Common shapes:

```python
# swap the sewing machine
{"machine_class": "OL-5T-SS"}
# add/change a machine attachment (see machine_classes.csv for valid codes)
{"attachment": "ATT-EG", "guidance_class": "mechanically_guided"}
# swap the handling method itself (different element => different param
# schema, so "params" REPLACES rather than merges -- see what_if.py docstring)
{"element": "HAM", "params": {"distance_cm": 15.0, "plies": 2,
                               "match_precision": "P2", "fabric_class": "REF_POPLIN",
                               "n_match_points": 2, "mass_g": 45.0}}
# tweak a same-element parameter (merges into existing params)
{"params": {"spi": 12}}
```

**Output**:
```python
{
  "operation_name": str, "change": dict,
  "operation_delta": {"ST_op_delta_min": float, "ST_op_delta_pct": float},
  "base_style_smv_min": float, "modified_style_smv_min": float,
  "style_smv_delta_min": float, "style_smv_delta_pct": float,
  # present only if n_workstations or target_rate_per_hour given:
  "line_balance": {"base": <balance_line() dict>, "modified": <balance_line() dict>},
  "bottleneck_change": {
      "base_bottleneck_workstation", "modified_bottleneck_workstation",
      "base_bottleneck_smv_min", "modified_bottleneck_smv_min",
      "bottleneck_smv_delta_min", "bottleneck_operation_changed",  # bool
  },
  "efficiency_delta": {"base_theoretical_efficiency",
                        "modified_theoretical_efficiency", "delta"},
  # present only if labour_rate_per_hour given:
  "costing": {"base": <full_costing_report() dict>, "modified": <...>},
  "cost_delta_per_garment": float,
}
```

`compare_operation()` (operation-level only, no style/line/cost
propagation) and `apply_step_change()` (pure step mutation, no engine call)
are also exposed for finer-grained use or unit testing a proposed change
before running the full comparison.

**What a router persists**: a what-if request is normally NOT persisted as
part of the style's own record (it's exploratory, not a committed change)
-- log it as an audit-trail event (`what_if_runs` table: style id, operation
name, `changes` dict, resulting deltas, requester, timestamp) if the
product wants a history of "what was tried", and only write back onto the
style itself if/when the user explicitly accepts the change (at which point
the router should re-run `shirt_library.build_style_operations()` with the
same modification baked in as a permanent change to that operation's
source spec, not just re-apply this module's patch every time).

## Error handling summary for the router layer

| Exception | Raised by | Meaning |
|---|---|---|
| `ValueError` | `balance_line()` | no `n_workstations`/target given, or target cycle time shorter than the longest operation |
| `ValueError` | `cost_per_garment` / `production_rate` / `required_operators` | `efficiency` outside `(0, 1]` |
| `ValueError` | `what_if._find_operation()` (via `compare_operation`/`compare_style`/`run_shirt_scenario`) | `operation_name` not found, or `match="contains"` matched more than one operation |
| `ValueError` | `what_if._find_step_index()` | no step matched the given `step_kind`/`element`/`step_index` selector |
| (engine's own exceptions) | `smv_assembly.assemble_operation/assemble_style` | e.g. an invalid `machine_class`/`element` code, or a parameter outside the taxonomy's declared domain -- these propagate unchanged; treat as a 400 with the engine's own message, which is already descriptive |

All three modules raise plain `ValueError`/engine exceptions with
human-readable messages -- there is no custom exception hierarchy to learn,
and none of them ever return a partially-computed result silently.
