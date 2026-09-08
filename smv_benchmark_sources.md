# SMV/SAM Benchmark Literature — Synthesis

## Objective

Extend the project's published-benchmark dataset (`smv_benchmarks.csv`, 19 rows
from one source) with additional operation-level SMV/SAM/cycle-time tables
from peer-reviewed, openly accessible garment-industry case studies — the same
IP-safety scope as the original Phase 0 benchmark work: **aggregate,
factory-reported timing figures only, never a predetermined-motion-time
element/code table** (GSD/MTM/MODAPTS motion-code → TMU mappings remain
licensed IP and out of scope).

The result is `smv_benchmarks_v2.csv`, 158 rows across 5 distinct papers (6
source-batches, since one paper reports a conventional/lean before-after pair
as two columns). See `extraction_log.md` for the row-by-row provenance and
per-source cross-check against each paper's own stated totals.

## What the literature actually offers

Searching OpenAlex across ~14 queries spanning line-balancing, work-study,
lean-manufacturing, and SMV/SAM terminology in the garment-sewing literature
turned up a fairly narrow, recurring genre: **industrial-engineering case
studies at named or anonymized Bangladeshi/South-Asian ready-made-garment
factories**, almost all structured around line-balancing or lean-manufacturing
interventions, each reporting a per-operation time table as an input to their
balancing/lean analysis (not as an end in itself). This is a real, useful, but
structurally narrow literature:

- **No paper publishes a standalone "SMV reference table" for its own sake.**
  Every usable table found here is a byproduct of a line-balancing or lean
  case study — the operation times exist because the authors needed them to
  compute workstation counts, balance delay, or line efficiency.
- **Knit garments dominate.** All 6 source-batches in this dataset are knit
  construction (round-neck T-shirts, a full-sleeve T-shirt, a polo shirt, a
  denim jacket) sewn on overlock/flatlock/single-needle machines. **None** are
  woven dress-shirt construction, which is what this project's own engine
  currently models (`seam_geometry.json`'s `CLASSIC` style). This is the same
  construction-type mismatch the original benchmark report already flagged for
  its one polo-shirt source — it simply persists across every new source
  found, because the literature itself skews toward knit-garment case studies.
- **Bangladesh dominates the geography.** 4 of 5 papers report data from
  Bangladeshi factories (one anonymized as "XYZ Group"); the fifth
  (`parvez_2017`) is from "Crony Group of Industries," also Bangladesh. No
  paper surfaced with comparable operation-level detail from other major
  garment-producing regions (Vietnam, outside the original Thao et al. source;
  Cambodia; Central America) despite targeted queries.
- **Trouser/denim coverage is real but thin.** The denim jacket source
  (`halim_2025`) is the only non-T-shirt/polo garment with full operation-level
  detail. A promising 72-operation trouser-assembly case study at a named
  Kenyan factory (Bongomin et al. 2020, DOI `10.1002/eng2.12157`, gold OA per
  CrossRef/DOAJ) could not be retrieved — every fetch route returned HTTP 403
  on the Wiley-hosted PDF. This is a genuine coverage gap, not a decision to
  exclude trousers.

## Per-source notes

| source_id | Garment | n rows | Method | Quality note |
|---|---|---|---|---|
| `thao_2023_table5` | Knit polo shirt | 57 | GSD / BKG / SAM, 3-way factory comparison | Carried over unchanged from the original benchmark file; own-average cross-check (k̄≈1.55) previously verified. |
| `parvez_2017_table5_1` | Knit round-neck top | 18 | Stopwatch time study (10-cycle avg × rating × allowance) | Scanned PDF (vision-read); row-sum (3.32 min) close to, not exact against, the paper's own console-printed total (3.26 min) — consistent with 2-decimal rounding on 18 cells. |
| `islam_2019_conventional` | Knit round-neck T-shirt | 18 | Time study / capacity chart | Row-sum (6.78 min) does **not** match the paper's stated style SMV (5.5 min); 5 of 18 operations use 2 operators and the paper's own multi-operator SMV accounting could not be reverse-engineered from the text given. Flagged, not corrected. |
| `halim_2025_current_layout` | Denim jacket | 27 | Time-and-motion study (baseline layout) | Born-digital PDF (Figure 6); values reported in seconds, converted to minutes here. No paper-stated grand total to cross-check (paper reports line-efficiency metrics instead). |
| `rahman_2023_conventional` | Knit full-sleeve T-shirt | 19 | Time study + process-flow analysis, conventional layout | Born-digital PDF (Table 1), highest-precision source; row-sum (6.840 min) matches the paper's stated total **exactly**. |
| `rahman_2023_lean` | Knit full-sleeve T-shirt | 19 | Same, post-5S/line-balancing/JIT layout | Row-sum (6.042 min) vs. paper's stated 5.940 min — 0.102 min residual, likely a 1-2 cell rounding/transcription issue not resolved without a further re-read. Flagged. |

Two of these five extractions (`halim_2025`, `rahman_2023`) required a
mid-process correction: an initial read of the wrong figure/table in each PDF
produced plausible-sounding but **fabricated** operation names and values
before the correct table was located and re-transcribed. Both draft versions
were discarded in full; see `extraction_log.md` for exactly what was misread
and how it was caught. This is disclosed here because it bears directly on
how much to trust the rest of this dataset — the same discipline (re-verify
against the actual rendered page, not the initial summary) was then applied
retroactively to every other new source before this file was finalized.

## Sources reviewed but not usable (see `extraction_log.md` for detail)

- Operator Skill Matrix line-balancing paper (2015) — no accessible full text.
- "Applying Lean Tools to Improve the Sewing Line Efficiency" (2023) — abstract
  confirms a per-operation knitted-jacket SMV table exists; PDF unreachable
  (403 on every route).
- Bongomin et al. (2020) NYTIL trouser line-balancing paper — gold OA per
  metadata, Wiley PDF returns 403.
- "Productivity Improvement... Line Balancing Algorithms" (2025) — scoped to
  one hemming unit's workstation count, not a full garment breakdown.
- The Bahir Dar Ethiopia paper (Heliyon) — **excluded outright: retracted**,
  confirmed via CrossRef.
- "Same Jeans, Same Stitch?" (Chaudhry & Faran 2016) — labor economics, not an
  operation-level time study.

## What this dataset does and does not support

**Supports**: an expanded, cited, order-of-magnitude plausibility check of the
engine's pure-machine-time model against real factory data (see
`model_vs_benchmark_crosscheck_v2.csv`/`.png`) — every matched operation class
lands within the published range's order of magnitude. It also gives future
work a starting point if a knit-garment style is ever added to the engine's
own library, since this data is knit-native where the engine is currently
woven-native.

**Does not support**: calibrating the engine's own `Gamma_skill`,
`a_steer`/`b_steer`/`k_R`, or allowance coefficients — those require raw,
per-element observations tied to the engine's own taxonomy codes (see
`time_study_schema.json`), which no published paper reports at that
granularity. This is the same conclusion the original Phase 0 report reached,
now confirmed across 5 additional sources rather than 1: **operation-level
literature benchmarks validate totals; they cannot substitute for factory-floor
element-level calibration data.**
