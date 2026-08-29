"""
calibration_diagnostics.py -- diagnostics and coverage reporting for
calibration_fit.py's fitted engine.

Produces:
 * observed-vs-predicted residual table + plot, in both raw seconds and
   log space (log space is the space the fit itself minimises in, so its
   residuals are what to trust for "did the fit converge sensibly").
 * a per-operation-kind error table with MAPE and RMSE (in log space, since
   MAPE on a ratio scale is degenerate near predicted=0).
 * a K-fold cross-validated accuracy metric (refits scope 1 K times, holding
   out a fold each time, to get an honest out-of-sample MAPE rather than a
   train-set number).
 * the coverage report as a figure (which calibration-pending symbols have
   enough supporting observations, grouped by scope).

All numbers in this module are demonstrated on a SYNTHETIC dataset (see
calibration_fit.generate_synthetic_batch) since no real factory time studies
exist yet -- every figure and table produced here is labelled accordingly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import handling_time as ht
import machine_time as mt
import effective_spm as es
import calibration_fit as cf


# --------------------------------------------------------------------------
# Prediction helper (mirrors calibration_fit's internal row-dispatch, but
# public here since diagnostics needs it independent of a live fit)
# --------------------------------------------------------------------------

def predict_row(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", p: "es.MotionParams", row: dict) -> float:
    if row["kind"] == "element_observation":
        return cf._predict_element_row(tax, row)
    elif row["kind"] == "seam_observation":
        binding = cf.classify_seam_binding(tax, mcat, row)
        return (cf._predict_seam_row_guide_component(tax, row) if binding == "guide"
                else cf._predict_seam_row_machine_component(mcat, row, p))
    elif row["kind"] == "cycle_observation":
        return cf._predict_cycle_row(mcat, row, p)
    raise ValueError(f"unknown row kind {row['kind']!r}")


# --------------------------------------------------------------------------
# Residual table
# --------------------------------------------------------------------------

def residual_table(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog", p: "es.MotionParams",
                    rows: list[dict]) -> pd.DataFrame:
    recs = []
    for r in rows:
        try:
            pred = predict_row(tax, mcat, p, r)
        except Exception as exc:
            continue
        obs = r["observed_s"]
        if pred <= 0 or obs <= 0:
            continue
        recs.append({
            "observation_id": r.get("observation_id"),
            "kind": r["kind"], "factory_id": r["factory_id"], "operator_id": r["operator_id"],
            "observed_s": obs, "predicted_s": pred,
            "resid_s": obs - pred,
            "log_resid": math.log(obs / pred),
            "abs_pct_error": abs(obs - pred) / obs * 100.0,
        })
    return pd.DataFrame.from_records(recs)


def error_summary_by_kind(resid_df: pd.DataFrame) -> pd.DataFrame:
    def _agg(g):
        return pd.Series({
            "n": len(g),
            "MAPE_pct": g["abs_pct_error"].mean(),
            "RMSE_log": math.sqrt((g["log_resid"] ** 2).mean()),
            "median_log_resid": g["log_resid"].median(),
            "bias_pct": ((g["predicted_s"] - g["observed_s"]) / g["observed_s"]).mean() * 100.0,
        })
    return resid_df.groupby("kind").apply(_agg, include_groups=False).reset_index()


# --------------------------------------------------------------------------
# K-fold cross-validated accuracy
# --------------------------------------------------------------------------

def cross_validated_mape(tax: "ht.Taxonomy", mcat: "mt.MachineCatalog",
                          rows: list[dict], k: int = 5, seed: int = 0) -> dict:
    """K-fold CV of the scope-1 fit: refit on k-1 folds, score MAPE on the
    held-out fold, using the SAME rows list for both folds (no leakage of
    factory/operator scopes since scope 1 pools across all of them anyway).
    Returns per-fold and aggregate out-of-sample MAPE, log-RMSE."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(rows))
    rng.shuffle(idx)
    folds = np.array_split(idx, k)

    fold_results = []
    for i in range(k):
        held_out_idx = set(folds[i].tolist())
        train_rows = [r for j, r in enumerate(rows) if j not in held_out_idx]
        test_rows = [r for j, r in enumerate(rows) if j in held_out_idx]
        if not train_rows or not test_rows:
            continue
        outcomes, p_fitted, _ = cf.fit_scope1(tax, mcat, es.MotionParams(), train_rows)
        fitted_raw = cf.json_deepcopy(tax.raw)
        gp_by_symbol = {gp["symbol"]: gp for gp in fitted_raw["global_parameters"]}
        ec_by_symbol = {ec["symbol"]: ec for ec in fitted_raw["engine_constants"]}
        for sym, o in outcomes.items():
            if o.used_default:
                continue
            if sym in gp_by_symbol:
                gp_by_symbol[sym]["default"] = o.fitted_value
            elif sym in ec_by_symbol:
                ec_by_symbol[sym]["default"] = o.fitted_value
        tax_fold = ht.Taxonomy(fitted_raw)

        errs = []
        for r in test_rows:
            try:
                pred = predict_row(tax_fold, mcat, p_fitted, r)
            except Exception:
                continue
            if pred > 0 and r["observed_s"] > 0:
                errs.append(abs(r["observed_s"] - pred) / r["observed_s"] * 100.0)
        if errs:
            fold_results.append({"fold": i, "n_test": len(errs), "MAPE_pct": float(np.mean(errs))})

    if not fold_results:
        return {"folds": [], "mean_MAPE_pct": None, "sd_MAPE_pct": None}
    mapes = [f["MAPE_pct"] for f in fold_results]
    return {
        "folds": fold_results,
        "mean_MAPE_pct": float(np.mean(mapes)),
        "sd_MAPE_pct": float(np.std(mapes)),
    }


# --------------------------------------------------------------------------
# Figure: multi-panel diagnostics
# --------------------------------------------------------------------------

_META_GREY = "#8c8c8c"
_KIND_COLORS = ["#2f6fab", "#c1652f", "#3f9142"]


def _default_palette(kinds: list[str]) -> dict:
    return {k: _KIND_COLORS[i % len(_KIND_COLORS)] for i, k in enumerate(sorted(kinds))}


def _plain_style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out")


def render_diagnostics_figure(resid_df: pd.DataFrame, error_by_kind: pd.DataFrame,
                               coverage_df: pd.DataFrame, cv_result: dict,
                               out_path: str = "calibration_diagnostics.png"):
    """Self-contained plotting (no dependency on any interactively-loaded
    skill helper) so this module runs the same way standalone in production
    as it does in a development session with figure-style tooling loaded."""
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "figure.dpi": 100})
    fig = plt.figure(figsize=(13, 9.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1],
                           hspace=0.38, wspace=0.30)

    palette = _default_palette(list(resid_df["kind"].unique()))
    META_GREY = _META_GREY
    set_frame = _plain_style

    # Panel A: observed vs predicted (log-log), colored by kind
    ax0 = fig.add_subplot(gs[0, 0])
    for kind, g in resid_df.groupby("kind"):
        ax0.scatter(g["predicted_s"], g["observed_s"], s=18, alpha=0.65,
                    color=palette[kind], label=kind.replace("_observation", ""), edgecolors="none")
    lims = [resid_df[["predicted_s", "observed_s"]].min().min() * 0.8,
            resid_df[["predicted_s", "observed_s"]].max().max() * 1.2]
    ax0.plot(lims, lims, color=META_GREY, lw=1.0, ls="--", zorder=0)
    ax0.set_xscale("log"); ax0.set_yscale("log")
    ax0.set_xlim(lims); ax0.set_ylim(lims)
    ax0.set_xlabel("Predicted time (s)"); ax0.set_ylabel("Observed time (s)")
    ax0.set_title("Predicted vs. observed cycle time (SYNTHETIC demo data)")
    ax0.legend(frameon=False, loc="upper left", fontsize=7)
    set_frame(ax0)

    # Panel B: log-residual histogram
    ax1 = fig.add_subplot(gs[0, 1])
    ax1.hist(resid_df["log_resid"], bins=30, color=META_GREY, edgecolor="white", linewidth=0.4)
    ax1.axvline(0, color="black", lw=1.0, ls="--")
    mean_lr = resid_df["log_resid"].mean()
    ax1.axvline(mean_lr, color=palette[sorted(palette)[0]], lw=1.5)
    ax1.set_xlabel("log(observed / predicted)")
    ax1.set_ylabel("count")
    ax1.set_title(f"Residual distribution (mean={mean_lr:+.3f})")
    set_frame(ax1)

    # Panel C: MAPE by observation kind + CV out-of-sample MAPE
    ax2 = fig.add_subplot(gs[1, 0])
    kinds = error_by_kind["kind"].str.replace("_observation", "", regex=False).tolist()
    mapes = error_by_kind["MAPE_pct"].tolist()
    colors = [palette[k] for k in error_by_kind["kind"]]
    bars = ax2.bar(kinds, mapes, color=colors, width=0.6)
    for b, m in zip(bars, mapes):
        ax2.text(b.get_x() + b.get_width() / 2, m + max(mapes) * 0.02, f"{m:.1f}%",
                  ha="center", va="bottom", fontsize=7)
    if cv_result.get("mean_MAPE_pct") is not None:
        ax2.axhline(cv_result["mean_MAPE_pct"], color="black", lw=1.2, ls=":")
        ax2.text(len(kinds) - 0.4, cv_result["mean_MAPE_pct"],
                  f"  {cv_result['mean_MAPE_pct']:.1f}% out-of-sample (K-fold CV)",
                  va="bottom", ha="right", fontsize=7)
    ax2.set_ylabel("MAPE (%)")
    ax2.set_title("In-sample error by observation kind, vs. cross-validated error")
    set_frame(ax2)

    # Panel D: coverage -- n supporting rows per engine-wide symbol, sufficient vs not
    ax3 = fig.add_subplot(gs[1, 1])
    ew = coverage_df[coverage_df["scope"] == "engine_wide"].sort_values("n_supporting_rows")
    colors3 = ["#c0c0c0" if s == "INSUFFICIENT" else palette[sorted(palette)[0]] for s in ew["status"]]
    ax3.barh(ew["symbol"], ew["n_supporting_rows"], color=colors3, height=0.7)
    ax3.axvline(cf.MIN_OBS_FOR_FIT, color="black", lw=1.0, ls="--")
    ax3.text(cf.MIN_OBS_FOR_FIT, -0.8, f" min={cf.MIN_OBS_FOR_FIT}", fontsize=6, va="top")
    ax3.set_xlabel("supporting observations")
    ax3.set_title("Coverage: engine-wide symbols, this dataset")
    ax3.tick_params(axis="y", labelsize=5.5)
    set_frame(ax3)

    fig.suptitle("Calibration diagnostics -- SYNTHETIC demonstration dataset (no real factory data yet)",
                 fontsize=11, y=0.995)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    return fig


if __name__ == "__main__":
    import time_study_loader as tsl

    tax = ht.load_taxonomy("element_taxonomy.json")
    mcat = mt.load_machine_catalog("machine_classes.csv")
    batch = cf.generate_synthetic_batch(tax, mcat, n_operators=8, n_per_operator=25, seed=42)
    loader = tsl.TimeStudyLoader(tax, mcat)
    lr = loader.load_batch_dict({k: v for k, v in batch.items() if k != "_ground_truth"})
    print(f"loaded {len(lr.rows)} rows, {len(lr.rejections)} rejections")

    result = cf.calibrate_all(tax, mcat, lr.rows)
    tax_fitted = ht.Taxonomy(result.fitted_tax_raw)

    resid = residual_table(tax_fitted, mcat, result.fitted_motion_params, lr.rows)
    by_kind = error_summary_by_kind(resid)
    cv = cross_validated_mape(tax, mcat, lr.rows, k=5, seed=0)

    print(by_kind.to_string(index=False))
    print(f"cross-validated MAPE: {cv['mean_MAPE_pct']:.2f}% +/- {cv['sd_MAPE_pct']:.2f}%")

    resid.to_csv("calibration_residuals.csv", index=False)
    by_kind.to_csv("calibration_error_by_kind.csv", index=False)
    result.coverage.to_csv("calibration_coverage.csv", index=False)

    render_diagnostics_figure(resid, by_kind, result.coverage, cv, "calibration_diagnostics.png")
    print("saved calibration_diagnostics.png, calibration_residuals.csv, "
          "calibration_error_by_kind.csv, calibration_coverage.csv")
