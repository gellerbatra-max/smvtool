"""
time_study_loader.py -- validating loader for time_study_schema.json.

Loads one or more study_batch JSON files, validates every observation against
the engine's own element/machine catalogs (element_taxonomy.json,
machine_classes.csv) and the schema's declared value domains, and returns a
flat, analysis-ready table (one row per observation) plus a rejection log.

This module deliberately duplicates none of handling_time.py's/machine_time.py's
computation -- it only validates *shape* here. calibration_fit.py is the
module that actually calls compute_element()/pure_machine_time_seam() on each
accepted row to get the engine's prediction for residual analysis.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import handling_time as ht
import machine_time as mt

OBSERVATION_KINDS = (
    "element_observation", "seam_observation", "cycle_observation", "operation_observation",
)
VALID_METHODS = {
    "STOPWATCH_CONTINUOUS", "STOPWATCH_SNAPBACK", "VIDEO_FRAME",
    "MOST_PREDETERMINED", "WORK_SAMPLING", "SYNTHETIC",
}
VALID_CURVATURE = {"straight", "gentle", "moderate", "tight"}
VALID_GUIDANCE = {"mechanically_guided", "seam_hidden", "seam_visible", "topstitch", "edgestitch_critical"}


@dataclass
class Rejection:
    batch_id: str
    observation_id: str
    reason: str


@dataclass
class LoadResult:
    rows: list = field(default_factory=list)          # accepted, flattened observation dicts
    rejections: list = field(default_factory=list)     # list[Rejection]
    n_batches: int = 0
    n_observations_seen: int = 0

    def rows_df(self):
        import pandas as pd
        return pd.DataFrame(self.rows)


class TimeStudyLoader:
    """Validates study_batch records against the taxonomy's own element/machine
    catalogs before calibration_fit.py ever sees them."""

    def __init__(self, taxonomy: "ht.Taxonomy", machine_catalog: "mt.MachineCatalog"):
        self.tax = taxonomy
        self.mcat = machine_catalog
        self._element_params = {
            code: {p["name"]: p for p in e["parameters"]}
            for code, e in taxonomy.elements.items()
        }

    def load_batches(self, paths: list) -> LoadResult:
        result = LoadResult()
        for path in paths:
            with open(path) as fh:
                batch = json.load(fh)
            self._load_one_batch(batch, result)
        return result

    def load_batch_dict(self, batch: dict, result: LoadResult | None = None) -> LoadResult:
        result = result or LoadResult()
        self._load_one_batch(batch, result)
        return result

    # -- internal -----------------------------------------------------------

    def _load_one_batch(self, batch: dict, result: LoadResult) -> None:
        for req in ("batch_id", "factory_id", "method", "rater_id", "date_range",
                    "performance_rating_applied", "observations"):
            if req not in batch:
                raise ValueError(f"study_batch missing required field {req!r}")
        if batch["method"] not in VALID_METHODS:
            raise ValueError(f"batch {batch['batch_id']}: unknown method {batch['method']!r}")

        result.n_batches += 1
        for obs in batch["observations"]:
            result.n_observations_seen += 1
            try:
                row = self._validate_observation(batch, obs)
                result.rows.append(row)
            except ValueError as exc:
                result.rejections.append(
                    Rejection(batch["batch_id"], obs.get("observation_id", "?"), str(exc))
                )

    def _validate_observation(self, batch: dict, obs: dict) -> dict:
        for req in ("observation_id", "operator_id", "observed_s"):
            if req not in obs:
                raise ValueError(f"observation missing required field {req!r}")

        observed_s = obs["observed_s"]
        if not isinstance(observed_s, (int, float)) or observed_s <= 0:
            raise ValueError(f"observed_s must be > 0, got {observed_s!r}")

        present_kinds = [k for k in OBSERVATION_KINDS if obs.get(k) is not None]
        if len(present_kinds) != 1:
            raise ValueError(
                f"exactly one of {OBSERVATION_KINDS} must be present, found {present_kinds}"
            )
        kind = present_kinds[0]

        pace = obs.get("pace_rating_pct")
        if pace is not None and not (50 <= pace <= 150):
            raise ValueError(f"pace_rating_pct {pace} outside [50, 150]")

        n_reps = obs.get("n_reps_averaged", 1)

        defaulted_fields = []
        detail = obs[kind]
        if kind == "element_observation":
            code = detail["element_code"]
            if code not in self.tax.elements:
                raise ValueError(f"unknown element_code {code!r}")
            params = detail.get("params", {})
            sig = self._element_params[code]
            unknown = set(params) - set(sig)
            if unknown:
                raise ValueError(f"{code}: unknown parameter(s) {sorted(unknown)}")
            for name, p in sig.items():
                if name not in params:
                    defaulted_fields.append(name)
                    continue
                domain = p.get("domain")
                if domain is not None and params[name] is not None:
                    lo, hi = domain
                    if not (lo <= params[name] <= hi):
                        raise ValueError(
                            f"{code}: parameter {name!r}={params[name]} outside domain [{lo}, {hi}]"
                        )
        elif kind == "seam_observation":
            mclass = detail["machine_class"]
            if mclass not in self.mcat.machines:
                raise ValueError(f"unknown machine_class {mclass!r} (not in machine_classes.csv)")
            if detail.get("curvature_class") not in VALID_CURVATURE:
                raise ValueError(f"invalid curvature_class {detail.get('curvature_class')!r}")
            if detail.get("guidance_class") not in VALID_GUIDANCE:
                raise ValueError(f"invalid guidance_class {detail.get('guidance_class')!r}")
            for req in ("path_length_mm", "spi", "plies"):
                if req not in detail:
                    raise ValueError(f"seam_observation missing {req!r}")
        elif kind == "cycle_observation":
            mclass = detail["machine_class"]
            if mclass not in self.mcat.machines:
                raise ValueError(f"unknown machine_class {mclass!r} (not in machine_classes.csv)")
            if "stitches" not in detail:
                raise ValueError("cycle_observation missing 'stitches'")
        elif kind == "operation_observation":
            if "operation_name" not in detail:
                raise ValueError("operation_observation missing 'operation_name'")

        return {
            "batch_id": batch["batch_id"],
            "factory_id": batch["factory_id"],
            "method": batch["method"],
            "rater_id": batch["rater_id"],
            "rater_qualification": batch.get("rater_qualification"),
            "performance_rating_applied": batch["performance_rating_applied"],
            "observation_id": obs["observation_id"],
            "operator_id": obs["operator_id"],
            "pace_rating_pct": pace,
            "n_reps_averaged": n_reps,
            "observed_s": observed_s,
            "kind": kind,
            "detail": detail,
            "defaulted_fields": defaulted_fields,
            "environment": obs.get("environment"),
        }


def load_taxonomy_and_catalog(taxonomy_path="element_taxonomy.json", machine_csv="machine_classes.csv"):
    return ht.load_taxonomy(taxonomy_path), mt.load_machine_catalog(machine_csv)


if __name__ == "__main__":
    tax, mcat = load_taxonomy_and_catalog()
    loader = TimeStudyLoader(tax, mcat)

    # Minimal smoke-test batch exercising all four observation kinds plus one
    # deliberate rejection (unknown element_code) and one domain violation.
    demo_batch = {
        "batch_id": "DEMO-001",
        "factory_id": "DEMO_FACTORY",
        "method": "STOPWATCH_CONTINUOUS",
        "rater_id": "analyst_1",
        "rater_qualification": "CERTIFIED_IE",
        "date_range": ["2026-08-01", "2026-08-02"],
        "performance_rating_applied": True,
        "observations": [
            {"observation_id": "o1", "operator_id": "op_1", "observed_s": 3.9, "n_reps_averaged": 1,
             "element_observation": {"element_code": "HAM",
                                      "params": {"distance_cm": 25.0, "plies": 2,
                                                 "match_precision": "P2", "fabric_class": "REF_POPLIN"}}},
            {"observation_id": "o2", "operator_id": "op_1", "observed_s": 60.0, "n_reps_averaged": 1,
             "seam_observation": {"machine_class": "SNLS-TOP", "path_length_mm": 445.7, "spi": 14,
                                   "plies": 3, "pivots": 2, "curvature_class": "moderate",
                                   "guidance_class": "topstitch"}},
            {"observation_id": "o3", "operator_id": "op_2", "observed_s": 12.0, "n_reps_averaged": 1,
             "cycle_observation": {"machine_class": "BH-LS", "stitches": 88}},
            {"observation_id": "o4", "operator_id": "op_2", "observed_s": 999.0, "n_reps_averaged": 1,
             "element_observation": {"element_code": "NOT_A_CODE", "params": {}}},
            {"observation_id": "o5", "operator_id": "op_2", "observed_s": 3.9, "n_reps_averaged": 1,
             "element_observation": {"element_code": "HAM",
                                      "params": {"distance_cm": 500.0, "plies": 2,
                                                 "match_precision": "P2", "fabric_class": "REF_POPLIN"}}},
        ],
    }
    result = loader.load_batch_dict(demo_batch)
    print(f"seen={result.n_observations_seen} accepted={len(result.rows)} rejected={len(result.rejections)}")
    for r in result.rejections:
        print(f"  REJECTED {r.observation_id}: {r.reason}")
