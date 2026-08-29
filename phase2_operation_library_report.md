# Phase 2 (Operation Library) — Completion Report

**Scope:** builds a usable woven-top operation library on top of Phase 0's
`seam_geometry.json` and Phase 1's engine, per the approved plan's "Operation
library" phase.

## What was built

| File | Role |
|---|---|
| `shirt_library.py` | Decomposes `seam_geometry.json`'s 21 seam + 6 cycle operations into full `smv_assembly.Operation` objects, with a documented, keyword-driven rule for which handling element (HAM/HAG/HFC/HRP) each operation gets, and three style variants: `CLASSIC`, `SHORT_SLEEVE`, `BLOUSE_COLLARLESS` |
| `validate_shirt_library.py` | Two separated validations: an exact stitch-path geometry crosscheck against `seam_geometry.json`'s own stored figures, and an explicitly product-mismatched order-of-magnitude comparison against the Phase-0 knit-polo benchmark |
| `test_shirt_library.py` | 20 new tests | all passing |
| `shirt_classic_M_operation_bulletin.csv` | Full per-operation standard-time breakdown, classic shirt, size M |
| `shirt_library_variant_smv_by_size.csv` | SMV by variant × size (15 rows) |
| `shirt_library_benchmark_comparison.csv` | Garment-level order-of-magnitude comparison |
| `shirt_library_summary.png` | Operation bulletin + variant SMV figure |

**Full suite: 82/82 passing** (`pytest test_engine.py test_calibration.py test_shirt_library.py`).

## Headline numbers (size M)

| Variant | Operations | SMV (min) | SMV (TMU) |
|---|---|---|---|
| Classic | 27 | 12.57 | 20,954.5 |
| Short sleeve | 22 | 10.05 | 16,758.0 |
| Blouse, collarless | 21 | 9.26 | 15,439.9 |

SMV increases monotonically with size in every variant (S→XXL), and both
reduced variants are cheaper than Classic at every size — both internal-
consistency properties are asserted in the test suite, not just eyeballed.

## Validation: what it does and honestly does not show

1. **Geometry crosscheck (exact, passes):** `shirt_library.py`'s seam records
   reproduce `seam_geometry.json`'s own stored `total_stitch_path_mm`
   (14,313.4 mm) exactly — confirming the operation-assembly logic reads the
   Phase-0 geometry correctly.
2. **Machine-time-in-minutes vs. the stored `machine_time_crosscheck`
   field: does NOT match, and the cause is UNRESOLVED.** The code path this
   deliverable actually runs and tests against —
   `crosscheck_machine_time()`'s call into `mt.pure_machine_time_seam()` per
   seam record plus `mt.time_cycle()` per cycle record — gives **3.221 min**
   total machine time (seam 2.557 + cycle 0.665) against the stored
   **4.966 min** (seam 3.732 + cycle 1.234), a **~35% gap**, with the
   cycle-time component alone off by a factor of ~1.86x. (A separate,
   one-off exploratory probe using a different, *blended* seam-time formula
   — `mt.time_seam()`, which is not what this module calls — got closer,
   ~4.47 min overall; that number describes a different code path than the
   one this deliverable ships and should not be read as the module's own
   result.) An earlier draft of this report claimed the gap was explained by
   a `MotionParams` coefficient change since the field was frozen — that
   claim was **checked and found false**: no edit to `effective_spm.py`'s
   `MotionParams` defaults exists anywhere in this project's history, and
   testing several other candidate formulas (pure vs. blended seam model,
   no ramp derate, no `eta_set` derate, alternate ply counts) against the
   *current* code did not reproduce the stored figure either. The actual
   method used to compute the stored field is not recoverable from this
   session. The geometry crosscheck (stitch-path totals) still passes
   exactly and is reported as the one verified check; the minutes-level gap
   is reported as an **open, unresolved discrepancy** (~35% on the module's
   own code path) that should be
   investigated before the stored crosscheck field is relied on for
   anything beyond a geometry sanity check.
3. **Garment-level benchmark comparison — order of magnitude only.** The
   only benchmark data available (Thao et al. 2023) is for a **knit polo
   shirt** at two Vietnamese factories, covering **7-12 assembly classes**
   and explicitly **excluding buttonhole/button-sew time**, whereas this
   library's Classic variant is a **woven dress shirt** including all
   buttonholes and buttons. The comparison table is labelled accordingly
   ("DIFFERENT PRODUCT, partial coverage") and the resulting ratio (0.85–1.9×
   the comparable factory's SAM total) is reported only as a plausibility
   check — same neighbourhood, not proof of accuracy. No product-matched,
   non-proprietary, element-level woven-shirt benchmark is available to this
   project (see `benchmark_report.md`'s own Phase-0 coverage-gap finding);
   closing that gap requires real factory time studies, per
   `engine_phase1_report.md` §5.

## Known limitations

- `SIZE_CLASS` (handling distances/masses per component) is `ESTIMATE`-tier
  engineering judgement, not sourced or fitted — exactly the kind of
  coefficient `calibration_fit.py` exists to correct once real
  `element_observation` time-study rows are available for these operations.
- `BLOUSE_COLLARLESS` reuses the shirt's own body pattern with only the
  collar/neckline and buttonhole set changed; it is not a genuinely distinct
  blouse silhouette (darted/princess-seamed body, gathered cap sleeve, its
  own grading). Building that needs its own Phase-0-style points-of-measure
  derivation from a real blouse spec, which was out of scope this phase.
