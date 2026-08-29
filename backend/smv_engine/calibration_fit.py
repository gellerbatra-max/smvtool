"""
calibration_fit.py -- hierarchical coefficient-fitting calibration module.

Pillar 5 of the self-calibrating synthetic engine: takes validated time-study
rows (from time_study_loader.py) and fits the taxonomy's/effective_spm's
`status: "calibration-pending"` (or, for MotionParams, `status: "ESTIMATE"`)
coefficients to real observations, replacing the shipped provisional defaults.

THREE CALIBRATION SCOPES (per the design direction fixed at handoff)
----------------------------------------------------------------------
 1. ENGINE-WIDE PHYSICAL CONSTANTS -- shared across every factory: the Fitts-
    law limb coefficients (a_fin/b_fin/a_wri/b_wri/a_arm/b_arm), the steering-
    law coefficients (a_steer/b_steer/k_R/R_ref_mm/k_theta), grasp/ply/bundle
    terms (g_0/g_ply/gamma_ply/g_bundle/kappa_m/m_ref_g/D_trunk_mm/c_lean),
    fabric-difficulty terms (phi_limp/phi_slip/phi_bulk/Phi_min/Phi_max),
    cognitive term (t_look), bimanual coupling (epsilon_bi), the four
    element-local engine_constants (D_match_mm/L_grip_cm/n_throat_aim/
    fold_tolerance_frac/k_ease), and effective_spm.py's MotionParams
    (a_up/a_dn/t_correct/theta_drift/t_pivot/t_endstop/t_trim_auto/
    t_trim_manual/eta_set/eta_ply). These are fit ONCE, pooling every
    factory's rows, because they describe human motor control and machine
    kinematics, not any one factory's fabric or culture.
 2. FACTORY-LEVEL REFERENCE-FABRIC / PACE PARAMETERS -- B_ref/MIU_ref/t_ref_mm
    (what "the reference fabric" physically is at THIS factory -- poplin in
    Dhaka is not poplin in Ho Chi Minh City) and a factory random-intercept
    pace effect, fit per factory_id with partial pooling toward the grand
    mean (shrinkage) so a factory with few observations does not get a wild
    factory-specific estimate.
 3. OPERATOR-LEVEL Gamma_skill -- a per-operator multiplier on top of the
    already-fit engine+factory layers, fit as a variance component nested
    within factory (so the same operator_id string at two different
    factories is never pooled together).

Scopes 2 and 3 are fit AFTER scope 1 is held fixed, on the log-residual
observed_s / predicted_s(scope-1-only, Gamma_skill=1, factory=reference),
via statsmodels MixedLM -- this is what "hierarchical" means here: a
sequential (not jointly Bayesian) partial-pooling scheme, chosen because it
is auditable with a standard, inspectable library rather than a bespoke MCMC
implementation, and because scope-1 physical constants are identifiable from
the pooled data in a way the small per-factory/operator samples typically
seen in a single time-study campaign are not.

SPARSE / UNBALANCED DATA
-------------------------
Every fit in this module degrades gracefully to "hold the shipped default"
when there are too few informative observations for a symbol -- see
`min_observations_for_fit` and `coverage_report()`. A parameter is never
silently left at a stale fitted value from a different, larger dataset
without the caller being told how many rows actually identified it.

IP PROVENANCE
-------------
This module fits NUMBERS ONLY -- coefficients of the already-open
Fitts/steering-law functional forms in handling_time.py/effective_spm.py.
It contains no lookup tables and reproduces no licensed predetermined-time
data. See element_taxonomy.json.spec.ip_provenance and
effective_spm.py's module docstring for the underlying provenance statement
this module's outputs inherit.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

import handling_time as ht
import machine_time as mt
import effective_spm as es

MIN_OBS_FOR_FIT = 5          # below this, a scope-1 symbol keeps its shipped default
MIN_OBS_FOR_FACTORY = 3      # below this, a factory's own B_ref/MIU_ref/t_ref_mm keep the global fit
MIN_OBS_FOR_OPERATOR = 3     # below this, Gamma_skill for that operator is shrunk to ~1.0 by MixedLM anyway


# ==========================================================================
# Scope 1: engine-wide physical constants (taxonomy globals + engine
# constants + effective_spm.MotionParams)
# ==========================================================================

# Which taxonomy global_parameters / engine_constants this module is willing
# to fit in scope 1. Excludes B_ref/MIU_ref/t_ref_mm (scope 2) and
# Gamma_skill (scope 3) even though the taxonomy also marks them
# calibration-pending -- those two scopes have their OWN fitting functions
# below because they are per-factory / per-operator, not global.
SCOPE1_TAXONOMY_SYMBOLS = [
    "a_fin", "b_fin", "a_wri", "b_wri", "a_arm", "b_arm",
    "D_trunk_mm", "c_lean", "g_0", "g_ply", "gamma_ply", "g_bundle",
    "kappa_m", "m_ref_g", "a_steer", "b_steer", "k_R", "R_ref_mm", "k_theta",
    "epsilon_bi", "t_look", "phi_limp", "phi_slip", "phi_bulk",
    "Phi_min", "Phi_max",
    "D_match_mm", "L_grip_cm", "n_throat_aim", "fold_tolerance_frac", "k_ease",
]

# effective_spm.MotionParams fields this module is willing to fit in scope 1.
# Bounds are physical-plausibility ranges (MotionParams.py declares no
# plausible_range in code -- these are this module's own documented choices,
# not taken from any licensed source):
#   a_up/a_dn (mm/s^2): human-guided cloth-feed acceleration; 100-1200 spans
#     "very cautious" to "brisk" without allowing runaway fits.
#   t_correct (s): visuomotor correction interval; classic tracking-task
#     literature puts this in the 0.10-0.35 s band.
#   theta_drift (rad): tolerated heading drift; kept small and positive.
#   t_pivot/t_endstop/t_trim_*: fixed costs, bounded well above 0 and below
#     a generous 3 s ceiling so a handful of outlier rows can't blow them up.
#   eta_set (dimensionless, 0-1): set-speed fraction of rated.
#   eta_ply (dimensionless, 0-1): fractional speed loss per ply above 2.
MOTIONPARAMS_BOUNDS = {
    "a_up": (100.0, 1200.0), "a_dn": (100.0, 1200.0),
    "t_correct": (0.08, 0.40), "theta_drift": (0.01, 0.12),
    "t_pivot": (0.10, 3.00), "t_endstop": (0.02, 1.00),
    "t_trim_auto": (0.05, 1.00), "t_trim_manual": (0.20, 3.00),
    "eta_set": (0.50, 0.99), "eta_ply": (0.0, 0.20),
}


@dataclass
class FitOutcome:
    symbol: str
    scope: str
    fitted_value: float | None
    default_value: float
    used_default: bool
    n_observations: int
    reason: str = ""
    se: float | None = None


@dataclass
class CalibrationResult:
    scope1: dict[str, FitOutcome] = field(default_factory=dict)
    factory: dict[str, dict[str, FitOutcome]] = field(default_factory=dict)   # factory_id -> symbol -> outcome
    operator_gamma: dict[str, float] = field(default_factory=dict)           # "factory_id::operator_id" -> Gamma_skill
    mixedlm_summary: str | None = None
    residuals_df: pd.DataFrame | None = None
    coverage: pd.DataFrame | None = None
    fitted_tax_raw: dict | None = None       # element_taxonomy.json dict with scope1+factory values patched in
    fitted_motion_params: "es.MotionParams | None" = None
    notes: list = field(default_factory=list)


def _predict_element_row(tax: "ht.Taxonomy", row: dict) -> float:
    detail = row["detail"]
    r = tax.compute_element(detail["element_code"], **detail.get("params", {}))
    return r["t_basic_s"]


def _predict_seam_row_guide_component(tax: "ht.Taxonomy", row: dict) -> float:
    """Guide-side prediction only (HGD), for rows the loader/diagnostics has
    flagged as guide-bound -- see `select_scope1_rows`."""
    d = row["detail"]
    tol_raw = es.GUIDANCE_TOLERANCE_MM[d["guidance_class"]]
    tol_mm = max(tol_raw, 0.3)
    R_mm = es.CURVATURE_CLASSES_MM[d["curvature_class"]]
    r = tax.compute_element(
        "HGD", path_cm=d["path_length_mm"] / 10.0, tolerance_mm=tol_mm,
        radius_cm=(None if math.isinf(R_mm) else R_mm / 10.0),
        plies=d.get("plies", 2), fabric_class=d.get("fabric_class", "REF_POPLIN"),
        guided_by=d.get("guided_by", "HAND"),
    )
    return r["t_basic_s"]


def _predict_seam_row_machine_component(mcat: "mt.MachineCatalog", row: dict,
                                         p: "es.MotionParams") -> float:
    d = row["detail"]
    r = mt.pure_machine_time_seam(
        mcat, d["machine_class"], path_length_mm=d["path_length_mm"], spi=d["spi"],
        plies=d.get("plies", 2), pivots=d.get("pivots", 0),
        attachment=d.get("attachment"), p=p,
    )
    return r["total_time_s"]


def _predict_cycle_row(mcat: "mt.MachineCatalog", row: dict, p: "es.MotionParams") -> float:
    d = row["detail"]
    r = mt.time_cycle(mcat, d["machine_class"], stitches=d["stitches"],
                       plies=d.get("plies", 2), p=p)
    return r["total_time_s"]


def classify_seam_binding(tax, mcat, row: dict) -> str:
    """Which pillar the engine's own MAX() would select for this seam row,
    using shipped (pre-fit) defaults -- used to route seam_observation rows
    to the guide-side or machine-side scope-1 fit, mirroring
    smv_assembly._assemble_seam_step's own binding logic."""
    d = row["detail"]
    t_guide = _predict_seam_row_guide_component(tax, row)
    t_machine = _predict_seam_row_machine_component(mcat, row, es.MotionParams())
    return "guide" if t_guide >= t_machine else "machine"


# ---- sensitivity (for both fitting weights and the coverage report) ------

def _finite_diff_sensitivity(predict_fn, symbol_value: float, bump: float = 0.05) -> float:
    """Relative sensitivity |d(pred)/d(symbol) * symbol/pred| via a symmetric
    bump; used only for local numerical derivatives inside least_squares'
    own Jacobian estimate is NOT what this is for -- this is the coverage-
    report sensitivity test: 'does perturbing this symbol move this row's
    prediction at all', which is a much cheaper, coarser question."""
    v0 = symbol_value
    f0 = predict_fn(v0)
    f1 = predict_fn(v0 * (1 + bump))
    if f0 == 0:
        return 0.0
    return abs((f1 - f0) / f0) / bump


def sensitivity_report(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", p: "es.MotionParams",
                        rows: list[dict]) -> pd.DataFrame:
    """For every SCOPE1_TAXONOMY_SYMBOL and MotionParams field, count how many
    rows are sensitive to it (|relative sensitivity| > 1e-4 under a 5% bump),
    grouped by which observation kind supplied that sensitivity. This is the
    basis of `coverage_report()`."""
    records = []

    def tax_predict_with(symbol, value, row):
        old = tax.globals.get(symbol, tax.engine_constants.get(symbol))
        is_global = symbol in tax.globals
        if is_global:
            tax.globals[symbol] = value
        else:
            tax.engine_constants[symbol] = value
        try:
            if row["kind"] == "element_observation":
                return _predict_element_row(tax, row)
            elif row["kind"] == "seam_observation":
                return _predict_seam_row_guide_component(tax, row)
            else:
                return None
        finally:
            if is_global:
                tax.globals[symbol] = old
            else:
                tax.engine_constants[symbol] = old

    for symbol in SCOPE1_TAXONOMY_SYMBOLS:
        val0 = tax.globals.get(symbol, tax.engine_constants.get(symbol))
        n_sensitive = 0
        kinds_hit = set()
        for row in rows:
            if row["kind"] not in ("element_observation", "seam_observation"):
                continue
            try:
                s = _finite_diff_sensitivity(lambda v, r=row, sym=symbol: tax_predict_with(sym, v, r), val0)
            except Exception:
                continue
            if s is not None and s > 1e-4:
                n_sensitive += 1
                kinds_hit.add(row["kind"])
        records.append({"scope": "engine_wide", "symbol": symbol, "default": val0,
                         "n_supporting_rows": n_sensitive, "observation_kinds": sorted(kinds_hit)})

    def mp_predict_with(field_name, value, row):
        kwargs = p.as_dict()
        kwargs[field_name] = value
        p2 = es.MotionParams(**kwargs)
        if row["kind"] == "seam_observation":
            return _predict_seam_row_machine_component(mcat, row, p2)
        elif row["kind"] == "cycle_observation":
            return _predict_cycle_row(mcat, row, p2)
        return None

    for field_name in MOTIONPARAMS_BOUNDS:
        val0 = getattr(p, field_name)
        n_sensitive = 0
        kinds_hit = set()
        for row in rows:
            if row["kind"] not in ("seam_observation", "cycle_observation"):
                continue
            try:
                s = _finite_diff_sensitivity(lambda v, r=row, fn=field_name: mp_predict_with(fn, v, r), val0)
            except Exception:
                continue
            if s is not None and s > 1e-4:
                n_sensitive += 1
                kinds_hit.add(row["kind"])
        records.append({"scope": "engine_wide", "symbol": field_name, "default": val0,
                         "n_supporting_rows": n_sensitive, "observation_kinds": sorted(kinds_hit)})

    return pd.DataFrame.from_records(records)


# ---- scope 1 fit -----------------------------------------------------------

def fit_scope1(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", p0: "es.MotionParams",
               rows: list[dict], symbols: list[str] | None = None,
               motion_fields: list[str] | None = None,
               min_obs: int = MIN_OBS_FOR_FIT) -> tuple[dict[str, FitOutcome], "es.MotionParams", pd.DataFrame]:
    """Jointly fit taxonomy scope-1 symbols and MotionParams fields by
    nonlinear least squares on log(observed_s) - log(predicted_s), pooling
    ALL factories' rows. Any symbol with fewer than `min_obs` sensitive rows
    (per `sensitivity_report`) is excluded from the fit vector and reported
    with `used_default=True`.
    """
    symbols = symbols if symbols is not None else list(SCOPE1_TAXONOMY_SYMBOLS)
    motion_fields = motion_fields if motion_fields is not None else list(MOTIONPARAMS_BOUNDS)

    cov = sensitivity_report(tax, mcat, p0, rows)
    cov_idx = cov.set_index("symbol")["n_supporting_rows"].to_dict()

    fit_tax_syms = [s for s in symbols if cov_idx.get(s, 0) >= min_obs]
    fit_mp_fields = [f for f in motion_fields if cov_idx.get(f, 0) >= min_obs]

    outcomes: dict[str, FitOutcome] = {}
    for s in symbols:
        if s not in fit_tax_syms:
            default = tax.globals.get(s, tax.engine_constants.get(s))
            outcomes[s] = FitOutcome(s, "engine_wide", None, default, True,
                                      cov_idx.get(s, 0),
                                      reason=f"< {min_obs} sensitive observations; kept shipped default")
    for f in motion_fields:
        if f not in fit_mp_fields:
            outcomes[f] = FitOutcome(f, "engine_wide", None, getattr(p0, f), True,
                                      cov_idx.get(f, 0),
                                      reason=f"< {min_obs} sensitive observations; kept shipped default")

    if not fit_tax_syms and not fit_mp_fields:
        return outcomes, p0, cov

    x0, lo, hi, names = [], [], [], []
    for s in fit_tax_syms:
        meta = tax.global_meta.get(s)
        default = tax.globals.get(s, tax.engine_constants.get(s))
        if meta is not None and meta.get("plausible_range"):
            lo_b, hi_b = meta["plausible_range"]
        else:
            # engine_constants: use a generous +/-100% band around the default,
            # floored just above 0 for strictly-positive quantities.
            lo_b, hi_b = max(1e-6, default * 0.1), default * 3.0
        x0.append(default); lo.append(lo_b); hi.append(hi_b); names.append(("tax", s))
    for f in fit_mp_fields:
        lo_b, hi_b = MOTIONPARAMS_BOUNDS[f]
        x0.append(getattr(p0, f)); lo.append(lo_b); hi.append(hi_b); names.append(("mp", f))

    elem_rows = [r for r in rows if r["kind"] == "element_observation"]
    seam_rows = [r for r in rows if r["kind"] == "seam_observation"]
    cycle_rows = [r for r in rows if r["kind"] == "cycle_observation"]
    seam_binding = {id(r): classify_seam_binding(tax, mcat, r) for r in seam_rows}

    def unpack(x):
        for (kind, name), val in zip(names, x):
            if kind == "tax":
                if name in tax.globals:
                    tax.globals[name] = val
                else:
                    tax.engine_constants[name] = val
        mp_kwargs = p0.as_dict()
        for (kind, name), val in zip(names, x):
            if kind == "mp":
                mp_kwargs[name] = val
        return es.MotionParams(**mp_kwargs)

    def residuals(x):
        p = unpack(x)
        res = []
        for r in elem_rows:
            pred = max(_predict_element_row(tax, r), 1e-6)
            res.append(math.log(r["observed_s"]) - math.log(pred))
        for r in seam_rows:
            if seam_binding[id(r)] == "guide":
                pred = max(_predict_seam_row_guide_component(tax, r), 1e-6)
            else:
                pred = max(_predict_seam_row_machine_component(mcat, r, p), 1e-6)
            res.append(math.log(r["observed_s"]) - math.log(pred))
        for r in cycle_rows:
            pred = max(_predict_cycle_row(mcat, r, p), 1e-6)
            res.append(math.log(r["observed_s"]) - math.log(pred))
        return np.array(res)

    result = least_squares(residuals, x0=np.array(x0), bounds=(np.array(lo), np.array(hi)),
                            method="trf")
    p_fitted = unpack(result.x)

    # crude per-parameter standard error from the linearised covariance
    try:
        J = result.jac
        dof = max(len(result.fun) - len(result.x), 1)
        s2 = float(np.sum(result.fun ** 2) / dof)
        cov_mat = s2 * np.linalg.pinv(J.T @ J)
        ses = np.sqrt(np.abs(np.diag(cov_mat)))
    except Exception:
        ses = [None] * len(names)

    for (kind, name), val, se in zip(names, result.x, ses):
        outcomes[name] = FitOutcome(
            name, "engine_wide", float(val),
            (tax.global_meta.get(name, {}).get("default") if kind == "tax" else getattr(p0, name)),
            False, cov_idx.get(name, 0), reason="fit", se=(float(se) if se is not None else None),
        )

    return outcomes, p_fitted, cov


# ==========================================================================
# Scope 2: factory-level reference-fabric parameters
# ==========================================================================

def fit_factory_reference_fabric(rows: list[dict], min_obs: int = MIN_OBS_FOR_FACTORY) -> dict[str, dict[str, FitOutcome]]:
    """B_ref/MIU_ref/t_ref_mm are properties of 'what this factory calls the
    reference fabric', not universal constants -- they can only be estimated
    from environment.fabric_class_actual / environment.fabric_measured_*
    metadata that the factory supplies alongside a row, NOT from
    compute_element residuals (those get absorbed into PHI's z-scores, which
    are already relative to whatever REF_POPLIN values are configured).

    This function looks for `environment.measured_B_uNm` /
    `environment.measured_MIU` / `environment.measured_t_mm` fields (direct
    KES-F-style fabric measurements attached to a batch) and, per factory_id,
    averages whatever measurements are present with >= min_obs support. A
    factory with no such measurements keeps the global (REF_POPLIN) values --
    this is the expected case until factories start submitting fabric-
    characterisation data alongside their time studies.
    """
    by_factory: dict[str, list[dict]] = {}
    for r in rows:
        env = r.get("environment") or {}
        by_factory.setdefault(r["factory_id"], []).append(env)

    out: dict[str, dict[str, FitOutcome]] = {}
    global_defaults = {"B_ref": 10.0, "MIU_ref": 0.15, "t_ref_mm": 0.30}
    for factory_id, envs in by_factory.items():
        out[factory_id] = {}
        for key, symbol in (("measured_B_uNm", "B_ref"), ("measured_MIU", "MIU_ref"),
                             ("measured_t_mm", "t_ref_mm")):
            vals = [e[key] for e in envs if isinstance(e, dict) and e.get(key) is not None]
            if len(vals) >= min_obs:
                out[factory_id][symbol] = FitOutcome(
                    symbol, f"factory:{factory_id}", float(np.mean(vals)),
                    global_defaults[symbol], False, len(vals),
                    reason=f"mean of {len(vals)} direct fabric measurements",
                )
            else:
                out[factory_id][symbol] = FitOutcome(
                    symbol, f"factory:{factory_id}", None, global_defaults[symbol], True,
                    len(vals), reason=f"< {min_obs} direct fabric measurements; kept global reference",
                )
    return out


# ==========================================================================
# Scope 3: operator-level Gamma_skill (hierarchical: operator nested in
# factory), fit on scope-1(+2)-residuals via statsmodels MixedLM
# ==========================================================================

def fit_operator_gamma(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", p_fitted: "es.MotionParams",
                        rows: list[dict]) -> tuple[dict[str, float], str | None, pd.DataFrame]:
    """Fit Gamma_skill as exp(operator random effect) nested within a
    factory random effect, on log(observed/predicted) residuals from the
    already-fit SCOPE-1-ONLY model held fixed (predicted_s uses the fitted
    scope-1 taxonomy with p_fitted's MotionParams, Gamma_skill=1, and the
    reference fabric -- scope 2's per-factory B_ref/MIU_ref/t_ref_mm is
    computed separately by fit_factory_reference_fabric() and is NOT merged
    in here; see calibrate_all() and the module docstring above). Falls
    back to a plain factory-mean / operator-mean shrinkage estimator if
    statsmodels is unavailable or the mixed model fails to converge
    (flagged in the returned notes-string), so this scope never hard-fails
    the pipeline.
    """
    records = []
    for r in rows:
        if r["kind"] == "element_observation":
            pred = _predict_element_row(tax, r)
        elif r["kind"] == "seam_observation":
            binding = classify_seam_binding(tax, mcat, r)
            pred = (_predict_seam_row_guide_component(tax, r) if binding == "guide"
                    else _predict_seam_row_machine_component(mcat, r, p_fitted))
        elif r["kind"] == "cycle_observation":
            pred = _predict_cycle_row(mcat, r, p_fitted)
        else:
            continue
        if pred <= 0:
            continue
        records.append({
            "factory_id": r["factory_id"], "operator_id": r["operator_id"],
            "group_key": f"{r['factory_id']}::{r['operator_id']}",
            "log_resid": math.log(max(r["observed_s"], 1e-6) / pred),
        })
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return {}, None, df

    summary_text = None
    try:
        import statsmodels.formula.api as smf
        model = smf.mixedlm("log_resid ~ 1", df, groups=df["factory_id"],
                             vc_formula={"operator": "0 + C(group_key)"})
        fit = model.fit(reml=True)
        summary_text = str(fit.summary())
        gamma = {}
        # random-effects dict keyed by group (factory) -> Series incl. vc terms.
        # statsmodels names variance-component terms
        # "<vc_name>[C(<grouping_col>)[<level>]]", e.g.
        # "operator[C(group_key)[SYN-FACTORY-1::OP1]]" -- extract the
        # INNERMOST bracketed level, not the outer vc-term wrapper.
        import re as _re
        for grp, re_series in fit.random_effects.items():
            for term, val in re_series.items():
                m = _re.search(r"C\(group_key\)\[([^\]]+)\]", term)
                if m:
                    key = m.group(1)
                    gamma[key] = float(math.exp(val))
        # operators with zero random-effect estimate (e.g. never appeared,
        # or shrunk fully to 0 by REML) still get an explicit Gamma_skill=1.0
        for key in df["group_key"].unique():
            gamma.setdefault(key, 1.0)
        return gamma, summary_text, df
    except Exception as exc:
        warnings.warn(f"MixedLM fit failed ({exc!r}); falling back to simple shrinkage estimator")
        grand_mean = df["log_resid"].mean()
        gamma = {}
        for key, g in df.groupby("group_key"):
            n = len(g)
            w = n / (n + 3.0)  # simple James-Stein-style shrinkage toward the grand mean
            shrunk = w * g["log_resid"].mean() + (1 - w) * grand_mean
            gamma[key] = float(math.exp(shrunk))
        return gamma, f"FALLBACK shrinkage estimator used (MixedLM raised {exc!r})", df


# ==========================================================================
# Orchestration
# ==========================================================================

def calibrate_all(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", rows: list[dict],
                   p0: "es.MotionParams | None" = None) -> CalibrationResult:
    """Run scope 1 -> scope 2 -> scope 3 in sequence and return everything
    a diagnostics/report step needs. `rows` should be `LoadResult.rows` from
    time_study_loader.py (already schema-validated). Rows with
    method == 'SYNTHETIC' are NOT filtered out here -- callers doing a real
    calibration must filter those themselves; this module fits whatever it
    is given and trusts the caller about what that is."""
    p0 = p0 or es.MotionParams()
    result = CalibrationResult()

    scope1_outcomes, p_fitted, cov = fit_scope1(tax, mcat, p0, rows)
    result.scope1 = scope1_outcomes
    result.fitted_motion_params = p_fitted

    # apply scope-1 fitted values onto a COPY of the taxonomy for downstream use
    fitted_raw = json_deepcopy(tax.raw)
    gp_by_symbol = {gp["symbol"]: gp for gp in fitted_raw["global_parameters"]}
    ec_by_symbol = {ec["symbol"]: ec for ec in fitted_raw["engine_constants"]}
    for sym, outcome in scope1_outcomes.items():
        if outcome.used_default:
            continue
        if sym in gp_by_symbol:
            gp_by_symbol[sym]["default"] = outcome.fitted_value
            gp_by_symbol[sym]["status"] = "fitted"
        elif sym in ec_by_symbol:
            ec_by_symbol[sym]["default"] = outcome.fitted_value
            ec_by_symbol[sym]["status"] = "fitted"
    result.fitted_tax_raw = fitted_raw
    tax_fitted = ht.Taxonomy(fitted_raw)

    result.factory = fit_factory_reference_fabric(rows)

    gamma, mixedlm_summary, resid_df = fit_operator_gamma(tax_fitted, mcat, p_fitted, rows)
    result.operator_gamma = gamma
    result.mixedlm_summary = mixedlm_summary
    result.residuals_df = resid_df

    result.coverage = coverage_report(cov, result.factory, rows)
    result.notes.append(
        f"Fit on {len(rows)} rows "
        f"({sum(1 for r in rows if r.get('method') == 'SYNTHETIC')} SYNTHETIC, "
        f"{sum(1 for r in rows if r.get('method') != 'SYNTHETIC')} non-synthetic)."
    )
    return result


def coverage_report(scope1_cov: pd.DataFrame, factory_outcomes: dict, rows: list[dict]) -> pd.DataFrame:
    """One row per calibration-pending symbol (all scopes), with n supporting
    observations and whether it ended up fit or held at default -- the
    'which coefficients still lack supporting observations' deliverable."""
    recs = []
    for _, row in scope1_cov.iterrows():
        recs.append({
            "scope": "engine_wide", "symbol": row["symbol"], "factory_id": None,
            "n_supporting_rows": row["n_supporting_rows"],
            "observation_kinds": ",".join(row["observation_kinds"]),
            "status": "SUFFICIENT" if row["n_supporting_rows"] >= MIN_OBS_FOR_FIT else "INSUFFICIENT",
        })
    for factory_id, syms in factory_outcomes.items():
        for symbol, outcome in syms.items():
            recs.append({
                "scope": f"factory:{factory_id}", "symbol": symbol, "factory_id": factory_id,
                "n_supporting_rows": outcome.n_observations, "observation_kinds": "environment.measured_*",
                "status": "SUFFICIENT" if not outcome.used_default else "INSUFFICIENT",
            })
    n_op_rows: dict[str, int] = {}
    for r in rows:
        key = f"{r['factory_id']}::{r['operator_id']}"
        n_op_rows[key] = n_op_rows.get(key, 0) + 1
    for key, n in n_op_rows.items():
        recs.append({
            "scope": "operator", "symbol": "Gamma_skill", "factory_id": key.split("::")[0],
            "n_supporting_rows": n, "observation_kinds": "any",
            "status": "SUFFICIENT" if n >= MIN_OBS_FOR_OPERATOR else "INSUFFICIENT (shrunk toward 1.0)",
        })
    return pd.DataFrame.from_records(recs)


def json_deepcopy(d):
    import json as _json
    return _json.loads(_json.dumps(d))


# ==========================================================================
# Synthetic time-study generator (SYNTHETIC-labelled, per schema convention)
# ==========================================================================

def generate_synthetic_batch(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog",
                              n_operators: int = 6, n_per_operator: int = 12,
                              factory_id: str = "SYN-FACTORY-1", seed: int = 0,
                              true_gamma_by_operator: dict | None = None,
                              true_param_perturbation: dict | None = None,
                              noise_sigma_log: float = 0.12) -> dict:
    """Generate a study_batch dict of method='SYNTHETIC' rows by perturbing
    the ENGINE'S OWN predictions with (a) a per-operator true Gamma_skill
    (default: drawn from the taxonomy's own plausible_range so a known
    ground truth exists to validate `fit_operator_gamma` against) and
    (b) log-normal measurement noise. This demonstrates and unit-tests the
    fitting code only -- see time_study_schema.json's own description of
    method='SYNTHETIC': generator-produced rows must never be used for a
    real factory's coefficients."""
    rng = np.random.default_rng(seed)
    true_gamma_by_operator = true_gamma_by_operator or {
        f"OP{i+1}": float(rng.uniform(0.90, 1.15)) for i in range(n_operators)
    }

    element_probe_params = {
        "HAG": {"distance_cm": 25.0, "precision_class": "P2", "fabric_class": "REF_POPLIN"},
        "HAM": {"distance_cm": 30.0, "match_precision": "P2", "n_match_points": 2,
                "fabric_class": "REF_POPLIN", "bundle_state": "LOOSE"},
        "HPF": {"foot_lift": "KNEE_LIFT"},
        "HTC": {"n_ends": 2, "tool_class": "NIPPER"},
        "HDS": {"distance_cm": 20.0, "fabric_class": "REF_POPLIN"},
        "HBO": {"n_ties": 1, "tie_type": "CLOTH_KNOT"},
        "HFC": {"fold_length_cm": 15.0, "fold_depth_mm": 8.0, "n_folds": 1},
        "HIN": {"inspect_class": "GLANCE"},
    }
    seam_probes = [
        dict(machine_class="SNLS-UBT", path_length_mm=180.0, spi=12.0, plies=2,
             curvature_class="moderate", guidance_class="topstitch"),
        dict(machine_class="SNLS-UBT", path_length_mm=90.0, spi=12.0, plies=2,
             curvature_class="tight", guidance_class="edgestitch_critical"),
        dict(machine_class="OL-3T", path_length_mm=250.0, spi=10.0, plies=3,
             curvature_class="gentle", guidance_class="seam_hidden"),
    ]
    cycle_probes = [
        dict(machine_class="BH-LS", stitches=88),
    ]

    observations = []
    obs_i = 0
    for op_i in range(n_operators):
        op_id = f"OP{op_i+1}"
        gamma_true = true_gamma_by_operator[op_id]
        for _ in range(n_per_operator):
            kind_choice = rng.choice(["element", "seam", "cycle"], p=[0.5, 0.4, 0.1])
            obs_i += 1
            obs_id = f"SYN-{factory_id}-{obs_i:05d}"
            if kind_choice == "element":
                code = rng.choice(list(element_probe_params))
                params = dict(element_probe_params[code])
                if "distance_cm" in params:
                    params["distance_cm"] = float(np.clip(params["distance_cm"] * rng.uniform(0.7, 1.3), 3, 80))
                true_s = tax.compute_element(code, **params)["t_basic_s"] * gamma_true
                observed = float(true_s * rng.lognormal(0, noise_sigma_log))
                observations.append({
                    "observation_id": obs_id, "operator_id": op_id, "n_reps_averaged": 1,
                    "observed_s": round(observed, 4),
                    "element_observation": {"element_code": code, "params": params},
                })
            elif kind_choice == "seam":
                probe = dict(rng.choice(seam_probes))
                probe["path_length_mm"] = float(np.clip(probe["path_length_mm"] * rng.uniform(0.8, 1.2), 20, 900))
                t_guide = _predict_seam_row_guide_component(
                    tax, {"detail": {**probe, "fabric_class": "REF_POPLIN", "guided_by": "HAND"}}
                )
                t_machine = _predict_seam_row_machine_component(
                    mcat, {"detail": probe}, es.MotionParams()
                )
                true_s = max(t_guide, t_machine) * gamma_true
                observed = float(true_s * rng.lognormal(0, noise_sigma_log))
                observations.append({
                    "observation_id": obs_id, "operator_id": op_id, "n_reps_averaged": 1,
                    "observed_s": round(observed, 4),
                    "seam_observation": {**probe, "pivots": 0},
                })
            else:
                probe = dict(rng.choice(cycle_probes))
                true_s = mt.time_cycle(mcat, probe["machine_class"], stitches=probe["stitches"])["total_time_s"] * gamma_true
                observed = float(true_s * rng.lognormal(0, noise_sigma_log))
                observations.append({
                    "observation_id": obs_id, "operator_id": op_id, "n_reps_averaged": 1,
                    "observed_s": round(observed, 4),
                    "cycle_observation": probe,
                })

    return {
        "batch_id": f"{factory_id}_SYNTHETIC_seed{seed}",
        "factory_id": factory_id,
        "method": "SYNTHETIC",
        "rater_id": "calibration_fit.generate_synthetic_batch",
        "rater_qualification": "AUTOMATED",
        "date_range": ["1970-01-01", "1970-01-01"],
        "performance_rating_applied": True,
        "observations": observations,
        "_ground_truth": {"gamma_by_operator": true_gamma_by_operator},   # not part of the schema; test-only
    }


if __name__ == "__main__":
    import time_study_loader as tsl

    tax = ht.load_taxonomy("element_taxonomy.json")
    mcat = mt.load_machine_catalog("machine_classes.csv")
    batch = generate_synthetic_batch(tax, mcat, n_operators=6, n_per_operator=15, seed=42)
    loader = tsl.TimeStudyLoader(tax, mcat)
    load_result = loader.load_batch_dict({k: v for k, v in batch.items() if k != "_ground_truth"})
    print(f"loaded {len(load_result.rows)} rows, {len(load_result.rejections)} rejections")

    cal = calibrate_all(tax, mcat, load_result.rows)
    n_fit = sum(1 for o in cal.scope1.values() if not o.used_default)
    print(f"scope1: {n_fit}/{len(cal.scope1)} symbols fit from data")
    print(f"operator gamma (fitted) vs ground truth:")
    for op_id, g_true in batch["_ground_truth"]["gamma_by_operator"].items():
        key = f"{batch['factory_id']}::{op_id}"
        print(f"  {op_id}: true={g_true:.3f}  fitted={cal.operator_gamma.get(key, float('nan')):.3f}")
