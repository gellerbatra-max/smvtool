from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import auth, models, engine_bridge, policy_service
from app.database import get_db

router = APIRouter(prefix="/library", tags=["library"])


@router.get("")
def browse_library(user: models.User = Depends(auth.require_any_authenticated)):
    """Menu of the seeded shirt_library.py operation library: variants,
    sizes, and the seam/cycle operation names sourced from seam_geometry.json.
    No SMV numbers here -- see /library/bulletin for a computed bulletin."""
    return engine_bridge.library_catalog()


@router.get("/bulletin")
def library_bulletin(
    size: str = Query("M"), variant: str = Query("CLASSIC"),
    bundle_size: int = Query(20), allowance_profile: str = Query("WOVEN_TOPS_DECOMPOSED"),
    db: Session = Depends(get_db), user: models.User = Depends(auth.require_any_authenticated),
):
    """Computed operation bulletin straight from shirt_library.style_smv()'s
    underlying calls (engine_bridge.library_style_bulletin), without needing
    to first create a persisted Style row -- useful for browsing the library
    interactively before deciding to seed a style from it."""
    if variant not in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
        raise HTTPException(status_code=400, detail=f"unknown variant {variant!r}")
    policy_row = policy_service.get_active(db)
    result = engine_bridge.library_style_bulletin(size, variant, bundle_size,
                                                    policy_row.document, allowance_profile)
    return {
        "size": size, "variant": variant, "bundle_size": bundle_size,
        "allowance_profile": allowance_profile,
        "smv_min": result["SMV_min"], "smv_tmu": result["SMV_tmu"],
        "engine_version": engine_bridge.ENGINE_VERSION,
        "operations": result["operations"],
        "warnings": result["all_warnings"],
    }
