# Phase 0 — Benchmark Literature Report

## Objective

Ground the synthetic SMV engine's outputs against **published, non-proprietary** timing
data from the garment-industry literature, without extracting or reproducing any
predetermined-motion-time (PMTS) element table — those tables (GSD/MTM/MODAPTS-style
code → TMU mappings) are licensed IP and are explicitly out of scope for this project.

## Source located and used

**Thao, P.T. et al., "Improve Building Database on the Operation Process and Performance
Time for Sewing Operations of Knitted Garment Products," *Fibres and Textiles*, 30(4),
2023, 58–64.** DOI: `10.15240/tul/008/2023-4-007`.

This paper reports **aggregate assembly-class comparisons** of sewing time for
Polo-Shirt production, measured three ways at two Vietnamese garment factories:

- **GSD** — General Sewing Data (predetermined-time-system estimate)
- **BKG** — a traditional-company floor time-study/observation method
- **SAM** — Standard Allowed Minute, the shop-floor "ground truth" time actually
  used for costing and line-balancing

The paper's own Tables 5 and 6 give these aggregate figures (in seconds) per
assembly class (collar, placket, sleeve opening, bottom, shoulder/armhole/side seams,
etc.) at **Ha Nam Hanosimex Co.** (traditional line) and **Tinh Loi Garment Co.**
(modernized line), plus the ratio coefficients `k = BKG/GSD` and `k' = SAM/GSD` per
class and their per-factory averages.

We extracted **only these aggregate class-level rows and ratios** into
`smv_benchmarks.csv` (19 rows). We reproduced the paper's own reported average
ratio (`k̄ ≈ 1.55` at Hanosimex) from our transcribed rows to 3 decimal places
(1.546), confirming the transcription is faithful to the source.

We deliberately did **not** extract the paper's Tables 7–8, which list an
element-by-element GSD/BKG breakdown (motion codes such as `AS2H`, `FUNF`, `MAP2`,
`AM2P`, with TMU values) for the armhole-seam operation — that is exactly the type
of PMTS element-code table this project excludes.

## Sources reviewed but not used for benchmark data

- **Nguyen, T.B.N. et al., "Designing Software to Analyze Sewing Process of
  Industrial Knitted Products," *CSSE* 44(2), 2023.** DOI:
  `10.32604/csse.2023.026502`. Contains a full 8-class GSD element/code/TMU
  description table (its own Table 5) — a genuine PMTS element table. We read
  this table to confirm its nature but **extracted none of its content**; it is
  excluded from all deliverables.
- **"An Improved Approach to Line Balancing for Garment Manufacturing,"
  *Vietnam Journal of Mechanics*.** DOI: `10.31357/vjm.v2i1.3645`. Discusses
  T-shirt line balancing via stochastic simulation (ARENA); does not report
  usable SAM/GSD/BKG comparison figures — it explicitly does not use SMV values,
  instead modeling processing-time distributions directly.
- **"Application of Lean Manufacturing in a Sewing Line for Improving Overall
  Equipment Effectiveness (OEE),"** *AJIBM* 8(9), 2018. DOI:
  `10.4236/ajibm.2018.89131`. An OEE/line-efficiency case study with no directly
  comparable per-operation timing figures.

## Cross-check against the synthetic engine

`model_vs_benchmark_crosscheck.csv` runs the reconstructed `effective_spm.py`
kinematic model over our own `seam_geometry.json` operations that are structurally
closest to the published classes (shoulder/yoke, sleeve, armhole, side seam), at
size M, using the machine classes and rated speeds from `machine_classes.csv`.

| Component | Model sew time (s) | Published SAM range, same class (s) |
|---|---|---|
| Armhole seam | 18.9 | 36.0 – 55.8 |
| Side seam | 8.8 | 21.0 – 76.2 |
| Shoulder/yoke | 3.5 – 8.1 | 21.0 – 37.4 |

This is a **plausibility check, not a validation**: our garment (woven dress
shirt) and the published garment (knit Polo-Shirt) differ in fabric, seam
length, ply count, and assumed machine class, so absolute agreement isn't
expected. The comparison confirms the two are in the same **order of
magnitude** (single-digit to tens of seconds per seam) rather than off by 10×
or more, which would indicate a modeling error. It does **not** replace a
proper calibration pass — that remains a Phase 1 activity once real production
data is available (see completion report).

## IP-safety statement

No element-level predetermined-motion-time code, TMU value, or element
description was extracted, transcribed, stored, or used anywhere in this
project's deliverables. Only factory-level aggregate class comparisons and
their derived ratio coefficients — already published as summary tables in a
peer-reviewed, openly accessible article — were used, with full citation and
table provenance recorded per row in `smv_benchmarks.csv`.
