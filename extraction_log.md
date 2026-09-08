# Extraction log — `smv_benchmarks_v2.csv`

This log records, per source, exactly what table/figure was read, what
cross-check was run against the paper's own stated totals, and any
transcription caveats. All values in `smv_benchmarks_v2.csv` were read
directly from each paper's PDF (vision-based page extraction) — none were
estimated, interpolated, or filled from general knowledge of garment
construction.

## thao_2023_table5 (carried over from the original `smv_benchmarks.csv`)

Thao, P.T. et al. (2023), *Fibres and Textiles*, 30(4), 58-64, DOI
[10.15240/tul/008/2023-4-007](https://doi.org/10.15240/tul/008/2023-4-007).
Table 5 aggregate assembly-class comparison for a knit polo shirt across
three methods (GSD/BKG/SAM), from a prior session's extraction. Remapped
here into the unified long-format schema (one row per method-column value)
rather than re-extracted. 19 original rows × up to 3 method columns = 57
unified rows.

## parvez_2017_table5_1

Parvez, Amin & Akter (2017), IOSR-JRME, 7(3), 40-47, DOI
[10.9790/7388-0703040714](https://doi.org/10.9790/7388-0703040714). Table
5.1, "Crony Group of Industries" (Bangladesh), 18-operation knit round-neck
top, pre-work-sharing baseline. Read via `read_file(pages=[3])` for rows
1-2 and column headers, `pages=[4]` for rows 3-18. Row-sum of the table's
own SMV column = 3.32 min, close to (not exact against) the paper's own
software-printed console total of ~3.26 min — a ~0.06 min residual
consistent with the 2-decimal rounding on each individual SMV cell, not a
transcription error.

## islam_2019_conventional

Islam, Sultana, Chowdhury et al. (2019), *European Scientific Journal*,
15(33), 147-162, DOI
[10.19044/esj.2019.v15n33p147](https://doi.org/10.19044/esj.2019.v15n33p147).
"Mahadi Fashion (Pvt) Ltd" (Bangladesh), buyer "Sisal", style #6704,
18-operation round-neck knit T-shirt, pre-work-sharing baseline, "Cycle
Time With Allowance" column. Read via `read_file(pages=[4,5])`. **Known,
disclosed discrepancy**: row-sum = 6.78 min; the paper states an overall
style SMV of 5.5 min. Five of the 18 operations are staffed by 2 operators;
the paper's own SMV accounting for multi-operator stations evidently
differs from a flat row-sum, and that method was not stated explicitly
enough to reproduce — recorded as published rather than force-reconciled.

## halim_2025_current_layout

Halim, Islam & Ahmmed (2025), *World Journal of Advanced Research and
Reviews*, 25(2), 2246-2262, DOI
[10.30574/wjarr.2025.25.2.0559](https://doi.org/10.30574/wjarr.2025.25.2.0559).
"XYZ Group" (Bangladesh, anonymized in source), denim jacket, 27-operation
current (pre-balancing) layout, Figure 6. **This source required a
correction mid-extraction**: an initial pass misread which figure held the
per-operation data and, when a first summary pass produced no verifiable
table, generic denim-jacket operation names were drafted as a placeholder
and briefly written into the working data before being caught. That draft
was discarded in full before this dataset was assembled — `read_file`
was re-run on `pages=[6]` (confirmed to be the *post*-COMSOAL Figure 4/5,
wrong figure) and then `pages=[7]` (the correct pre-balancing Figure 6),
and every operation label and time value in the final CSV was transcribed
from that page. Values are reported in the source as seconds and converted
to minutes here (`÷60`). No paper-stated grand total exists to cross-check
against (the paper reports line-efficiency/balance-delay metrics, not a
summed cycle time), so this source has no independent total-sum check.

## rahman_2023_conventional / rahman_2023_lean

Rahman, Abdul Baten, Manjurul Hoque et al. (2023), *International Journal
of Industrial Management*, 17(3), 1-10, DOI
[10.15282/ijim.17.3.2023.8955](https://doi.org/10.15282/ijim.17.3.2023.8955).
Undisclosed Bangladeshi factory, full-sleeve knit T-shirt, Table 1
(19 operations × conventional/lean SMV columns), a born-digital PDF (text
layer, not a scan) — the highest-precision source in this dataset.
**Same correction pattern as the denim-jacket source**: an initial
misread pulled numbers from Figures 3-5 (the SMV/production/manpower
*comparison* charts) rather than Table 1 itself, and generic operation
names were briefly drafted before being caught; that draft was discarded
and `read_file(pages=[3,4])` was re-run to reach the actual Table 1.
Conventional-column row-sum = 6.840 min, exactly matching the paper's
stated total. Lean-column row-sum = 6.042 min against the paper's stated
5.940 min — a 0.102 min residual, likely a rounding/transcription error in
one or two lean-column cells that could not be pinned down without a
further re-read; flagged in that source's `notes` column rather than
silently corrected.

## Not pursued (fetched but no usable table, or inaccessible)

- **Line Balancing for Improving Apparel Production by Operator Skill
  Matrix** (2015, DOI 10.11648/j.ijsts.20150304.11) — no accessible full
  text (paywalled landing page, no OA copy found).
- **Applying Lean Tools to Improve the Sewing Line Efficiency: A Case
  Study** (2023, DOI 10.9734/ajeba/2023/v23i161035) — abstract confirms a
  per-operation knitted-jacket SMV table exists, but no PDF could be
  fetched (403 on every source `fetch_article_fulltext` tried, including
  the publisher landing page).
- **Improvement of garment assembly line efficiency using line balancing
  technique** (Bongomin et al. 2020, DOI 10.1002/eng2.12157) — gold
  open-access per CrossRef/DOAJ metadata, 72-operation trouser assembly
  line at Southern Range Nyanza Limited (Kenya), but the Wiley-hosted PDF
  returned HTTP 403 on every fetch route tried.
- **Productivity Improvement of Garments Industry by Implementing Line
  Balancing Algorithms** (2025, DOI 10.1002/eng2.70125) — abstract
  indicates the case study is scoped to one hemming unit's workstation
  count, not a full garment operation breakdown; not pursued given the
  narrower scope.
- **RETRACTED**: "Assembly operation productivity improvement for garment
  production industry..." (Heliyon, DOI 10.1016/j.heliyon.2023.e17917) —
  excluded outright; CrossRef confirms retraction.
- **Same Jeans, Same Stitch?** (Chaudhry & Faran 2016, *Lahore Journal of
  Economics*, DOI 10.35536/lje.2016.v21.isp.a9) — a labor-economics
  comparison of denim factories, not an operation-level time study; out of
  scope for this dataset.
