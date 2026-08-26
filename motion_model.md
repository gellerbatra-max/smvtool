# The Handling-Time Motion Model

**A parametric, calibratable model of manual handling time for woven-top sewing operations**

Specification version 0.1.0 — draft for implementation
Companion machine-readable files: `element_taxonomy.json`, `allowance_policy.json`

---

## 0. Scope, purpose and intellectual-property position

### 0.1 What this document specifies

This document defines the mathematical heart of the handling-time pillar of a synthetic SMV
engine for woven tops (shirts and blouses). It specifies:

1. a continuous parametric function that maps the *physical description* of a manual act
   (distance, tolerance, ply count, fabric properties, mass) to a *time in seconds*;
2. the complete parameter list, with symbol, physical meaning, units, plausible range,
   source, and an explicit status of either **literature-grounded** or **calibration-pending**;
3. the rules by which element times combine into operation basic time, including how manual
   guidance time and machine sewing time overlap;
4. the calibration procedure by which factory time-study data fits the free coefficients.

It does **not** specify machine (needle-running) time, which is the deterministic pillar
(`stitches = seam_length × stitch_density`; `time = stitches / SPM_effective`), nor the
web application, nor the operation library. It provides the interface those pillars consume.

### 0.2 The design commitment: compute, never look up

The defining architectural constraint is that **no element time is stored**. Every element
in the taxonomy is a *program of motion phases* whose arguments are physical quantities, and
every phase time is the value of a continuous function of those quantities. There is no table
anywhere in this specification of the form *(motion class, distance class) → time*.

This is not merely an IP hygiene measure, though it is that. It has three engineering
consequences that a lookup architecture cannot deliver:

- **Interpolation is free and principled.** A 17 cm reach to a 3.5 mm tolerance is computed,
  not rounded to the nearest tabulated class. Discretisation error, which in class-based
  systems is bounded below by the class width, disappears.
- **The model is falsifiable and fittable.** A parametric model has residuals. A factory can
  fit its own coefficients, compute the residual distribution, and know how good its standards
  are. A lookup table has no residual structure to examine.
- **Extrapolation is visible.** When a fabric or a tolerance falls outside the calibration
  envelope, the engine can say so, because the envelope is a region in a continuous parameter
  space. A lookup table silently returns its nearest class.

### 0.3 Intellectual-property position

This model is built exclusively on open, peer-reviewed motor-control and human-factors
literature, on published fabric-objective-measurement literature, and on openly published
apparel industrial-engineering practice. Every source is named in §9.

No licensed predetermined-motion-time database was consulted, transcribed, paraphrased or
used as a structural template. Specifically: no GSD code table or GSD TMU value appears in
this specification or in the companion JSON files; no MTM-1, MTM-2 or MTM-UAS data card
content appears, and in particular no distance-class TMU table of the GA/GB/GC/PA/PB/PC form
is reproduced in any code, data file or documentation of this project. The MTM data card is
copyright-protected and marked reprint-not-permitted; its *values* are therefore off-limits
while the *fact of its structure* — that predetermined-motion-time systems decompose work into
motion elements and assign each a time as a function of distance and difficulty class — is
established prior art that may be freely described, and is described here as such.

Where this specification refers to any predetermined-motion-time system it does so to
characterise a methodology, to explain a design choice, or to cite peer-reviewed academic
work *about* such systems. The relationship is one of independent reimplementation of a
public methodology on a public scientific basis.

The element codes, element names, parameter signatures, class taxonomies and granularity in
`element_taxonomy.json` are original to this project. They were designed from the physics and
the motor-control literature outward, and their granularity is set by what the parametric
functions can distinguish, not by any external code set.

### 0.4 Unit convention (mandatory)

Internal computation is in **seconds** and **millimetres**. Output is available in seconds,
minutes and TMU, using exactly:

| Relation | Value |
|---|---|
| 1 TMU | 0.0006 min |
| 1 TMU | 0.036 s |
| 1 s | 27.7778 TMU |
| 1 min | 1666.6667 TMU |

Some secondary web sources state 33.33 TMU/s. **That value is wrong and must never be used.**
The engine must assert `abs(TMU_per_s - 27.777778) < 1e-6` at start-up.

Parameter signatures accept distances in **centimetres** (the unit an industrial engineer
measures a workstation in) and tolerances in **millimetres** (the unit a garment tolerance is
specified in). Conversion to millimetres happens on entry: `mm = 10 × cm`.

All times produced by this model are **basic time at 100 % standard performance**. Rating is
therefore already applied; observed study times must be multiplied by `rating/100` before
being used in calibration. Allowances are applied afterwards per `allowance_policy.json`.

---

## 1. Why Fitts' law is the right foundation

### 1.1 The empirical law

Fitts (1954) established that the time to make a rapid aimed movement to a target is a linear
function of the logarithm of the ratio of movement amplitude to target width. The relationship
is one of the most robust quantitative regularities in experimental psychology; it has been
replicated across limbs, effectors, input devices, age groups and even under water, and it
remains the standard model of aimed movement seventy years on.

In the **Shannon formulation** (MacKenzie, 1989, 1992), which is now the standard form because
it never yields a negative index of difficulty and exhibits better empirical fit than the
original:

$$MT = a + b \cdot ID, \qquad ID = \log_2\!\left(\frac{D}{W} + 1\right)$$

where `MT` is movement time, `D` the movement amplitude (distance to the target centre),
`W` the target width along the movement axis, and `ID` the index of difficulty in bits.
The reciprocal `1/b` is the **throughput** or information-processing rate of the limb, in
bits per second.

Two earlier variants remain in the literature and are worth naming because they explain
why published coefficient values differ:

- Fitts' original: `ID = log₂(2D/W)`, which goes negative for `D < W/2`.
- Welford's two-part form: `ID = log₂(D/W + 0.5)`, which separates a distance-covering
  component from a target-acquisition component and often fits slightly better than the
  original.

**This specification uses the Shannon formulation exclusively**, for the non-negativity
property and its better reported fit. A model option to switch formulation is not provided:
mixing formulations across a coefficient set is a common source of silent error, since `a`
and `b` are not comparable between forms.

### 1.2 Why it is defensible for sewing, and where it is not

Fitts' law is a law about *aimed movement under a tolerance constraint*. That is precisely what
dominates the manual content of a sewing operation: bring the plies to the needle and set the
edge to a 2 mm seam margin; register a notch to a 1 mm tolerance; put the point of a collar
where the needle will catch it; drop a finished piece in a box (a 60 mm tolerance, hence a
fast movement). In each case the operator's time is set by how far the hand travels and how
tightly the endpoint must be controlled. This is the same causal structure that predetermined-
motion-time systems capture with distance-and-difficulty classes — which is why the class
structure of those systems is, in effect, a coarse discretisation of a Fitts surface.

Peer-reviewed work has examined this correspondence directly. A 2025 experimental assessment
of the MOST predetermined-motion-time system (*International Journal of Advanced Manufacturing
Technology*, doi:10.1007/s00170-025-15791-6, and the related conference paper *Evaluating the
Accuracy of the MOST Predetermined Motion Time System through Lab Experiments*) compared MOST
predictions against measured times and against Fitts-law-style regression models. Two of its
findings are directly load-bearing for this project. First, the classical predetermined-motion
approach carries measurable systematic error against observed times. Second, and more usefully,
**object weight was a statistically significant predictor of movement time that the
predetermined-motion system does not represent** — a gap the model in §3.4 closes explicitly.
That is a peer-reviewed argument that a fitted parametric model can outperform the class-based
approach it replaces, on the same tasks, using variables the class-based approach discards.

Three honest limitations must be stated, because each one drives a design decision:

1. **Fitts' law models transport and endpoint control, not grasp.** Closing the hand on three
   plies of slippery georgette and securing control of them is not an aimed movement. It is
   modelled here as a separate additive phase (§3.3) whose coefficients have no Fitts
   provenance and are therefore calibration-pending.
2. **Fitts' law is a law of unconstrained-path point-to-point movement.** Guiding fabric along
   a stitch line for 30 cm is a *path-constrained* movement, for which the correct model is the
   steering law (§2.2), not Fitts' law.
3. **Visual search and decision are outside its scope.** Inspection is modelled crudely and
   flagged as such (§3.7); if inspection is a material share of an operation it should be
   measured, not modelled.

A literature search for direct published applications of Fitts' law to garment sewing or
textile handling returned no such study. The published garment time-study literature is
overwhelmingly stopwatch-and-PMTS based; work such as Ren's *Study on Standard Time of Garment
Sewing Based on GSD* applies a licensed system rather than deriving from motor-control theory.
**This model is therefore a novel application of an established law to a domain where it has
not previously been fitted.** That is the project's contribution and also its principal risk:
the *functional forms* below are literature-grounded, but the *coefficient values* for sewing
specifically are not, and are marked accordingly. Nothing in this specification should be
presented to a customer as a validated sewing motion model until §8 calibration has been run
on real time studies.

---

## 2. The motion-phase primitives

Five primitives are sufficient to construct every element in the taxonomy. Each element is an
ordered program of phases; the element time is a declared combination of its phase times.

### 2.1 Point phase — discrete aimed movement

For transport, positioning, and corrective sub-movements:

$$t_{\text{point}} = \Big[\,a_L + b_L \cdot \log_2\!\left(\tfrac{D}{W} + 1\right)\Big]\cdot\lambda_m(m)\cdot\Phi_{\text{point}}(f) \;+\; c_{\text{lean}}\,\mathbb{1}[D > D_{\text{trunk}}]$$

with `D`, `W` in mm, `t` in s. The subscript `L` denotes the **limb class** selected by `D`
(§2.1.1); `λ_m` is the mass multiplier (§3.4); `Φ_point` the fabric-difficulty multiplier
(§3.5); and the indicator term charges trunk recruitment on reaches beyond the seated envelope.

Where an element requires `n` successive aimed acts at the same difficulty — registering two
match points, snipping four thread ends — the phase is evaluated once and multiplied by `n`.
This is exact under Fitts' law only if the acts are independent; the assumption is stated
rather than hidden.

#### 2.1.1 Limb-dependent coefficients

The throughput `1/b` depends strongly on which limb segment executes the movement. Langolf,
Chaffin and Foulke (1976), *An investigation of Fitts' law using a wide range of movement
amplitudes*, **Journal of Motor Behavior** 8(2):113–128, remains the canonical source: working
across amplitudes from roughly 0.25 cm to 30.5 cm, they reported information-processing rates
of approximately **38 bit/s for finger motion, 23 bit/s for wrist motion, and 10 bit/s for arm
motion** — i.e. `b ≈ 0.026, 0.043, 0.100 s/bit` respectively. Their amplitude range maps almost
exactly onto the working envelope of a sewing station, which is why their limb bands are
adopted here directly.

That finger figure is contested and must not be treated as settled. Balakrishnan and MacKenzie
(1997), *Performance differences in the fingers, wrist and forearm in computer input control*
(CHI '97, doi:10.1145/258549.258764), re-examined limb-segment bandwidth and obtained
**substantially lower** rates for the index finger than Langolf et al., attributing the
discrepancy partly to task and apparatus differences. The literature therefore brackets rather
than fixes finger throughput. This specification takes the Langolf value as a **lower bound on
`b_fin`** and treats the default as the geometric midpoint of the disputed span, flagged
calibration-pending.

At the whole-arm end, reported slopes for practised aimed movement cluster somewhat above the
Langolf lower bound. MacKenzie and Buxton (1994) report intercepts around 200–240 ms and slopes
around 167–225 ms/bit for point-and-click; MacKenzie et al. (CHI 2008, *An Error Model for
Pointing Based on Fitts' Law*) report `a ≈ 94 ms` averaged over participants. The default
`b_arm = 0.150 s/bit` (6.7 bit/s) is chosen inside that reported span.

| Limb class | Distance band `D` | Slope symbol | Default `b` (s/bit) | Throughput (bit/s) | Status |
|---|---|---|---|---|---|
| `FINGER` | ≤ 25 mm | `b_fin` | 0.055 | 18.2 | literature-bracketed, midpoint |
| `WRIST` | 25–120 mm | `b_wri` | 0.080 | 12.5 | literature-grounded |
| `ARM` | > 120 mm | `b_arm` | 0.150 | 6.7 | literature-grounded |

The band edges (25 mm, 120 mm) are engineering conventions of this project chosen to
approximate the anatomical transition between finger-only, wrist-rotation and shoulder-elbow
movement. They are editable and calibration-pending. The engine must produce a **continuous**
time across a band edge or standards will jump discontinuously for small changes in
workstation layout; §7.2 specifies the required blending.

### 2.2 Steer phase — continuous constrained guidance

Guiding fabric along a stitch line, feeding an edge into a folder throat, and running a match
along two edges are all *path-constrained* movements: the hand must stay inside a tunnel of
lateral tolerance `W` for a path length `L`. The governing model is the **steering law** of
Accot and Zhai (1997), *Beyond Fitts' law: models for trajectory-based HCI tasks* (CHI '97,
doi:10.1145/258549.258760), derived by integrating Fitts' law along a path:

$$t_{\text{steer}} = \Big[\,a_s + b_s \cdot ID_{\text{steer}}\Big]\cdot\Phi_{\text{steer}}(f),
\qquad ID_{\text{steer}} = \frac{L}{W}\left(1 + k_R\left(\frac{R_{\text{ref}}}{R}\right)^{1/3}\right)$$

The bracketed factor is the curvature augmentation. Accot and Zhai (1999) found circular
tunnels significantly harder than straight tunnels of equal length and width, and Nancel and
Lank's curvature-corrected steering law expresses this as movement time proportional to
$\int ds / (W R^{1/3})$ — the cube-root radius dependence adopted here. For a straight path
`R → ∞` and the augmentation vanishes.

Two properties of this phase make it the most important one in the whole model:

**It yields a guidance speed limit.** Ignoring the intercept, `t = b_s L / W`, so the
steady-state guidance speed is

$$v_{\text{guide}} = W / b_s$$

*Guidance speed is proportional to the tolerance the operator must hold.* A 4 mm topstitch
tolerance can be fed twice as fast as a 2 mm one. This is a falsifiable, physically meaningful
prediction and it is the single most valuable thing the steering law contributes: it is the
mechanism by which the engine explains the gap between rated and achieved machine SPM without
an empirical fudge factor (§5.2).

**It absorbs mechanical guidance correctly.** An edge guide, folder or template does not make
the operator faster at holding a tolerance; it *widens the tolerance the operator must hold*.
The taxonomy therefore models attachments as a multiplier on `W` (`guide_relief`), not as a
time discount. This is a structural claim worth testing during calibration: it predicts that
adding an edge guide to a 1 mm topstitch operation saves far more time than adding one to a
5 mm seam operation.

The default `b_s = 0.0133 s` is anchored to be physically consistent with the established
machine-time reference points. A 5,000 SPM head at 14 SPI covers 9.9 yd/min ≈ 151 mm/s of
seam; at 8 SPI it covers 17.4 yd/min ≈ 265 mm/s. Setting `b_s` so that a 2 mm guidance
tolerance yields `v_guide = 150 mm/s` puts operator guidance capability and machine capability
at parity in the fine-stitch-density case, and makes guidance the binding constraint at coarse
densities. That is the observed behaviour on a real line: coarse-density seams do not run at
the machine's rated speed. This anchoring is a **reasoned initial guess, not a measurement**,
and `b_s` is the first coefficient §8 calibration should refit, from observed feed speeds.

### 2.3 Grasp phase — acquiring control of plies

$$t_{\text{grasp}} = \Big[\,g_0 + g_{\text{ply}}\,\max(n_p - 1, 0)^{\gamma_p} + \varepsilon_{\text{extra}}\Big]\cdot\Phi_{\text{grasp}}(f)$$

`n_p` is ply count, `ε_extra` an element-specific additive (bundle extraction, edge separation).
The ply term is a continuous power law, deliberately not a table keyed by ply count. With
`γ_p = 1` it is linear in extra plies; `γ_p > 1` encodes accelerating difficulty. Fit `γ_p`
only when the factory's studies contain at least three distinct ply counts; otherwise hold it
at 1.0, because `g_ply` and `γ_p` are not jointly identifiable from two ply levels.

Grasp has no Fitts provenance. All three coefficients are calibration-pending.

### 2.4 Fixed phase — bounded process acts

$$t_{\text{fixed}} = t_{\text{base}}\cdot n_{\text{act}}\cdot\Phi_{\text{fixed}}(f)$$

For acts with no reach component and no tolerance-driven duration: a snip, a knot, a knee-lift,
a needle-position wheel turn, a reorientation through an angle. `t_base` comes from the physical
class tables in the taxonomy (`tool_class`, `tie_type`, `control_class`). These are **process
constants of the workstation and its tooling** — how long a thread nipper takes to close —
not motion-time data keyed by distance and difficulty. Every one is calibration-pending. They
are the cheapest values in the whole model to measure directly, and a factory should.

The pivot element uses a fixed phase with `t_base = k_θ · (θ/90°)`, a linear angle model.
Pastel (2006) treated a corner as a coupled steering-and-pointing problem and found corner
angle a significant determinant of movement time; the linear form here is the simplest
specification consistent with that finding and should be re-examined against data.

### 2.5 Cognitive phase — fixation and verification

$$t_{\text{cog}} = t_{\text{look}}\cdot k_{\text{class}}\cdot n_{\text{checks}}$$

Deliberately the least mechanistic part of the model. Visual search obeys no analogue of
Fitts' law that this specification can defensibly import. `t_look` is a single global,
calibration-pending, and `k_class` a small ordinal multiplier. If a factory's studies show
inspection is a material share of an operation time, it should be measured directly and this
phase treated as a placeholder.

---

## 3. The modifier terms

The modifiers are the part of the model that replaces the licensed lookup tables' notion of
"difficulty class". Each is a continuous function of a *measurable physical property* of the
work, not an analyst's ordinal judgement.

### 3.1 Precision: the target width `W`

`W` is not a modifier at all — it is the Fitts target width, and it carries the entire
precision effect through the logarithm. This is the model's most important economy: what a
class-based system represents as separate difficulty codes, this model represents as a single
continuous variable with a physical unit (millimetres of tolerance).

The `precision_class` table maps named engineering tolerances to `W` in mm: from `P0` (toss
into a box, 60 mm) through `P2` (standard seam-edge alignment, 6 mm) to `P4` (stripe or check
match, 1 mm). These are **garment tolerances**, defined by this project from garment
specification practice. They are not time values and they are editable.

Where the tolerance is a style specification the planner already knows — a seam margin, a
topstitch margin, a folder throat width — the signature takes it in millimetres directly and
bypasses the class table.

### 3.2 Ply count

Ply count enters twice, and it is important not to conflate the two effects:

- in the **grasp** phase, through the power-law separation term (§2.3): more plies are harder
  to pick up and separate;
- in **mass**, since more plies weigh more (§3.4).

Ply count does *not* enter the point-phase index of difficulty. Adding a ply does not change
the distance to the target or the tolerance at the target. This is a substantive modelling
claim and calibration should test it: if residuals on point-dominated elements correlate with
ply count, the claim is wrong and a `W`-narrowing ply term is needed.

### 3.3 Grasp complexity

Handled entirely by the `ε_extra` argument of the grasp phase and the `bundle_state` parameter:
`g_bundle` is charged when the ply must be peeled from a tied or clamped bundle or separated
from fused cut edges. Calibration-pending.

### 3.4 Mass and bulk

$$\lambda_m(m) = 1 + \kappa_m\,\log_2\!\left(1 + \frac{m}{m_{\text{ref}}}\right)$$

Logarithmic, matching the pattern reported in the object-weight literature. Hagadorn (2004),
*The Effects of Object Weight and Three-Dimensional Movement on Human Movement Time and Fitts'
Law* (RIT thesis), found movement time increased with object weight in a logarithmic pattern;
the MOST assessment cited in §1.2 found object weight a statistically significant predictor
that the predetermined-motion system omits. Recent work on virtual-to-physical load
transformation likewise reports load effects on movement time and perceived difficulty.

The **direction and functional form are literature-grounded; the magnitude `κ_m` for
sub-kilogram garment parts is calibration-pending.** With the default `κ_m = 0.05` and
`m_ref = 100 g`, a 100 g panel costs 5 % over a massless movement and a 2 kg bundle costs
about 22 %. Those are plausible but unverified.

Note that mass enters as a multiplier on the *loaded* movement only. The taxonomy's
out-and-back structure (empty reach out, loaded return) exists so that this asymmetry is
represented rather than averaged away.

### 3.5 Fabric handling difficulty

This is where the model earns or loses its credibility, because "limp, slippery cloth is
harder to handle" is exactly the kind of knowledge that licensed systems encode as difficulty
codes and that this project must derive instead.

**Descriptors.** Three measurable fabric properties, each normalised logarithmically against a
reference fabric so that the reference has all descriptors zero and multiplier unity, and each
**rectified at zero** so that it is a one-sided penalty:

$$z_{\text{limp}} = \max\!\left(0,\ \log_2\frac{B_{\text{ref}}}{B}\right), \qquad
z_{\text{slip}} = \max\!\left(0,\ \log_2\frac{\mu_{\text{ref}}}{\mu}\right), \qquad
z_{\text{bulk}} = \max\!\left(0,\ \log_2\frac{t}{t_{\text{ref}}}\right)$$

The rectification is not cosmetic. Without it, the credit for being crisper or grippier than
the reference can cancel a genuine bulk penalty: in the specification smoke test (§8.5)
brushed flannel — stiffer, grippier *and* bulkier than poplin — computed as **faster** than
poplin, which is physically wrong. Rectifying makes `Φ` monotone non-decreasing in every
difficulty descriptor, which is the behaviour an industrial engineer will expect and audit
against. The consequence to accept deliberately: the reference fabric becomes the
easiest-handling point in the model, so it must be a genuinely easy, well-behaved cloth (crisp
cotton shirting poplin) rather than an average of the factory's range. With rectification
`Φ_min` is unreachable from the descriptors and survives only as a guard rail.

where `B` is bending rigidity (μN·m), `μ` the surface coefficient of friction (KES-F `MIU`),
and `t` single-ply thickness (mm). Larger `z_limp` means limper; larger `z_slip` means more
slippery; larger `z_bulk` means bulkier. The reference fabric is crisp cotton shirting poplin.

These are the standard quantities of **fabric objective measurement**: the KES-F system
(Kawabata) measures bending, shear, surface friction, compression and tensile properties, and
the FAST system (CSIRO) was developed as a simpler industrial alternative measuring bending
rigidity, extensibility, compression and dimensional stability specifically for tailorability
assessment. The published sewability and fabric-handle literature associates low bending and
shear rigidity with difficulty in making-up — distortion during cutting and sewing, poor
control of limp fabric, seam pucker — and the two instruments have a published quantitative
relationship for bending rigidity. Surface friction is the standard measure of slipperiness,
and object-handling research reports that slippery objects require significantly more time to
manipulate than high-friction ones.

**Multiplier.** A single fabric-sensitivity vector, scaled per phase type:

$$\Phi_{\text{phase}}(f) = \mathrm{clamp}\Big(1 + s_{\text{phase}}\big(\phi_L z_{\text{limp}} + \phi_S z_{\text{slip}} + \phi_B z_{\text{bulk}}\big),\ \Phi_{\min},\ \Phi_{\max}\Big)$$

with phase scales `s_grasp = 1.0`, `s_point = 0.7`, `s_steer = 0.5`, `s_fixed = 0.3`,
`s_cog = 0`. The ordering encodes a physical claim: fabric properties bite hardest when you
are trying to get hold of the cloth, less hard when transporting it, less again when guiding
it along a guide, and not at all when looking at it.

This structure was chosen for **identifiability**. A per-element fabric table would need
dozens of coefficients that no realistic factory data set could constrain. Three sensitivities
plus four phase scales — seven numbers — can be fitted from a few dozen well-designed studies
spanning fabric types.

**Status.** The *direction* of each effect is literature-supported. The *magnitudes*
`φ_L, φ_S, φ_B` and all four phase scales are **calibration-pending**. The clamps `Φ_min`,
`Φ_max` are guard rails against extrapolation outside the calibration envelope, not physical
quantities; the engine must flag any element whose `Φ` was clamped, because a clamp means the
model is being asked about a fabric it has not been taught.

The nine fabric classes in the taxonomy carry *nominal* descriptor values typical of the
qualities named (poplin, lawn, georgette, satin, twill, linen, flannel, stretch shirting, fused
component). These are literature-typical values, **not measurements of any factory's lots**,
and are flagged as such. A factory with FAST or KES-F access should replace them with its own
measurements; a factory without should at minimum rank its own qualities against the reference.

### 3.6 Bimanual coordination

Sewing is a two-handed craft and a model that sums both hands' times will overstate every
matching operation.

Kelso, Southard and Goodman (1979), *On the nature of human interlimb coordination*
(**Science** 203:1029–1031) and the companion *JEP: Human Perception and Performance*
5:229–238, established the governing finding: when the two hands move simultaneously to targets
of **disparate** difficulty, the movements are performed **together**, with the easier hand
slowing to accommodate the harder one. The limbs behave as a coupled unit rather than as
independent effectors.

Shea, Boyle and Kovacs (2011), *Bimanual Fitts' tasks: Kelso, Southard, and Goodman, 1979
revisited* (**Experimental Brain Research**, doi:10.1007/s00221-011-2915-5), replicated the
overall coupling pattern while showing that synchrony is not perfect — there are systematic
departures from strict simultaneity. The model therefore uses `max()` plus a small penalty
rather than pure `max()`:

$$t_{\text{bimanual}} = \max(t_{\text{left}}, t_{\text{right}})\cdot(1 + \epsilon_{\text{bi}})$$

`ε_bi` default 0.05, plausible range 0–0.20, magnitude calibration-pending. The functional
form is literature-grounded. The audit trail must record which hand was limiting: that record
is directly actionable, because an operation whose time is set by one hand repeatedly is a
workplace-layout problem.

Elements declare their own bimanual mode: `single_hand`, `max_with_coupling_penalty`,
`coupled_two_hand_single_task` (both hands on one object, e.g. guiding a seam — no max applies,
the phase time already describes the two-handed act), or `not_applicable`.

### 3.7 Operator group

`Γ_skill`, a multiplicative factor on all handling time, default 1.00 and **held at 1.00 for
the standard-performance definition**. It exists so that a factory maintaining cohort-specific
standards (a learner line, a sample room) can express that without corrupting the engineered
standard. Any SMV computed with `Γ_skill ≠ 1` must be labelled as a cohort standard, never
published as the style SMV.

---

## 4. Assembled element time

For element `e` with phase program `P(e)`:

$$t_{\text{basic}}(e) = \Gamma_{\text{skill}}\cdot \mathcal{C}_e\big(\{t_p : p \in P(e)\}\big)$$

where `C_e` is the element's declared combination rule: `sum`, `sum × n_events`,
`sum × n_folds`, `sum × n_passes`, or `sum_then_bimanual` (phases flagged simultaneous
combined by §3.6, the remainder summed).

The taxonomy defines **23 elements**, listed in §6.

---

## 5. Operation assembly

### 5.1 Basic time of an operation

$$BT_{\text{op}} = \underbrace{\sum_{e \in H} t_{\text{basic}}(e)}_{\text{non-overlapping handling}}
+ \underbrace{\sum_{j \in S} \max\big(t_{\text{mach}}(j),\, t_{\text{guide}}(j)\big)}_{\text{seam segments}}
+ \underbrace{\frac{1}{N_b}\sum_{e \in B} t_{\text{basic}}(e)}_{\text{bundle, amortised}}$$

with `N_b` the bundle size.

### 5.2 The machine-overlap rule

This is the most consequential rule in the specification. For each sewn seam segment `j`, the
machine is running while the operator guides. **These times overlap; they must not be added.**

$$t_{\text{seam}}(j) = \max\big(t_{\text{mach}}(j),\ t_{\text{guide}}(j)\big)$$

where `t_mach(j)` comes from the machine pillar (`stitches/SPM`) and `t_guide(j)` is the
`guide_seam` element time from the steering law.

The consequence is that **achieved stitch rate is an output of the model, not an input**:

$$\text{SPM}_{\text{achieved}}(j) = \frac{60\,\cdot\,\text{stitches}(j)}{t_{\text{seam}}(j)}$$

This is how the engine explains, from first principles, the established observation that rated
machine SPM is never the achieved average. Where the tolerance is tight or the stitch density
coarse, `t_guide > t_mach` and the operator's guidance capability is binding — the machine
waits for the hands. Where the stitch density is fine, `t_mach > t_guide` and the machine is
binding. Acceleration, curve, pivot and guidance losses are then not a single empirical
derating factor but *separately identifiable* effects: the pivot element charges corner time
explicitly, the curvature term charges curve time explicitly, and the steering law charges
tolerance-driven guidance time explicitly.

**The engine must record, for every seam segment, which of the two was binding.** This is the
model's most useful diagnostic output: a line where guidance binds on most seams has a
tolerance, guide-attachment or training opportunity, not a machinery opportunity. It is also
the model's most falsifiable prediction, and the first thing §8 validation should check against
observed feed speeds.

### 5.3 No double counting of hand travel

The taxonomy charges hand-return travel inside `dispose_and_stack` and inside the out-and-back
structure of the acquire elements. An operation model must not charge the same travel twice.
The validator flags any operation in which a dispose element is immediately followed by an
acquire element whose reach exceeds the dispose distance, as that pattern is likely a double
count.

### 5.4 Standard time and style SMV

$$ST_{\text{op}} = \sum_{e} BT_e\left(1 + \sum_{c \in A(e)} r_c\right), \qquad
SMV_{\text{style}} = \sum_{\text{op}} ST_{\text{op}}$$

Allowances are applied **per element**, never as a single lump on the operation. That is what
makes machine-delay allowance correct: it can be restricted to the machine-bound component.
See `allowance_policy.json` and §7.

---

## 6. Element taxonomy summary

Full parameter signatures, phase programs, defaults, domains and units are in
`element_taxonomy.json`. The 23 elements:

| Code | Name | Dominant phase | Notes |
|---|---|---|---|
| `HAG` | `acquire_part` | point + grasp | single part, no matching |
| `HAM` | `acquire_and_match` | point + grasp, bimanual | the workhorse of assembly; registers `n` match points |
| `HAB` | `separate_ply_from_bundle` | grasp | limiting act is ply separation, not transport |
| `HTR` | `transport_part` | point | move without matching |
| `HPF` | `present_under_foot` | point + fixed | sets edge at needle, lowers foot |
| `HGD` | `guide_seam` | steer | **the machine-overlap element** |
| `HPV` | `pivot_at_corner` | point + fixed | machine stopped; angle-linear |
| `HRP` | `reposition_mid_seam` | grasp + point | `n_events` predicted from grip span |
| `HFD` | `engage_folder_or_guide` | point + steer | folder/binder/hemmer entry |
| `HAL` | `align_edges_by_hand` | steer + fixed | running match; distributes ease |
| `HFC` | `fold_or_crease` | grasp + steer | tolerance is a fraction of fold depth |
| `HTO` | `turn_component_through` | grasp + steer + point | collars, cuffs; corners at finest tolerance |
| `HTU` | `use_hand_tool` | point + fixed | generic tool element |
| `HTC` | `trim_thread_ends` | point + fixed | `NONE_AUTO` represents an auto-trimmer |
| `HMK` | `mark_position` | point + fixed + cognitive | chalk, template, buttonhole spacing |
| `HAC` | `actuate_machine_control` | point + fixed | backtack, knee lift, hand wheel |
| `HDS` | `dispose_and_stack` | point | includes empty-hand return |
| `HBO` | `bundle_open` | point + fixed | per bundle; amortised |
| `HBC` | `bundle_close` | point + fixed | per bundle; amortised |
| `HBM` | `bundle_move` | point + fixed | per bundle; `WALK` mode must be measured |
| `HIN` | `inspect_work` | cognitive | least mechanistic; measure if material |
| `HSM` | `smooth_and_tension` | steer | wide-tolerance sweep |
| `HAS` | `aside_and_regrasp` | point + grasp | grip change; frequent use signals method issue |

Coverage against the brief's required list is asserted explicitly in the taxonomy's
`coverage_check` block, so a downstream implementer can test it.

---

## 7. Implementation requirements

These are normative. Downstream tracks implement this specification literally, so anything
left implicit here becomes a defect there.

### 7.1 Expression evaluation

Phase arguments are given as restricted expressions over the element's own parameters, the
global parameters, and the whitelisted helper functions in the taxonomy's `expression_grammar`
block. The evaluator must be a **restricted evaluator, not `eval()`** — parse to an AST, permit
only the declared identifiers, operators and functions, and reject anything else. The grammar
block is the normative whitelist.

### 7.2 Continuity across limb bands

Naïve band selection makes `t` discontinuous at 25 mm and 120 mm, so a 1 mm change in a
workstation dimension can shift a standard. The engine must blend across a transition width
`w_blend` (default 15 mm) using a smooth weight `σ` on the log-distance:

`t = (1-σ)·t_lower_band + σ·t_upper_band`, `σ` monotone from 0 to 1 across the band edge.

The blend is a numerical-hygiene device, not a physical claim, and must be documented as such
in the audit trail.

### 7.3 Guard rails

- Every parameter has a declared `domain`. Out-of-domain input is an **error**, not a clamp.
- `Φ` clamping is permitted but must be **flagged** in the audit trail.
- `log₂(D/W + 1)` is safe for all `D ≥ 0, W > 0`. Assert `W > 0`.
- Assert the TMU constant at start-up (§0.4).
- `HBM` with `mode='WALK'` must **refuse** to compute and require a measured value.

### 7.4 Audit trail (minimum content)

Per element: code, all supplied parameter values, resolved class-table values, every phase time
in seconds, the limb class selected for each point phase, the `Φ` applied per phase and whether
it was clamped, which hand was limiting for bimanual elements. Per seam segment: which of
machine or guidance was binding, and the resulting achieved SPM. Per operation: bundle size and
amortised bundle contribution. Per SMV: global parameter set id and version, allowance policy
id and version, and the calibration run id that produced the coefficients.

An SMV that cannot be reproduced from its audit trail is not a standard. Coefficient sets and
allowance policies are **versioned and immutable once used**; editing creates a new version.

### 7.5 Parameter-set provenance

Every parameter carries `status ∈ {literature-grounded, calibration-pending}`. The engine must
surface, on any SMV it produces, **what fraction of the computed time flowed through
calibration-pending coefficients**. Before calibration that fraction is high, and the tool must
say so rather than presenting a confident number. This is the honesty mechanism that keeps the
model from looking more validated than it is.

---

## 8. Calibration procedure

### 8.1 What is fitted

Free coefficients, in the order they should be attacked:

1. `b_s`, `a_s` — steering, from observed feed speeds at known tolerances. Highest leverage:
   guidance time dominates long seams and drives the machine-overlap decision.
2. `g_0`, `g_ply` — grasp, from pick-up elements at varying ply counts.
3. `a_L`, `b_L` per limb class — from transport and positioning elements across distances and
   tolerances. Constrain `a_L ≥ 0` and `b_fin < b_wri < b_arm`.
4. `φ_L, φ_S, φ_B` and phase scales — from the same operations run in different fabrics.
5. `κ_m`, `k_θ`, `k_R`, `ε_bi`, `t_look`, `c_lean` — lower leverage; fit last or hold at default.
6. Process constants (`tool_class`, `tie_type`, `control_class`) — measure directly rather than
   fitting; they are cheap to time and poorly identified in a regression.

### 8.2 Method

Nonlinear least squares on log-transformed element times, minimising

$$\sum_i w_i\Big(\log t_i^{\text{obs}} - \log t_i^{\text{pred}}(\boldsymbol{\theta})\Big)^2
+ \text{penalty}(\boldsymbol{\theta})$$

Log-space because element times are positive and right-skewed, and because it makes the
residual a proportional error, which is the error an industrial engineer cares about. Weights
`w_i` from study sample size. The penalty term keeps coefficients inside their declared
plausible ranges — a soft prior, so that a small data set cannot drive `b_arm` to an
implausible value.

Observed times must be rated to 100 % before fitting (§0.4). Time studies must record, for each
element occurrence: the element code, every parameter value, the fabric lot, the operator, the
rating, and the observed time. **A study that does not record the parameter values cannot be
used for calibration** — this is the single most important thing to communicate to the factory
before data collection starts.

### 8.3 Design of the calibration study

The identifiability of the coefficient set depends on the *spread* of conditions, not the
number of observations. Minimum viable design:

- ≥ 3 distance levels spanning each limb band;
- ≥ 3 tolerance levels (roughly 1, 3, 6 mm) at fixed distance;
- ≥ 3 ply levels (1, 2, 4);
- ≥ 3 fabric classes spanning the descriptor space (crisp/light, slippery, bulky);
- ≥ 2 guidance conditions (free-hand vs edge guide) at matched tolerance;
- ≥ 20 observations per cell.

One thousand observations of the same operation in the same fabric will fit nothing.

### 8.4 Acceptance and reporting

Report per-element median absolute percentage error, the residual distribution, and
`R²` in log space. Refuse to publish a coefficient set whose fitted value sits outside its
declared plausible range without an explicit override and a reason string. Store the fitted
set as an immutable, versioned record, with the study data reference, and stamp its id into
every SMV computed from it.

Validation against published shirt SMV benchmarks is a separate downstream track, and should
be treated as an independent test, never folded back into the fit.

### 8.5 Specification smoke test (pre-calibration)

The equations above were evaluated at their default coefficients to check that the
specification is *self-consistent and physically sensible* before any data exists. This is a
sanity test of the structure, **not** a validation of the numbers. Downstream implementers
should reproduce these figures as an acceptance test of their implementation.

**Guidance speed.** `v_guide = W/b_s` gives 75, 150, 301 and 451 mm/s at tolerances of 1, 2, 4
and 6 mm — the intended tolerance-proportional behaviour.

**Machine-overlap behaviour.** A 60 cm side seam on a 5,000 SPM rated head at a 2 mm guidance
tolerance:

| SPI | machine (s) | guidance (s) | binding | achieved SPM | % of rated |
|---|---|---|---|---|---|
| 8 | 2.27 | 4.14 | guidance | 2,739 | 55 % |
| 10 | 2.83 | 4.14 | guidance | 3,423 | 68 % |
| 12 | 3.40 | 4.14 | guidance | 4,108 | 82 % |
| 14 | 3.97 | 4.14 | guidance | 4,793 | 96 % |

This is the intended and most important qualitative result of the whole model: **achieved SPM
rises towards the rated value as stitch density increases**, because the machine is doing more
work per unit of seam length while the operator's guidance capability is unchanged. At coarse
densities the hands are binding and the head cannot be exploited. That reproduces, from first
principles, the established observation that rated SPM is never achieved — with the derating
emerging from the model rather than being imposed on it. It is also the model's sharpest
falsifiable prediction and should be the first thing checked against observed feed speeds.

**Fabric ordering.** After rectification (§3.5) the nine fabric classes order correctly on a
reference shoulder-join operation, with the reference poplin fastest and sheer slippery blouse
cloth slowest (`Φ_grasp` from 1.00 to 1.37, operation standard time 0.1555 to 0.1756 min). No
class reaches `Φ_max`, so no default fabric class sits outside the guard rails. **This test is
what caught the unrectified-descriptor defect**, and it should be retained as a regression test:
*the reference fabric must be the fastest of all classes, and `Φ` must be ≥ 1 for every class
and phase.*

**Order-of-magnitude flag (open issue).** A simple 15 cm shoulder join computes to 7.4 s basic
/ 0.156 min standard. Thirty such operations would give roughly 4.7 min, against published
whole-shirt SMVs in the region of 15–25 min. The gap is expected — a real shirt has many more
operations, and its collar, cuff, placket and buttonhole work is far more complex than a plain
join — but the ratio has not been demonstrated to close, and it is the clearest available
signal that **the default coefficients may under-predict handling time**. Closing this gap is
the job of §8 calibration and of the downstream validation track; until then no whole-garment
SMV from this engine should be quoted.

---

## 9. Sources

**Motor control — aimed movement**

1. Fitts, P. M. (1954). The information capacity of the human motor system in controlling the
   amplitude of movement. *Journal of Experimental Psychology* 47(6):381–391.
2. MacKenzie, I. S. (1989). A note on the information-theoretic basis for Fitts' law.
   *Journal of Motor Behavior* 21:323–330. — Shannon formulation.
3. MacKenzie, I. S. (1992). Fitts' law as a research and design tool in human–computer
   interaction. *Human–Computer Interaction* 7:91–139.
4. Welford, A. T. (1968). *Fundamentals of Skill*. Methuen, London. — two-part ID form.
5. Langolf, G. D., Chaffin, D. B., & Foulke, J. A. (1976). An investigation of Fitts' law using
   a wide range of movement amplitudes. *Journal of Motor Behavior* 8(2):113–128. — limb-segment
   information capacities: finger ≈ 38 bit/s, wrist ≈ 23 bit/s, arm ≈ 10 bit/s, over amplitudes
   ≈ 0.25–30.5 cm.
6. Balakrishnan, R., & MacKenzie, I. S. (1997). Performance differences in the fingers, wrist,
   and forearm in computer input control. *CHI '97*, doi:10.1145/258549.258764. — substantially
   lower finger bandwidth than (5); brackets `b_fin`.
7. MacKenzie, I. S., & Buxton, W. (1994) and MacKenzie et al. (2008), *An Error Model for
   Pointing Based on Fitts' Law*, CHI '08. — reported intercepts ≈ 94–240 ms and slopes
   ≈ 167–225 ms/bit for practised aimed movement.
8. Limb segment information transmission capacity, PubMed 2926285. — supporting limb-segment
   bandwidth literature.

**Motor control — path-constrained movement**

9. Accot, J., & Zhai, S. (1997). Beyond Fitts' law: models for trajectory-based HCI tasks.
   *CHI '97*, doi:10.1145/258549.258760. — the steering law.
10. Accot, J., & Zhai, S. (1999). Performance evaluation of input devices in trajectory-based
    tasks: an application of the steering law. *CHI '99*. — circular vs straight tunnels.
11. Nancel, M., & Lank, E. Curvature-corrected steering law; and *Curves Ahead: Enhancing the
    Steering Law for Complex Curved Trajectories*, arXiv:2503.11914. — `MT ∝ ∫ds/(W R^{1/3})`.
12. Pastel, R. (2006). Measuring the difficulty of steering through corners. *CHI '06*. —
    corners as coupled steering-plus-pointing; corner angle significant.

**Motor control — bimanual and load**

13. Kelso, J. A. S., Southard, D. L., & Goodman, D. (1979). On the nature of human interlimb
    coordination. *Science* 203:1029–1031; and *JEP: HPP* 5:229–238. — simultaneous execution;
    easier hand slows to the harder.
14. Shea, C. H., Boyle, J., & Kovacs, A. J. (2011). Bimanual Fitts' tasks: Kelso, Southard, and
    Goodman, 1979 revisited. *Experimental Brain Research*, doi:10.1007/s00221-011-2915-5. —
    coupling replicated, strict synchrony qualified.
15. Hagadorn, J. (2004). *The Effects of Object Weight and Three-Dimensional Movement on Human
    Movement Time and Fitts' Law*. MS thesis, Rochester Institute of Technology. — logarithmic
    weight effect.
16. Virtual-to-physical load transformation: misplacement rate, perceived difficulty, and
    movement time. *International Journal of Industrial Ergonomics* (2025),
    doi:10.1016/j.ergon.2025.103859 (S0169814125001763). — load effects on movement time.

**Predetermined-motion-time systems — cited as prior art and as comparison, values not used**

17. Improving time estimation accuracy in manufacturing systems: experimental assessment of the
    MOST predetermined motion time system. *International Journal of Advanced Manufacturing
    Technology* (2025), doi:10.1007/s00170-025-15791-6; and *Evaluating the Accuracy of the MOST
    Predetermined Motion Time System through Lab Experiments* (AHFE open access). — systematic
    error of the class-based approach; **object weight a significant predictor absent from
    MOST**.
18. Ren, L. Study on standard time of garment sewing based on GSD. Atlantis Press. — cited only
    as evidence that the garment literature is PMTS-based and that no Fitts-law treatment of
    sewing exists; no GSD content used.

**Fabric objective measurement**

19. Kawabata KES-F system and CSIRO FAST system literature: bending rigidity, shear rigidity,
    surface friction (`MIU`), thickness and compression as the standard descriptors of fabric
    tailorability and handle. See the published KES-F/FAST bending-rigidity correlation
    (ResearchGate 229049144) and the sewability reviews in *ScienceDirect Topics*: Fabric
    Assurance by Simple Testing; Sewability; Shear Rigidity; Fabric Handle.
20. The relation between fabric construction, treatments and sewability (Academia 29122727). —
    low bending/shear rigidity associated with making-up difficulty.
21. Paulun et al. (2016) and subsequent object-handling reviews on surface friction and
    manipulation time. — slippery objects handled more slowly.

**Apparel industrial engineering and allowances** (detailed citations in `allowance_policy.json`)

22. Kanawaty, G. (ed.) (1992). *Introduction to Work Study*, 4th rev. ed. ILO, Geneva. —
    recommended allowance guidance: constant 5 %/7 % personal needs, 4 % basic fatigue,
    variable allowances for posture, force, light, atmosphere, attention, noise, monotony.
23. Ferreira García et al. (2019). Determination of allowance time by work sampling and heart
    rate in a manufacturing plant in Juárez, México. *Journal of Engineering* (Wiley),
    doi:10.1155/2019/1316734.
24. Apparel Resources, *IE in Apparel Manufacturing-5: Determining Allowances*. — including the
    ILO's own position that it has not adopted and is not likely to adopt allowance standards.
25. Cronometras, *Complete Guide to ILO Fatigue Allowances*.
26. Online Clothing Study: *How to Calculate Garment SAM*; *How to do Time Study for Garment
    Operations*; *Secret Behind Calculation of Machine Time in SAM*. — the ≈10 % bundle and
    ≈20 % machine-and-personal convention, the rule that machine allowance applies only to
    running-machine elements, and the `SPI × length / RPM` machine-time form.

---

## 10. Honest statement of what is and is not established

**Literature-grounded** (functional form and, where stated, coefficient magnitude):
the Shannon-form Fitts equation; limb-dependence of throughput and the bracketing values for
finger, wrist and arm; the steering law and its cube-root curvature augmentation; the
tolerance-proportional guidance-speed consequence; bimanual `max`-with-coupling; the logarithmic
form and direction of the mass effect; the direction of the limpness, slipperiness and bulk
effects; corner angle as a determinant of pivot time; the ILO constant allowances of 5 %/7 %
personal needs and 4 % basic fatigue and the published variable-allowance ranges.

**Calibration-pending** (form reasoned, value provisional): every grasp coefficient; the
steering intercept and slope; all fabric sensitivity magnitudes and phase scales; the mass
sensitivity magnitude; the pivot, curvature and bimanual-penalty magnitudes; the visual-fixation
unit; the trunk-lean adder and threshold; all limb-band edges; all tool, tie and control process
constants; all engine geometry conventions (`D_match`, `L_grip`, `n_throat_aim`,
`fold_tolerance_frac`, `k_ease`); the fabric-class descriptor values; the machine-delay
allowance; the bundle allowance; the seated-posture allowance; and the close-attention
precision mapping.

**Not modelled and requiring direct measurement**: walking; operator learning curves; line
balance and work-in-progress effects; press and fusing operations; visual search beyond a
placeholder.

The count matters and should be stated plainly to any stakeholder: **the functional skeleton of
this model is standing on published science; most of its numerical flesh is not yet on it.**
Before calibration, this engine is a well-posed hypothesis with a defensible structure, not a
validated standard-setting instrument. After calibration against a properly designed factory
study, it becomes an instrument whose accuracy is *measurable* — which is more than the licensed
alternative offers, since a lookup table has no residuals to report.
