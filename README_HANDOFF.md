# SMV Engine Project — Handoff Bundle

This zip contains the complete, current state of the self-calibrating SMV
(Standard Minute Value) engine project, packaged for moving to a new Claude
account/session.

## What's inside

**Source specs (inputs to the engine, provided by the user originally):**
- `element_taxonomy.json` — 23 handling elements, phase-primitive equations
  (Fitts-law point/steer/grasp/fixed/cognitive), fabric-difficulty (PHI) model,
  global parameters, class tables, assembly rules
- `allowance_policy.json` — 12 allowance categories, 3 profiles
  (decomposed/conventional/ILO-floor), application rules
- `seam_geometry.json` — seam and cycle operations with per-size path lengths,
  used for validation/crosscheck
- `machine_classes.csv` — machine and attachment catalog
- `effective_spm.py` — pre-existing machine-speed model (ramp/pivot/guidance
  kinematics) that the engine wraps
- `motion_model.md` — narrative spec behind the taxonomy

**Engine modules built this project (in dependency order):**
1. `handling_time.py` — interpreter over the taxonomy's expression grammar;
   computes all 23 elements' times with full audit trail + domain validation
2. `machine_time.py` — wraps `effective_spm.py` into `time_seam()`/
   `time_cycle()`, plus `pure_machine_time_seam()` (guidance-free machine-only
   estimate, needed for the assembly module's `MAX(t_machine, t_guide)` rule)
3. `allowance.py` — allowance-policy engine (AR1–AR8): additive-then-single-
   multiplication, parametric FORCE_WEIGHT/CLOSE_ATTENTION, caps enforced
4. `smv_assembly.py` — ties it all together: `BT_op`/`ST_op` per operation,
   bundle amortization, no-double-count checks, full audit trail
5. `test_engine.py` — pytest suite, 35/35 passing, covering all four modules
6. `worked_example.py` / `worked_example.png` / `worked_example_audit_trail.csv`
   — a full end-to-end worked example (armhole seam, size M): 76.75s = 1.279
   min = 2131.9 TMU, with the finding that operator guidance (not machine
   speed) is the binding constraint for this tight-curvature topstitched seam
7. `time_study_schema.json` / `time_study_loader.py` — ingestion schema +
   validating loader for real factory time-study data, designed to feed the
   next step (hierarchical coefficient-fitting / calibration module — the
   engine's `calibration-pending` global parameters are the fit targets)

**Reference/prior reports:**
- `phase0_completion_report.md`, `benchmark_report.md` — earlier phase
  writeups
- `smv_benchmarks.csv`, `model_vs_benchmark_crosscheck.csv` — benchmark
  comparison data
- `effective_spm_model.png` — figure from the machine-speed model
- `plan_build-the-smv-calculation-engine-phase-1_e6fffbae.json`,
  `plan_recover-and-complete-phase-0-engineering_e6fffbae.json` — the
  project's plan documents (step titles/descriptions), useful for restating
  exact step titles to a fresh session

## Where the project stood at handoff (updated)

**Phase 1 is now COMPLETE.** Completed plan steps: (1) handling-time module,
(2) machine-time module, (3) SMV assembly + allowance application, (4) engine
test suite (35/35 passing), (5) worked example end-to-end, (6) time-study
ingestion schema, (7) hierarchical coefficient-fitting calibration module
(`calibration_fit.py`), (8) calibration diagnostics + coverage report
(`calibration_diagnostics.py`), (9) Phase 1 completion report
(`engine_phase1_report.md`).

Full test suite: **62/62 passing** (`pytest test_engine.py test_calibration.py`
from inside `smv_engine_bundle/`, with `PYTHONPATH=.` set — the modules import
each other by bare name and are not yet packaged).

**Calibration module design** (as built): fits engine constants in three
sequential scopes — (1) engine-wide physical constants shared across
factories, fit by bounded nonlinear least squares in log-time space, pooling
every factory's rows, with a sensitivity-gated fit vector so any symbol below
`MIN_OBS_FOR_FIT` (default 5) keeps its shipped default rather than being
fit from too little data; (2) factory-level reference-fabric parameters
(`B_ref`/`MIU_ref`/`t_ref_mm`), fit from direct `environment.measured_*`
fabric measurements per factory, never from residuals; (3) operator-level
`Gamma_skill`, fit via `statsmodels` `MixedLM` (operator nested in factory)
on the scope-1(+2) residuals, with a closed-form shrinkage fallback if
`MixedLM` fails to converge. A synthetic-data generator
(`generate_synthetic_batch`, method-tagged `SYNTHETIC` per schema convention)
demonstrates and tests all three scopes since no real factory time-study data
exists yet. See `engine_phase1_report.md` for full design rationale, the
demonstrated in-sample/cross-validated MAPE (~10-12%), the coverage-report
finding (20/41 scope-1 symbols identified by the 200-row synthetic demo, 21
still needing better-targeted observations), and the recommended real-data
campaign size going forward.

**Phase 2 (Operation library) is also now COMPLETE.** `shirt_library.py`
decomposes Phase 0's `seam_geometry.json` (21 seam + 6 cycle operations for
a classic men's woven shirt) into full `smv_assembly.Operation` objects with
a documented, keyword-driven rule for handling-element assignment, plus two
style variants (`SHORT_SLEEVE`, `BLOUSE_COLLARLESS`) built by the same
DERIVED_GEOMETRIC convention Phase 0 established. `validate_shirt_library.py`
runs an exact geometry crosscheck (passes) and an explicitly-labelled
order-of-magnitude comparison against the only available (product-mismatched)
public benchmark. See `phase2_operation_library_report.md` for full detail,
including an UNRESOLVED discrepancy on the stored machine-time crosscheck
field (recomputed minutes don't match it, and after testing several
candidate explanations against the current code, none reproduced the stored
figure -- the root cause is not established, flagged for follow-up, not
waved away) and the two things NOT attempted (a genuinely distinct blouse
silhouette; closing the woven-shirt benchmark gap, which needs real
time-study data).
Test suite: **82/82 passing**.

**Not yet started:** the multi-user web application (FastAPI backend +
browser UI) — the engine + calibration + operation-library layers are a
Python library only at this point, with no HTTP interface, database
persistence, or UI.

## To resume in a new session

1. Upload this zip (or its unpacked contents) as an attachment.
2. Point the agent at this README plus `engine_phase1_report.md` (and the
   plan JSON files, if continuing against the original plan) to reconstruct
   context, or simply say "continue the SMV engine project — see
   README_HANDOFF.md" and paste/attach this file.
3. Environment: pure-Python, needs `pandas`, `pytest`, `numpy`, `scipy`,
   `statsmodels`, `matplotlib`. Run tests with
   `PYTHONPATH=. pytest test_engine.py test_calibration.py test_shirt_library.py -q`
   from inside the unpacked bundle directory (82/82 passing).
4. Natural next step: build the FastAPI + browser application layer over
   `shirt_library.style_smv()` / `smv_assembly.assemble_style()` (Phase 3 of
   the original plan), OR begin a real factory time-study campaign designed
   against `engine_phase1_report.md` §5's coverage recommendations, feeding
   results through `time_study_loader.py` into `calibration_fit.calibrate_all()`.
