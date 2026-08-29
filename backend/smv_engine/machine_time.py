"""
machine_time.py -- Machine-class catalog + seam/cycle machine-time wrapper.

Pillar 1 (MACHINE TIME) of the self-calibrating synthetic engine, at the
level the SMV-assembly module (pillar 4) actually calls: given a machine
CODE from machine_classes.csv and a seam or cycle-operation description
lifted straight out of seam_geometry.json, produce a fully auditable
machine-time breakdown.

All the physics live in effective_spm.py (Fitts/steering-law derived,
IP-clean per its own docstring); this module's job is purely the
plumbing between the catalog data and that solver, plus a small,
clearly-labelled model for cycle machines (buttonhole/bartack/button-sew)
that effective_spm.py does not itself cover.

Public API
----------
    load_machine_catalog(path="machine_classes.csv") -> MachineCatalog
    MachineCatalog.get(code) -> dict (raw catalog row)
    time_seam(catalog, machine_class, path_length_mm, spi, ...) -> dict
    time_cycle(catalog, machine_class, stitches, ...) -> dict

CYCLE-MACHINE MODELING NOTE (read before trusting cycle-time numbers)
----------------------------------------------------------------------
effective_spm.py's guidance-speed-cap model assumes a human operator is
visually tracking a stitch line in real time. Cycle machines (computer-
controlled buttonhole, bartack, button-sew) instead run a fixed cam/servo
program: the clamp follows a pre-taught path at the machine's own set
speed, and the operator does not steer it stitch-by-stitch. The guidance
term therefore does not apply. This module models cycle-machine time as

    t_sew  = stitches / machine_set_spm * 60        (no ramp, no guidance cap)
    t_total = t_sew + t_endstop + t_trim

This is an explicit ASSUMPTION distinguishing it from the seam model, not
a literature-derived equation -- flagged `status: "ASSUMPTION"` in every
cycle-time result so the calibration module can treat it separately, and
so a reviewer knows it is not derived the way the seam model is.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass

import effective_spm as es


# --------------------------------------------------------------------------
# Machine-class catalog
# --------------------------------------------------------------------------

_BOOL_COLS = {"auto_trim", "needle_pos", "auto_foot_lift"}
_FLOAT_COLS = {"rated_spm", "typical_spm", "speed_multiplier"}


def _parse_row(row: dict) -> dict:
    out = dict(row)
    for c in _BOOL_COLS:
        v = row.get(c, "")
        out[c] = (v == "Y") if v in ("Y", "N") else None
    for c in _FLOAT_COLS:
        v = row.get(c, "")
        try:
            out[c] = float(v) if v not in ("", None) else None
        except ValueError:
            out[c] = None
    return out


class MachineCatalog:
    """Wraps machine_classes.csv: machine and attachment rows keyed by code."""

    def __init__(self, rows: list[dict]):
        self.rows = {r["code"]: r for r in rows}
        self.machines = {c: r for c, r in self.rows.items() if r["record_type"] == "machine"}
        self.attachments = {c: r for c, r in self.rows.items() if r["record_type"] == "attachment"}

    def get(self, code: str) -> dict:
        if code not in self.rows:
            raise KeyError(f"unknown machine/attachment code {code!r}")
        return self.rows[code]

    def list_machines(self) -> list[str]:
        return sorted(self.machines)

    def list_attachments(self) -> list[str]:
        return sorted(self.attachments)


def load_machine_catalog(path: str = "machine_classes.csv") -> MachineCatalog:
    with open(path, newline="") as fh:
        rows = [_parse_row(r) for r in csv.DictReader(fh)]
    return MachineCatalog(rows)


# --------------------------------------------------------------------------
# Seam-operation machine time (wraps effective_spm.solve_run)
# --------------------------------------------------------------------------

def time_seam(
    catalog: MachineCatalog,
    machine_class: str,
    path_length_mm: float | list[float],
    spi: float,
    curvature_class: str | list[str] = "straight",
    guidance_class: str | None = None,
    plies: int = 2,
    pivots: int = 0,
    attachment: str | None = None,
    label: str = "",
    p: "es.MotionParams | None" = None,
) -> dict:
    """Time one continuous stitching run using a catalog machine class.

    `path_length_mm`/`curvature_class` may each be a single value (one
    homogeneous segment) or parallel lists describing several segments of
    one run (e.g. a collar with straight sides and tight-radius points).
    `pivots` in-seam corner stops are distributed evenly across internal
    segment boundaries when a single homogeneous segment is given, or read
    directly as `pivot_after` flags when the caller passes per-segment
    curvature and wants explicit control (use `segments=` in that case --
    see `time_seam_explicit`).

    `guidance_class=None` falls back to the machine's own catalog
    `guidance_default`. If `attachment` is given, its `guidance_default`
    overrides the machine's (a mechanical guide/folder/binder changes what
    tolerance regime the operator is actually working to), and its
    `speed_multiplier` derates the seam-speed cap for the drag/friction of
    the attachment itself.
    """
    mrow = catalog.get(machine_class)
    if mrow["record_type"] != "machine":
        raise ValueError(f"{machine_class!r} is not a machine ({mrow['record_type']!r})")
    rated_spm = mrow["rated_spm"]
    auto_trim = mrow["auto_trim"] if mrow["auto_trim"] is not None else True

    fabric_factor = 1.0
    if attachment is not None:
        arow = catalog.get(attachment)
        if arow["record_type"] != "attachment":
            raise ValueError(f"{attachment!r} is not an attachment")
        fabric_factor = arow["speed_multiplier"] if arow["speed_multiplier"] is not None else 1.0
        if guidance_class is None:
            guidance_class = arow["guidance_default"]
    if guidance_class is None:
        guidance_class = mrow["guidance_default"]

    lengths = path_length_mm if isinstance(path_length_mm, list) else [path_length_mm]
    curvs = curvature_class if isinstance(curvature_class, list) else [curvature_class] * len(lengths)
    if len(curvs) != len(lengths):
        raise ValueError("path_length_mm and curvature_class lists must be the same length")

    n_segs = len(lengths)
    # distribute `pivots` in-seam pivots across internal segment boundaries
    if pivots > n_segs - 1 and n_segs > 1:
        raise ValueError(f"cannot place {pivots} pivots across only {n_segs} segments")
    segments = []
    for i, (L, cv) in enumerate(zip(lengths, curvs)):
        pivot_after = (i < n_segs - 1) and (i < pivots)
        segments.append(es.Segment(length_mm=L, curvature=cv, guidance=guidance_class,
                                    pivot_after=pivot_after))
    if n_segs == 1 and pivots > 0:
        # single homogeneous segment described as visiting `pivots` corners:
        # split evenly so each pivot cost is charged once at each corner.
        L = lengths[0] / (pivots + 1)
        segments = [es.Segment(length_mm=L, curvature=curvs[0], guidance=guidance_class,
                                pivot_after=(i < pivots)) for i in range(pivots + 1)]

    run = es.Run(segments=segments, spi=spi, plies=plies, fabric_factor=fabric_factor,
                 auto_trim=auto_trim, label=label or f"{machine_class} seam")
    result = es.solve_run(run, rated_spm, p)
    result["machine_class"] = machine_class
    result["attachment"] = attachment
    result["guidance_class_used"] = guidance_class
    result["status"] = "MODEL (effective_spm.py kinematic derivation)"
    return result


# --------------------------------------------------------------------------
# Cycle-operation machine time (buttonhole / bartack / button-sew)
# --------------------------------------------------------------------------

def time_cycle(
    catalog: MachineCatalog,
    machine_class: str,
    stitches: float,
    plies: int = 2,
    fabric_factor: float = 1.0,
    p: "es.MotionParams | None" = None,
) -> dict:
    """Time one cycle-machine actuation (buttonhole, bartack, button-sew).

    See module docstring for the modeling assumption: no ramp, no
    operator guidance cap -- the machine runs its own taught program at
    its derated set speed.
    """
    mrow = catalog.get(machine_class)
    if mrow["record_type"] != "machine":
        raise ValueError(f"{machine_class!r} is not a machine ({mrow['record_type']!r})")
    p = p or es.MotionParams()
    rated_spm = mrow["rated_spm"]
    auto_trim = mrow["auto_trim"] if mrow["auto_trim"] is not None else True

    machine_set_spm = es.machine_speed_cap_spm(rated_spm, plies, fabric_factor, p)
    t_sew = stitches / machine_set_spm * 60.0
    t_trim = p.t_trim_auto if auto_trim else p.t_trim_manual
    t_total = t_sew + p.t_endstop + t_trim

    return {
        "machine_class": machine_class,
        "stitches": stitches,
        "rated_spm": rated_spm,
        "machine_set_spm": round(machine_set_spm, 1),
        "sew_time_s": round(t_sew, 4),
        "endstop_time_s": round(p.t_endstop, 4),
        "trim_time_s": round(t_trim, 4),
        "total_time_s": round(t_total, 4),
        "total_time_min": round(t_total / 60.0, 5),
        "total_tmu": round(t_total * es.TMU_PER_SECOND, 1),
        "status": "ASSUMPTION (no operator-guidance term; see module docstring)",
    }


# --------------------------------------------------------------------------
# Pure machine-cap seam time (for assembly_rules.machine_overlap)
# --------------------------------------------------------------------------
#
# time_seam() above reproduces effective_spm.py's own blended model, which
# folds the operator-guidance cap directly into its per-segment speed cap
# (see effective_spm.guidance_speed_cap_mms / _segment_speed_caps). That is
# the right function to call standalone -- e.g. for the Phase-0 benchmark
# cross-check, where no separate handling-time guide element exists.
#
# element_taxonomy.json's assembly_rules.machine_overlap, however, specifies
# a strict two-pillar decomposition for SMV assembly: t_seam = MAX(t_machine,
# t_guide) where t_machine comes ONLY from the machine-time pillar (rated
# speed, set-speed/ply/fabric derates, and the ramp/pivot/trim kinematics --
# NOT the guidance cap) and t_guide comes from the HGD handling element
# (handling_time.py), which has its own independently-fitted steering-law
# coefficients (a_steer, b_steer, k_R). Assembling a seam therefore needs
# the *pure* machine-cap time below, so the two pillars are genuinely
# independent estimates and the MAX (and which one binds) is meaningful.

def pure_machine_time_seam(
    catalog: MachineCatalog,
    machine_class: str,
    path_length_mm: float,
    spi: float,
    plies: int = 2,
    pivots: int = 0,
    attachment: str | None = None,
    label: str = "",
    p: "es.MotionParams | None" = None,
) -> dict:
    """Machine-time-only estimate for one seam run: rated speed, set-speed/
    ply/fabric derates, and ramp/pivot/trim kinematics -- with NO operator-
    guidance cap folded in (that is HGD's job; see module note above).

    pivots in-seam corner stops split the run into `pivots + 1` equal-length
    rest-to-rest blocks (matching time_seam's single-homogeneous-segment
    convention), each independently ramp-limited at the same uniform cap
    (uniform because, with no guidance term, cap does not vary along the run).
    """
    mrow = catalog.get(machine_class)
    if mrow["record_type"] != "machine":
        raise ValueError(f"{machine_class!r} is not a machine ({mrow['record_type']!r})")
    p = p or es.MotionParams()
    rated_spm = mrow["rated_spm"]
    auto_trim = mrow["auto_trim"] if mrow["auto_trim"] is not None else True

    fabric_factor = 1.0
    if attachment is not None:
        arow = catalog.get(attachment)
        if arow["record_type"] != "attachment":
            raise ValueError(f"{attachment!r} is not an attachment")
        fabric_factor = arow["speed_multiplier"] if arow["speed_multiplier"] is not None else 1.0

    rho = es.stitch_density_per_mm(spi)
    n_mach = es.machine_speed_cap_spm(rated_spm, plies, fabric_factor, p)
    v_mach = n_mach / (rho * 60.0)

    n_blocks = pivots + 1
    block_len = path_length_mm / n_blocks
    t_cruise_block = block_len / v_mach
    phi = es.ramp_efficiency(block_len, v_mach, p)
    t_block = t_cruise_block / phi
    t_sew = n_blocks * t_block

    t_trim = p.t_trim_auto if auto_trim else p.t_trim_manual
    t_fixed = pivots * p.t_pivot + p.t_endstop + t_trim
    t_total = t_sew + t_fixed

    stitches = path_length_mm * rho

    return {
        "label": label or f"{machine_class} seam (pure machine cap)",
        "seam_length_mm": round(path_length_mm, 2),
        "spi": spi,
        "stitches": round(stitches, 1),
        "rated_spm": rated_spm,
        "machine_set_spm": round(n_mach, 1),
        "sew_time_s": round(t_sew, 4),
        "pivot_time_s": round(pivots * p.t_pivot, 4),
        "endstop_time_s": round(p.t_endstop, 4),
        "trim_time_s": round(t_trim, 4),
        "total_time_s": round(t_total, 4),
        "total_time_min": round(t_total / 60.0, 5),
        "total_tmu": round(t_total * es.TMU_PER_SECOND, 1),
        "achieved_avg_spm_cycle": round(stitches / (t_total / 60.0), 1) if t_total > 0 else 0.0,
        "n_blocks": n_blocks,
        "block_length_mm": round(block_len, 2),
        "ramp_efficiency": round(phi, 4),
        "machine_class": machine_class,
        "attachment": attachment,
        "status": "MODEL (pure machine cap: no guidance term; see module note above)",
    }


if __name__ == "__main__":
    cat = load_machine_catalog("machine_classes.csv")
    print(f"Loaded catalog: {len(cat.machines)} machines, {len(cat.attachments)} attachments")

    r = time_seam(cat, "SNLS-UBT", path_length_mm=445.7, spi=14,
                  curvature_class="moderate", plies=2, pivots=2, label="collar run-stitch, size M")
    print(f"Collar run-stitch (M): total_time_s={r['total_time_s']}, "
          f"achieved_avg_spm_cycle={r['achieved_avg_spm_cycle']}")

    r2 = time_cycle(cat, "BH-LS", stitches=88)
    print(f"Buttonhole (BH-LS, 88 stitches): total_time_s={r2['total_time_s']}")
