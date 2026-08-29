"""analytics_router.py -- wires the Analytics track (line balancing, costing,
what-if scenario comparison) into the FastAPI application.

The analytics modules (app/analytics/{line_balancing,costing,what_if}.py)
were built standalone against the vendored engine and know nothing about
FastAPI, PostgreSQL, or this app's models -- this router is the ONLY glue.
It loads a style's persisted operations from the database, converts them
into the engine Operation objects the analytics functions expect (via
engine_bridge, so no engine import happens here directly -- consistent
with the rest of the backend's "engine_bridge is the only place that
imports the engine" rule), calls the analytics function, and returns the
result. Nothing here computes a timing number itself; every number comes
from smv_assembly (through engine_bridge/analytics) or a plain arithmetic
identity in costing.py that is cited in that module's own docstring.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app import auth, models, schemas, policy_service
from app.database import get_db
from app.routers.styles_router import _get_style_or_404

router = APIRouter(prefix="/styles", tags=["analytics"])

_ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "..", "analytics")
_ANALYTICS_DIR = os.path.abspath(_ANALYTICS_DIR)
if _ANALYTICS_DIR not in sys.path:
    sys.path.insert(0, _ANALYTICS_DIR)

import line_balancing as lb   # noqa: E402
import costing as ct          # noqa: E402
import what_if as wi          # noqa: E402

from app import engine_bridge  # noqa: E402


@lru_cache(maxsize=1)
def _engine_context():
    """Builds an analytics EngineContext (tax/mcat/pol/sa/sl handles) from
    the SAME vendored engine dir engine_bridge.py already uses -- one
    engine, one set of physical constants, never two competing loads."""
    import engine_loader as el
    return el.load_engine_context(engine_bridge._ENGINE_DIR)


def _style_operations_for_engine(db: OrmSession, style_id: str) -> list:
    """Loads a style's persisted operations (in sequence order) and builds
    the same sa.Operation objects engine_bridge.compute_style() builds --
    the shape line_balancing/what_if expect as `operations`/`style`."""
    ctx = _engine_context()
    ops_rows = db.query(models.Operation).filter(
        models.Operation.style_id == style_id
    ).order_by(models.Operation.sequence).all()
    if not ops_rows:
        raise HTTPException(status_code=400, detail="style has no operations")
    return [ctx.sa.Operation(name=o.name, steps=o.steps, bundle_size=o.bundle_size)
            for o in ops_rows]


def _assembled_style(db: OrmSession, style_id: str, allowance_profile: str) -> dict:
    ctx = _engine_context()
    ops = _style_operations_for_engine(db, style_id)
    policy_row = policy_service.get_active(db)
    if policy_row is None:
        raise HTTPException(status_code=400, detail="no allowance policy available")
    pol = engine_bridge.build_allowance_policy(policy_row.document)
    return engine_bridge._sanitize_json(
        ctx.sa.assemble_style(ctx.tax, ctx.mcat, pol, ops, allowance_profile=allowance_profile)
    )


@router.post("/{style_id}/line-balance", response_model=schemas.LineBalanceOut)
def line_balance(style_id: str, payload: schemas.LineBalanceRequest,
                  db: OrmSession = Depends(get_db),
                  user: models.User = Depends(auth.require_any_authenticated)):
    _get_style_or_404(db, style_id)
    style = _assembled_style(db, style_id, payload.allowance_profile)
    try:
        result = lb.balance_line(
            style, n_workstations=payload.n_workstations,
            target_rate_per_hour=payload.target_rate_per_hour,
            target_rate_per_day=payload.target_rate_per_day,
            shift_hours=payload.shift_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/{style_id}/costing", response_model=dict)
def costing(style_id: str, payload: schemas.CostingRequest,
            db: OrmSession = Depends(get_db),
            user: models.User = Depends(auth.require_any_authenticated)):
    _get_style_or_404(db, style_id)
    style = _assembled_style(db, style_id, payload.allowance_profile)
    try:
        return ct.full_costing_report(
            style, labour_rate_per_hour=payload.labour_rate_per_hour,
            efficiency=payload.efficiency, n_operators=payload.n_operators,
            target_output_per_hour=payload.target_output_per_hour,
            target_output_per_day=payload.target_output_per_day,
            shift_hours=payload.shift_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{style_id}/what-if", response_model=dict)
def what_if_scenario(style_id: str, payload: schemas.WhatIfRequest,
                      db: OrmSession = Depends(get_db),
                      user: models.User = Depends(auth.require_writer)):
    """require_writer, not require_any_authenticated: a what-if run is cheap
    engine compute but conceptually a proposed EDIT under evaluation, so it
    is gated the same as other style-mutating actions -- it does not persist
    anything, but a viewer should not be running scenario comparisons any
    more than they can edit an operation directly."""
    _get_style_or_404(db, style_id)
    ctx = _engine_context()
    operations = _style_operations_for_engine(db, style_id)
    try:
        result = wi.compare_style(
            ctx, operations, payload.operation_name, payload.changes,
            step_kind=payload.step_kind, element=payload.element,
            step_index=payload.step_index, allowance_profile=payload.allowance_profile,
            match=payload.match, n_workstations=payload.n_workstations,
            target_rate_per_hour=payload.target_rate_per_hour,
            labour_rate_per_hour=payload.labour_rate_per_hour,
            line_efficiency=payload.line_efficiency,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return engine_bridge._sanitize_json(result)
