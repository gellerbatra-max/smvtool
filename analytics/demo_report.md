# Analytics demo -- CLASSIC shirt, size M

Style SMV: **12.5727 min** = 20954.5 TMU, across 27 operations (computed by `smv_assembly.assemble_style()` via `shirt_library.build_style_operations()` -- no numbers below are hardcoded; every one is a fresh engine call).

## 1. Line balance (RPW, chain precedence -- see line_balancing.py docstring)
- Requested workstations: 10; used: 10
- Bottleneck: workstation 6 at 1.5522 min
- Theoretical efficiency (sum SMV / (N x bottleneck)): 81.00%
- Achievable output: 38.65 garments/hour vs. target 45.0/hour (meets target: False; efficiency at target: 85.90%)
- Total idle time across stations: 2.9495 min
- Per-workstation detail: see demo_workstation_loads.csv; operation->workstation assignment: demo_line_balance.csv

## 2. Costing and production targets
- Labour rate: 3.20/hour, line efficiency: 80%
- Cost of make per garment (SAM x labour_rate/60 / efficiency): **0.8382**
- Output at 10 operators: 38.18/hour, 305.4 per 8h shift
- Daily labour cost at 10 operators: 256.00
- Operators required to hit 45/hour target: **12** (raw 11.79)
- Full detail: demo_costing.csv

## 3. What-if scenario: 'side_seam: Close side seam (felled or safety-stitch) (size M)'
Proposed change: swap the side-seam machine from FOA-401 (feed-off-arm chainstitch lapseamer) to OL-5T-SS (5-thread safety stitch) -- a real method-planning decision, recomputed by the engine, not looked up.

- Operation SMV: -0.0629 min (-17.11%)
- Style SMV: 12.5727 -> 12.5099 min (-0.0629 min, -0.50%)
- Bottleneck workstation: 6 -> 6 (+0.0000 min)
- Theoretical efficiency: 81.00% -> 80.59% (-0.405 pp)
- Cost per garment: 0.8382 -> 0.8340 (-0.0042)
- Full detail: demo_what_if.csv
