# Phase 1 (Calculation Engine + Calibration) — Completion Report

**Project:** Self-calibrating SMV (Standard Minute Value) engine for woven-top
garment sewing, built as an independent replacement for GSD (General Sewing
Data).
**Scope of this report:** Phase 1 only — the engine core (handling time,
machine time, allowance, assembly) and the calibration module (coefficient
fitting, diagnostics). Phase 0 (motion model, machine data, benchmarks) is
covered by `phase0_completion_report.md`; the multi-user web application is
future work, not started.

## 1. What was built

| Module | Role | Status |
|---|---|---|
| `handling_time.py` | Interprets `element_taxonomy.json`'s 23-element phase-primitive grammar (Fitts-law point/steer/grasp/fixed/cognitive) into per-element auditable time | Complete, tested |
| `machine_time.py` | Wraps `effective_spm.py`'s kinematic seam/cycle solver into a catalog-driven interface | Complete, tested |
| `allowance.py` | Applies `allowance_policy.json`'s 12 allowance categories per element | Complete, tested |
| `smv_assembly.py` | Composes operation SMV: `BT_op`/`ST_op`, `MAX(t_machine, t_guide)` seam binding, bundle amortisation, no-double-count checks | Complete, tested |
| `time_study_schema.json` / `time_study_loader.py` | Ingestion schema + validating loader for factory time-study data | Complete, tested |
| **`calibration_fit.py`** | **Hierarchical coefficient fitting** — this phase's main new work | Complete, tested |
| **`calibration_diagnostics.py`** | **Residual analysis, cross-validation, coverage reporting** — this phase's main new work | Complete, tested |
| `test_engine.py` + `test_calibration.py` | Full pytest suite | **62/62 passing** (35 engine + 27 calibration/diagnostics) |

Every module remains a pure interpreter over the taxonomy/policy/catalog
JSON/CSV files from Phase 0 — no engine module hardcodes a time value; every
number traces back to a phase-primitive equation, a fitted coefficient, or a
declared allowance policy.

## 2. Calibration module design

### 2.1 Why hierarchical, and why this particular hierarchy

The taxonomy ships 30 global parameters and 5 element-local engine constants,
24 of them marked `calibration-pending`; `effective_spm.py`'s `MotionParams`
adds 10 more. A single flat regression over all ~41 quantities against
whatever a factory happens to time-study first would be badly identified:
most factories' first time-study campaign will not evenly sample every
element × fabric × machine combination, so many coefficients would be
determined almost entirely by regularisation rather than data. The taxonomy's
own design already separates these concerns by *what kind of thing* a
parameter describes, so calibration follows that separation as three scopes,
fit **sequentially, each held fixed for the next**:

1. **Engine-wide physical constants** (`fit_scope1`) — the Fitts/steering-law
   coefficients, grasp/ply/bundle terms, fabric-difficulty terms, cognitive
   term, bimanual coupling, the four element-local engine constants, and
   `effective_spm.MotionParams`. These describe human motor control and
   sewing-machine kinematics, not any one factory's culture or fabric, so they
   are fit **once, pooling every factory's rows**, by nonlinear least squares
   on `log(observed_s) - log(predicted_s)` (log space because cycle times are
   strictly positive and multiplicative, not additive, in their natural
   variability). Fit is via `scipy.optimize.least_squares` with `trf`
   (bounded trust-region reflective), bounded by each symbol's taxonomy-
   declared `plausible_range` (or a documented ±generous band for the four
   engine constants and `MotionParams` fields, which carry no
   `plausible_range` field in their source JSON/dataclass).
2. **Factory-level reference-fabric parameters** (`fit_factory_reference_fabric`)
   — `B_ref`/`MIU_ref`/`t_ref_mm` describe what a *specific factory* means by
   "the reference fabric" (a Dhaka poplin lot is not a Ho Chi Minh City poplin
   lot). These are fit per `factory_id` from direct KES-F-style fabric
   measurements attached to a batch's `environment.measured_*` fields — never
   from residuals, since residual-based fitting would conflate fabric identity
   with every other unmodelled factory effect.
3. **Operator-level `Gamma_skill`** (`fit_operator_gamma`) — a per-operator
   multiplier nested within factory, fit via `statsmodels` `MixedLM` on the
   scope-1(+2)-residuals with a `factory_id` group and an `operator`
   variance component keyed `factory_id::operator_id` (so the same
   `operator_id` string at two factories is never pooled). `MixedLM`'s REML
   partial pooling is exactly the shrinkage a small, unbalanced per-operator
   sample needs: an operator with few observations is pulled toward 1.0
   rather than given a noisy, overconfident personal multiplier. A closed-
   form James–Stein-style shrinkage estimator is the automatic fallback if
   `MixedLM` fails to converge (this happened routinely on the single-factory
   synthetic demo below — see §4 — because a one-level grouping factor is a
   degenerate case for a nested-variance-component model; it is not expected
   to recur with two or more real factories in the training set).

This is a **sequential partial-pooling** scheme, not a jointly Bayesian one:
each scope is fit and then frozen before the next scope sees its residuals.
That trade-off was chosen deliberately over a joint hierarchical Bayesian fit
(e.g. via a bespoke MCMC/variational implementation) because every stage uses
a standard, independently auditable library (`scipy.optimize`,
`statsmodels`) that a reviewer without a probabilistic-programming background
can inspect, and because the scope-1 physical constants are — by
construction — identifiable from data pooled across every factory, in a way
that the modest per-factory/per-operator samples a single time-study
campaign typically produces are not.

### 2.2 Sparse and unbalanced data handling

Nothing in this module fits blind. Before any regression runs,
`sensitivity_report()` numerically tests, for every scope-1 symbol, how many
supplied observation rows actually move that symbol's prediction (a 5% bump
test, not the optimizer's own Jacobian) and what kind of observation
supplied that sensitivity. Any symbol below `MIN_OBS_FOR_FIT` (default 5)
sensitive rows is **excluded from the fit vector entirely** and reported with
`used_default=True` plus the reason — the shipped default is kept, not
silently overwritten by an underdetermined fit. The same pattern governs
scope 2 (`MIN_OBS_FOR_FACTORY`, default 3 direct fabric measurements) and is
implicit in scope 3 (an operator with `< MIN_OBS_FOR_OPERATOR` observations
is shrunk hard toward 1.0 by the mixed model's own variance-component
estimate, and is flagged as such in the coverage report rather than
presented as a confident personal multiplier).

### 2.3 Coverage / diagnostics report

`calibration_diagnostics.py`, run against the SYNTHETIC demonstration batch
described in §4, produces:

- `calibration_diagnostics.png` — four panels: predicted-vs-observed
  (log-log), residual-distribution histogram, MAPE by observation kind
  against the cross-validated out-of-sample MAPE, and a coverage bar chart of
  supporting-observation counts per engine-wide symbol.
- `calibration_residuals.csv` — one row per observation with
  observed/predicted/residual/log-residual/percent-error.
- `calibration_error_by_kind.csv` — MAPE, log-RMSE, median log-residual and
  bias by observation kind (element/seam/cycle).
- `calibration_coverage.csv` — every calibration-pending symbol across all
  three scopes, its supporting-observation count, and `SUFFICIENT` /
  `INSUFFICIENT` status — **the explicit answer to "which coefficients still
  lack supporting observations."**

On the 200-row synthetic demo batch (8 synthetic operators, mixed element/
seam/cycle rows), the coverage report finds **21 of 41 scope-1 symbols**
sufficiently supported (`t_endstop`, `eta_set`, `t_trim_auto`, `a_steer`,
`b_steer`, `k_R`, `a_up`/`a_dn`/`R_ref_mm`, `kappa_m`, `m_ref_g`, `a_arm`/
`b_arm`, `a_wri`/`b_wri`, `g_0`, `eta_ply`, `g_ply`, `epsilon_bi`,
`fold_tolerance_frac`, `t_look`) and **20 insufficient**
(`phi_limp`/`phi_slip`/`phi_bulk`/`Phi_min`/`Phi_max`, `a_fin`/`b_fin`,
`D_trunk_mm`, `c_lean`, `gamma_ply`, `g_bundle`, `t_pivot`, `theta_drift`,
`t_correct`, `t_trim_manual`, `k_theta`, `k_ease`, `n_throat_aim`,
`L_grip_cm`, `D_match_mm`) — because this demo batch's probe set
(§4) never exercised the fine-finger-motion, fabric-difficulty-rectification,
or bundle-handling elements densely enough. This is the expected, honest
shape of a first-pass campaign: **a real time-study design should be
deliberately built to visit each `element_taxonomy.json` element with varied
distance/plies/precision-class combinations, not just the operations a floor
happens to run that week**, precisely so the coverage report comes back
green across more of the 41 rows.

## 3. Test suite

`pytest test_engine.py test_calibration.py` — **62 passed, 0 failed**
(35 pre-existing engine tests + 27 new calibration/diagnostics tests). New
coverage includes: synthetic-generator reproducibility and schema-validity;
sensitivity-report correctness (including the finding that `b_steer` is
legitimately sensitive to *both* `element_observation` and
`seam_observation` rows, since several handling elements besides the seam-
guide element use a `steer` phase); sparse-data fallback-to-default behaviour;
a recovery test that perturbs `g_0` in a copied taxonomy, generates synthetic
data from the perturbed version, and checks the fit moves measurably closer
to the (unknown-to-the-fitter) true value than the shipped default was;
bounds respected on both taxonomy `plausible_range`s and `MotionParams`
bounds; factory-level fabric-reference isolation across factories; operator-
`Gamma_skill` rank-order recovery under known ground truth; and an IP-
provenance smoke check that the module's source contains no `TMU_BY_DISTANCE`
table or MTM Get-code literals.

## 4. Worked demonstration: synthetic data, not real calibration

**No real factory time-study data exists yet.** Every number in §2.3 and
every figure/table this phase produced is generated by
`calibration_fit.generate_synthetic_batch()`, which perturbs the *engine's
own* predictions with a per-operator ground-truth `Gamma_skill` multiplier
and log-normal measurement noise (`noise_sigma_log=0.12` by default), then
labels every resulting row `method: "SYNTHETIC"` per `time_study_schema.json`'s
own convention for exactly this purpose — so these rows can never be
mistaken for, or accidentally pooled with, real observations. On this
self-consistent synthetic set, `calibration_diagnostics.py` recovers:

- **In-sample MAPE:** 10.2% (element), 12.1% (seam), 11.5% (cycle)
- **5-fold cross-validated out-of-sample MAPE: 11.8% ± 1.8%**
- Operator-level `Gamma_skill` recovers the correct **rank order** of
  synthetic operators' true skill multipliers in every seeded trial run
  during test development (see `test_recovers_operator_ranking`), though
  point estimates are shrunk toward 1.0 relative to the (larger, deliberately
  well-separated) synthetic ground truth — the expected and correct behaviour
  of a partial-pooling estimator on a modest per-operator sample.

This demonstrates the fitting **machinery is correct** — it recovers a known
answer from data generated by a known process. It says nothing about the
engine's absolute accuracy on a real factory floor, because the "observed"
times here are the engine's own predictions plus noise, not independent
ground truth from a stopwatch.

## 5. What real time-study data is needed next

Per the original project's own feasibility estimate at the start of this
project, **roughly 30–50 real time studies** were flagged as the point at
which absolute SMVs might begin to approach GSD-grade accuracy. This phase's
coverage analysis sharpens that estimate:

- **Not 30–50 *studies* uniformly — 30–50 *observations per scope-1 symbol*
  that is actually exercised.** Because scope 1 pools across the whole
  factory network, a single well-designed time-study campaign that
  deliberately varies distance/plies/precision-class/fabric per element (not
  just timing whatever operations are already running) can identify most of
  the 41 scope-1 symbols from as few as 150–250 total observations, per the
  synthetic demonstration's own coverage pattern in §2.3 — but a campaign
  that only times the operations already on the floor will under-visit
  several elements (bundle handling, fine-finger elements, fabric-difficulty
  rectification) exactly as the demo did.
- **Scope 2 (factory reference fabric)** needs a *different kind of data*
  entirely: direct KES-F (or equivalent) bending-rigidity, friction and
  thickness measurements of the factory's actual reference fabric lot, not
  more stopwatch rows. Recommend at least 3 such measurements per factory
  before trusting a factory-specific `B_ref`/`MIU_ref`/`t_ref_mm`.
  `fit_factory_reference_fabric` will fall back to the global (nominal
  poplin) values indefinitely until this data is supplied — it is not
  optional infrastructure, it is a real measurement gap.
- **Scope 3 (operator `Gamma_skill`)** needs roughly 10+ observations per
  operator before the mixed model gives a confident (as opposed to
  shrunk-to-1.0) personal multiplier; this is the cheapest scope to satisfy
  since it accrues automatically from ordinary line time studies.
- A useful acceptance target for "ready to replace GSD on woven tops": the
  coverage report at ≥ 80% `SUFFICIENT` across scope-1 symbols, cross-
  validated MAPE (on REAL, non-SYNTHETIC data) below roughly 10–15%, and at
  least one factory with a measured (non-default) reference fabric.

## 6. IP provenance statement

No licensed predetermined-motion-time data was used anywhere in this phase's
engine logic, defaults, or test fixtures:

- `calibration_fit.py` and `calibration_diagnostics.py` fit **numbers only**
  — coefficients of the open Fitts-law / steering-law functional forms
  already established in `handling_time.py` and `effective_spm.py` (see
  those modules' own IP-provenance docstrings). Neither module contains a
  lookup table keyed by a GSD or MTM code, and the IP-provenance smoke test
  (`test_no_hardcoded_gsd_or_mtm_tables_in_module`) checks the source contains
  no `TMU_BY_DISTANCE` table structure and no MTM Get-code literals
  (`GB1`/`GB2`).
- `time_study_schema.json` / `time_study_loader.py` (Phase 0's final step,
  validated again this phase) define a *factory's own* observation format;
  they reference the taxonomy's own element codes, not any licensed system's
  codes.
- The synthetic-data generator produces rows explicitly and permanently
  labelled `method: "SYNTHETIC"`, generated from the engine's own equations
  plus noise — no external proprietary dataset was consulted to build or
  validate it.
- Unit convention throughout: `1 TMU = 0.0006 min = 0.036 s` ⇒
  `1 s = 27.7778 TMU`, `1 min = 1666.67 TMU` — the correct conversion (a
  competing `33.33 TMU/s` figure found in some secondary web sources during
  Phase 0's literature search is wrong and is not used anywhere in this
  codebase).

## 7. Known limitations / honest caveats

- The `MixedLM` fit on the single-factory synthetic demo in §4 triggers a
  boundary-of-parameter-space convergence warning — expected with only one
  `factory_id` group (a degenerate case for a nested variance-component
  model) and handled by the module's documented shrinkage fallback; this is
  not expected to recur once two or more real factories are in the training
  set, but should be watched on the first real multi-factory fit.
- Scope 1's per-parameter standard errors are computed from a linearised
  Gauss–Newton covariance approximation (`least_squares`'s Jacobian at the
  optimum), not a full nonlinear confidence interval — adequate for
  flagging which fitted values are loosely determined, not a substitute for
  a proper bootstrap if a factory needs defensible confidence bounds for an
  audit.
- No real-world validation exists yet for either the engine's absolute SMVs
  or the calibration module's real-data behaviour — see §5 for what closes
  that gap.

## Files delivered this phase

`calibration_fit.py`, `calibration_diagnostics.py`, `test_calibration.py`
(added to the existing `test_engine.py`), `calibration_diagnostics.png`,
`calibration_residuals.csv`, `calibration_error_by_kind.csv`,
`calibration_coverage.csv`, this report.
