from __future__ import annotations

from fastapi import APIRouter, Depends

from app import auth, models, engine_bridge

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/status")
def calibration_status(user: models.User = Depends(auth.require_any_authenticated)):
    """Honest data-quality surface: which engine coefficients are
    calibration-pending (shipped defaults awaiting real factory time-study
    data) vs literature-grounded, read straight off the vendored
    element_taxonomy.json's own status fields via
    engine_bridge.calibration_status_report() -- never fabricated, never a
    lookup table. (calibration_fit.calibrate_all() has not been run against
    real factory data yet, so this endpoint reports the taxonomy's shipped
    status, not a fitted-coefficient result -- see engine_bridge.py.)"""
    return engine_bridge.calibration_status_report()
