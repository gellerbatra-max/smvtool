# Phase 0 (Engineering Foundation) — Completion Report

**Project:** Self-calibrating SMV (Standard Minute Value) engine for garment sewing time
**Scope of this report:** Phase 0 only — the three engineering-foundation tracks
(Motion model, Machine data, Benchmarks). Phase 1 (calculation engine) and any
application layer are explicitly out of scope, per the user's decision to finish
Phase 0 before continuing.

## Recovery context

This session resumed a prior session that was interrupted by a platform OAuth
error partway through Phase 0. The Motion-model track had completed and been
reviewed; the Machine-data and Benchmarks tracks had made substantial progress
but failed before saving deliverables. All recovered/rebuilt content in this
report was reconstructed from the interrupted session's own tool-call transcript
(not re-derived from scratch), and cross-checked byte-for-byte or numerically
against that transcript's own validation output wherever possible.

## Track 1 — Motion model (recovered, unmodified)

| File | Description |
|---|---|
| `motion_model.md` | Narrative motion-model specification |
| `element_taxonomy.json` | 23 elements, 30 global parameters, 5 engine constants |
| `allowance_policy.json` | 12 allowance categories |

**Status:** Fully complete and previously reviewed. Recovered by replaying the
original session's edit history programmatically; the reconstructed
`motion_model.md` matched the original saved artifact's byte count (52,161
bytes) exactly, and the taxonomy/allowance element counts matched the original
session's own validation checks. A reconciliation-arithmetic issue a reviewer
had flagged in the original session (allowance category sums) was confirmed
already corrected in the shipped `allowance_policy.json`.

## Track 2 — Machine data (rebuilt and validated)

| File | Description |
|---|---|
| `effective_spm.py` | Kinematic model: rated machine SPM → achieved average speed |
| `machine_classes.csv` | 17 machine classes + 7 attachments |
| `seam_geometry.json` | 21 seam operations + 6 cycle (buttonhole/button/bartack) operations across 10 garment components, for a men's woven dress shirt, sizes S–XXL |
| `effective_spm_model.png` | Two-panel figure: achieved speed vs. seam length by curvature/guidance class, and by representative shirt operations |

**Validation performed:**
- `effective_spm.py` reproduces the project's own grounded theoretical-maximum
  reference points (rated 5000 sti/min → 17.4 yd/min at 8 SPI, 9.9 yd/min at 14
  SPI) to within 0.25%.
- Every `machine_class` code referenced in `seam_geometry.json` resolves
  cleanly against `machine_classes.csv` (no dangling references).
- A machine-time crosscheck for size M gives **4.97 min (8,277 TMU)** of pure
  machine time (seam + cycle operations only — excludes handling and PF&D
  allowances, which belong to Pillars 2–3 of the full engine).
- Cross-referenced against published knit-Polo-Shirt SAM benchmarks (Track 3):
  model sew times for structurally comparable seams (armhole, side seam,
  shoulder/yoke) came out in the same order of magnitude as the published
  figures (single-digit to tens of seconds per seam), not off by 10× or more —
  a plausibility check, not a calibration.

**Provenance discipline:** every row/field in `machine_classes.csv` and
`seam_geometry.json` is tagged `SOURCED`, `DERIVED_GEOMETRIC`, or `ESTIMATE`.

## Track 3 — Benchmarks (new literature harvest)

| File | Description |
|---|---|
| `smv_benchmarks.csv` | 19 rows of published GSD/BKG/SAM aggregate assembly-class comparisons (Polo-Shirt, two Vietnamese factories) with per-row citation |
| `model_vs_benchmark_crosscheck.csv` | Synthetic-model sew times for the structurally closest operations, for comparison against the published SAM ranges |
| `benchmark_report.md` | Full literature review: what was used, what was deliberately excluded, and why |

**Key finding:** the only usable open-access source with legitimate *aggregate*
(non-element-level) SMV benchmark data was Thao et al. 2023 (DOI
`10.15240/tul/008/2023-4-007`), reporting GSD/BKG/SAM comparisons by assembly
class at two garment factories. Two other candidate papers were read in full
and found to contain genuine predetermined-motion-time **element** tables
(motion codes + TMU values) — that content was explicitly excluded from every
deliverable.

## IP-safety statement (project-wide)

No predetermined-motion-time-system (GSD/MTM/MODAPTS-style) element table —
codes, TMU values, or element descriptions — has been extracted, transcribed,
stored, or used anywhere in this project's deliverables, at any point across
either session. This was verified by:
1. Explicit keyword/pattern scans of all three Machine-data files (matches
   found only inside their own disclaimer text).
2. Manual review confirming two candidate literature sources containing actual
   PMTS element tables were read for context only, with zero data extracted.
3. Every `smv_benchmarks.csv` row carrying full citation and source-table
   provenance, restricted to the source paper's own *aggregate* comparison
   tables (Tables 5–6), never its element-level breakdown (Tables 7–8).

All machine timing in this project's synthetic engine (`effective_spm.py`)
is derived from **first-principles kinematics** (rated machine speed, stitch
density, curvature/guidance-driven speed derates, ramp physics) calibrated
against manufacturer spec-sheet values and published aggregate SAM data — not
from any licensed predetermined-time database.

## Open items / calibration-pending gaps

- `effective_spm.py`'s derate coefficients (guidance caps, ramp efficiency,
  curvature classes) are currently `ESTIMATE`-tagged, informed by the
  order-of-magnitude benchmark check above but not fitted to real production
  data. Phase 1 should treat these as free parameters for calibration once
  actual factory time-study data is available (this is the "self-calibrating"
  half of the engine's design intent).
- `machine_classes.csv` mixes `SOURCED` (manufacturer spec-sheet) and
  `ESTIMATE` rows where no public spec exists — flagged per-row.
- The benchmark comparison uses a *different garment* (knit Polo-Shirt vs. our
  woven dress shirt) as the only available open-access aggregate source; a
  same-garment-type benchmark would tighten the plausibility check
  considerably and should be sought in Phase 1 if a suitable source appears.
- Handling time (Pillar 2) and PF&D allowances (Pillar 3) are represented by
  the completed Motion-model and Allowance-policy tracks but have not yet been
  integrated with Track 2's machine time into a single per-garment SMV total —
  that integration is Phase 1's first task (the calculation engine).

## Recommended next step

Phase 1: build the calculation engine that combines Pillar 1 (this report's
machine time), Pillar 2 (handling time, from `motion_model.md`/
`element_taxonomy.json`), and Pillar 3 (PF&D allowances, from
`allowance_policy.json`) into a single per-garment SMV, with the calibration
hooks needed to fit `effective_spm.py`'s ESTIMATE coefficients against real
factory time-study data as it becomes available.
