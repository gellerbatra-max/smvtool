"""
effective_spm.py -- Effective sewing-speed model for the synthetic SMV engine.

Pillar 1 (MACHINE TIME) of the self-calibrating synthetic engine.

Converts a *rated* machine speed (sti/min, from the manufacturer spec sheet)
into an *achieved average* speed over a real stitching run, accounting for:

  1. set-speed derate            (the machine is not set to its rated maximum)
  2. fabric / ply derate         (stitch length, plies, fabric hand)
  3. operator guidance cap       (tracking tolerance vs path curvature)
  4. acceleration / deceleration (a short seam never reaches cruise speed)
  5. pivots and run-end costs    (corner turns, needle positioning, trim)

IP PROVENANCE
-------------
Contains NO predetermined-motion-time table data. No GSD codes, no MTM data
card values, no TMU-by-distance-class lookups. Every relationship here is a
continuous parametric function derived from kinematics (constant-acceleration
trapezoidal velocity profile) and from open, peer-reviewed motor-control
science (speed-accuracy tradeoff / iterative-corrections models of aimed
movement). All coefficients are FITTED to the factory's own time studies;
the defaults shipped here are explicitly labelled estimates.

UNIT CONVENTION (project standard, do not change)
-------------------------------------------------
1 TMU = 0.0006 min = 0.036 s;  1 s = 27.777... TMU;  1 min = 1666.67 TMU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Sequence

MM_PER_INCH = 25.4
TMU_PER_SECOND = 1.0 / 0.036          # 27.7778
TMU_PER_MINUTE = 1.0 / 0.0006         # 1666.667


# ----------------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------------

@dataclass
class MotionParams:
    """Fitted coefficients of the effective-speed model.

    `status` for every default is ESTIMATE unless noted. These are the
    quantities the calibration module fits to factory time-study data.
    """
    # -- acceleration limits (mm/s^2), operator-dominated, not motor-dominated
    a_up: float = 508.0      # ramp-in acceleration
    a_dn: float = 305.0      # ramp-out (approach-to-endpoint) deceleration

    # -- operator visuomotor correction interval (s)
    t_correct: float = 0.20

    # -- straight-line drift half-angle the operator tolerates (rad)
    theta_drift: float = 0.035

    # -- fixed costs
    t_pivot: float = 0.55    # s per in-seam corner pivot (stop, turn, restart)
    t_endstop: float = 0.13  # s needle-positioning / stop-accuracy at run end
    t_trim_auto: float = 0.25   # s automatic thread trim cycle
    t_trim_manual: float = 0.85  # s manual clip / pull-away

    # -- derates
    eta_set: float = 0.85    # set speed / rated speed
    eta_ply: float = 0.04    # fractional speed loss per ply above 2

    def as_dict(self) -> dict:
        return asdict(self)


# Guidance tolerance e (mm): how far off the intended stitch line the operator
# may drift before the result is rejected. Smaller e => lower speed cap.
GUIDANCE_TOLERANCE_MM = {
    "mechanically_guided": 2.50,   # edge guide, folder, binder or puller holds the path
    "seam_hidden": 1.20,           # seam allowance later covered / overlocked
    "seam_visible": 0.70,          # construction seam that shows on the outside
    "topstitch": 0.40,             # decorative topstitch, edge-stitch
    "edgestitch_critical": 0.25,   # 1 mm edge-stitch on collar / cuff / placket
}

# Curvature classes for woven tops, as path radius of curvature R (mm).
# R = inf  -> straight.  Values are geometric properties of shirt patterns.
CURVATURE_CLASSES_MM = {
    "straight": math.inf,
    "gentle": 300.0,       # bottom-hem sweep, side-seam waist shaping
    "moderate": 120.0,     # collar outer edge, back of armhole, cuff long edge
    "tight": 60.0,         # front scye, underarm, collar band ends
    "very_tight": 22.0,    # collar point, cuff corner radius, pocket point
}


@dataclass
class Segment:
    """One geometrically homogeneous piece of a stitching run."""
    length_mm: float
    curvature: str = "straight"          # key of CURVATURE_CLASSES_MM
    guidance: str = "seam_hidden"        # key of GUIDANCE_TOLERANCE_MM
    pivot_after: bool = False            # operator stops and turns at the end


@dataclass
class Run:
    """A continuous stitching run: needle down to thread trim."""
    segments: Sequence[Segment]
    spi: float = 12.0                    # stitches per inch
    plies: int = 2
    fabric_factor: float = 1.00          # 1.0 = mid-weight poplin reference
    auto_trim: bool = True
    label: str = ""


# ----------------------------------------------------------------------------
# Component functions
# ----------------------------------------------------------------------------

def stitch_density_per_mm(spi: float) -> float:
    """rho: stitches per mm of seam."""
    return spi / MM_PER_INCH


def machine_speed_cap_spm(rated_spm: float, plies: int, fabric_factor: float,
                          p: MotionParams) -> float:
    """Sustainable machine set speed, sti/min. Derate 1 and 2."""
    ply_derate = max(0.35, 1.0 - p.eta_ply * max(0, plies - 2))
    return rated_spm * p.eta_set * ply_derate * fabric_factor


def guidance_speed_cap_mms(curvature: str, guidance: str,
                           p: MotionParams) -> float:
    """Operator guidance speed cap, mm/s.

    Two regimes, both from the speed-accuracy tradeoff of visually guided
    corrective movement with correction interval T_c and tolerance e:

    STRAIGHT  the operator corrects lateral drift every T_c. Drift accumulated
              in one interval at heading error theta is v*T_c*theta, and must
              stay inside e:
                  v_straight = e / (T_c * theta)

    CURVED    on a path of radius R the operator approximates the curve by
              chords of length c = v*T_c. The sagitta (mid-chord deviation) of
              a chord on a circle of radius R is c^2/(8R), and must stay inside
              e:
                  v_curve = sqrt(8 * e * R) / T_c
    """
    e = GUIDANCE_TOLERANCE_MM[guidance]
    R = CURVATURE_CLASSES_MM[curvature]
    v_straight = e / (p.t_correct * p.theta_drift)
    if math.isinf(R):
        return v_straight
    v_curve = math.sqrt(8.0 * e * R) / p.t_correct
    return min(v_straight, v_curve)


def characteristic_ramp_length_mm(v_cap_mms: float, p: MotionParams) -> float:
    """L0 = d_in + d_out, the seam length below which cruise is never reached.

    d_in  = v^2 / (2 a_up)     d_out = v^2 / (2 a_dn)
    """
    return 0.5 * v_cap_mms ** 2 * (1.0 / p.a_up + 1.0 / p.a_dn)


def ramp_efficiency(length_mm: float, v_cap_mms: float,
                    p: MotionParams) -> float:
    """Phi(L): achieved mean speed / cruise speed, for a rest-to-rest run.

    Constant-acceleration trapezoidal velocity profile:

        L >= L0   trapezoid   t = (L + L0) / v_cap   ->  Phi = L / (L + L0)
        L <  L0   triangle    t = 2*sqrt(L*L0)/v_cap ->  Phi = sqrt(L/L0) / 2

    Continuous at L = L0 (both give 1/2). Phi -> 1 as L -> inf, which is what
    reproduces the theoretical no-ramping maximum in the long-seam limit.
    """
    if length_mm <= 0:
        return 0.0
    L0 = characteristic_ramp_length_mm(v_cap_mms, p)
    if L0 <= 0:
        return 1.0
    if length_mm >= L0:
        return length_mm / (length_mm + L0)
    return math.sqrt(length_mm / L0) / 2.0


# ----------------------------------------------------------------------------
# Run-level solution
# ----------------------------------------------------------------------------

def _segment_speed_caps(run: Run, rated_spm: float,
                        p: MotionParams) -> list[float]:
    """Per-segment speed cap in mm/s = min(machine cap, guidance cap)."""
    rho = stitch_density_per_mm(run.spi)
    n_mach = machine_speed_cap_spm(rated_spm, run.plies, run.fabric_factor, p)
    v_mach = n_mach / (rho * 60.0)
    return [min(v_mach, guidance_speed_cap_mms(s.curvature, s.guidance, p))
            for s in run.segments]


def solve_run(run: Run, rated_spm: float,
              p: MotionParams | None = None) -> dict:
    """Time a stitching run. Returns a fully auditable breakdown.

    A run is decomposed into rest-to-rest sub-runs at every pivot. Within a
    sub-run each segment is timed at its own cap, and the ramp penalty is
    applied once to the sub-run as a whole using the length-weighted mean cap
    (the operator ramps in once and lands once, not per segment).
    """
    p = p or MotionParams()
    rho = stitch_density_per_mm(run.spi)
    caps = _segment_speed_caps(run, rated_spm, p)

    # split into rest-to-rest sub-runs at pivots
    sub, cur = [], []
    for seg, cap in zip(run.segments, caps):
        cur.append((seg, cap))
        if seg.pivot_after:
            sub.append(cur)
            cur = []
    if cur:
        sub.append(cur)

    n_pivots = sum(1 for s in run.segments if s.pivot_after)
    t_sew, detail = 0.0, []
    for block in sub:
        L_block = sum(seg.length_mm for seg, _ in block)
        if L_block <= 0:
            continue
        # cruise time at each segment's own cap
        t_cruise = sum(seg.length_mm / cap for seg, cap in block)
        v_eff_cruise = L_block / t_cruise            # harmonic, length-weighted
        phi = ramp_efficiency(L_block, v_eff_cruise, p)
        t_block = t_cruise / phi
        t_sew += t_block
        detail.append({
            "length_mm": round(L_block, 2),
            "cruise_speed_mms": round(v_eff_cruise, 2),
            "L0_mm": round(characteristic_ramp_length_mm(v_eff_cruise, p), 2),
            "ramp_efficiency": round(phi, 4),
            "sew_time_s": round(t_block, 4),
        })

    t_trim = p.t_trim_auto if run.auto_trim else p.t_trim_manual
    t_fixed = n_pivots * p.t_pivot + p.t_endstop + t_trim
    t_total = t_sew + t_fixed

    L_total = sum(s.length_mm for s in run.segments)
    stitches = L_total * rho
    n_mach = machine_speed_cap_spm(rated_spm, run.plies, run.fabric_factor, p)

    return {
        "label": run.label,
        "seam_length_mm": round(L_total, 2),
        "spi": run.spi,
        "stitches": round(stitches, 1),
        "rated_spm": rated_spm,
        "machine_set_spm": round(n_mach, 1),
        "sew_time_s": round(t_sew, 4),
        "pivot_time_s": round(n_pivots * p.t_pivot, 4),
        "endstop_time_s": round(p.t_endstop, 4),
        "trim_time_s": round(t_trim, 4),
        "total_time_s": round(t_total, 4),
        "total_time_min": round(t_total / 60.0, 5),
        "total_tmu": round(t_total * TMU_PER_SECOND, 1),
        # headline: achieved average spindle speed over the stitching portion
        "achieved_avg_spm_sewing": round(stitches / (t_sew / 60.0), 1) if t_sew > 0 else 0.0,
        # including fixed costs -- the number that drives SMV
        "achieved_avg_spm_cycle": round(stitches / (t_total / 60.0), 1) if t_total > 0 else 0.0,
        "utilisation_vs_rated": round(stitches / (t_sew / 60.0) / rated_spm, 4) if t_sew > 0 else 0.0,
        "blocks": detail,
    }


# ----------------------------------------------------------------------------
# Convenience: single homogeneous seam
# ----------------------------------------------------------------------------

def simple_seam(length_mm: float, rated_spm: float, spi: float = 12.0,
                curvature: str = "straight", guidance: str = "seam_hidden",
                plies: int = 2, auto_trim: bool = True,
                p: MotionParams | None = None) -> dict:
    return solve_run(
        Run(segments=[Segment(length_mm, curvature, guidance)], spi=spi,
            plies=plies, auto_trim=auto_trim,
            label=f"{length_mm:.0f} mm {curvature} {guidance}"),
        rated_spm, p)


def coverage_yd_per_min(length_mm: float, rated_spm: float, spi: float,
                        curvature: str = "straight",
                        guidance: str = "mechanically_guided",
                        p: MotionParams | None = None,
                        include_fixed: bool = False) -> float:
    """Seam coverage rate in yards/min -- the units of the grounded check."""
    r = simple_seam(length_mm, rated_spm, spi=spi, curvature=curvature,
                    guidance=guidance, p=p)
    t_min = r["total_time_min"] if include_fixed else r["sew_time_s"] / 60.0
    return (length_mm / 914.4) / t_min


def theoretical_max_yd_per_min(rated_spm: float, spi: float) -> float:
    """No ramping, no derate, no guidance cap: rated_spm / SPI, in yd/min.

    This is the closed-form the project context pins the model against:
    5000 sti/min at 8 SPI -> 17.4 yd/min; at 14 SPI -> 9.9 yd/min.
    """
    return rated_spm / spi / 36.0
