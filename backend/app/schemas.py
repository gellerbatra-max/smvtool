"""schemas.py -- Pydantic request/response models."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- auth ----

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserCreate(BaseModel):
    username: str
    full_name: str
    role: str = Field(description="ie_engineer | viewer | administrator")
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime.datetime


# -------------------------------------------------------------- styles ----

class OperationIn(BaseModel):
    name: str
    sequence: int = 0
    bundle_size: int = 20
    steps: list[dict[str, Any]]


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    style_id: str
    name: str
    sequence: int
    bundle_size: int
    steps: list[dict[str, Any]]
    created_at: datetime.datetime
    updated_at: datetime.datetime


class StyleCreate(BaseModel):
    name: str
    garment_type: str = "woven_shirt"
    variant: str = "CLASSIC"
    size: str = "M"
    bundle_size: int = 20
    notes: Optional[str] = None
    seed_from_library: bool = Field(
        default=False,
        description="If true, seed this style's operations from shirt_library.py's "
                    "operation bulletin for the given variant/size instead of starting empty.",
    )


class StyleUpdate(BaseModel):
    name: Optional[str] = None
    variant: Optional[str] = None
    size: Optional[str] = None
    bundle_size: Optional[int] = None
    notes: Optional[str] = None


class StyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    garment_type: str
    variant: str
    size: str
    bundle_size: int
    notes: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class StyleDetailOut(StyleOut):
    operations: list[OperationOut] = []


# ------------------------------------------------------------- compute ----

class ComputeRequest(BaseModel):
    allowance_profile: str = "WOVEN_TOPS_DECOMPOSED"
    allowance_policy_id: Optional[str] = Field(
        default=None,
        description="Specific allowance_policies row id to compute against. "
                    "Defaults to the currently-active policy for the style's garment type.",
    )


class SMVResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    operation_id: str
    style_id: str
    st_op_s: float
    st_op_min: float
    bt_op_s: float
    bt_op_min: float
    allowance_profile: str
    engine_version: str
    calibration_version: Optional[str] = None
    computed_at: datetime.datetime


class ComputeResponse(BaseModel):
    style_id: str
    smv_min: float
    smv_tmu: float
    bt_style_min: float
    allowance_profile: str
    engine_version: str
    warnings: list[str]
    results: list[SMVResultOut]


class BulletinOperation(BaseModel):
    operation_id: str
    name: str
    sequence: int
    bundle_size: int
    latest_result: Optional[dict[str, Any]] = None  # full SMVResult + audit trail


class BulletinOut(BaseModel):
    style: StyleOut
    operations: list[BulletinOperation]
    smv_min: Optional[float] = None
    smv_tmu: Optional[float] = None


# ------------------------------------------------------------ audit log ---

class ChangeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_type: str
    entity_id: str
    style_id: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: datetime.datetime
    action: str
    field: str
    prior_value: Optional[str] = None
    new_value: Optional[str] = None


# --------------------------------------------------------- allowance ------

class AllowancePolicyCreate(BaseModel):
    policy_name: str
    document: dict[str, Any]


class AllowancePolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    policy_name: str
    version: int
    is_active: bool
    created_at: datetime.datetime


# ------------------------------------------------------------ analytics ----
# Request/response shapes for the Analytics track (line_balancing.py /
# costing.py / what_if.py), wired in via analytics_router.py. Responses are
# typed `dict` at the route level (see analytics_router.py) because the
# analytics modules' own output dicts are already documented in
# app/analytics/../INTEGRATION.md and are stable but not currently mirrored
# as Pydantic models -- only the REQUEST shapes are validated here.

class LineBalanceRequest(BaseModel):
    allowance_profile: str = "WOVEN_TOPS_DECOMPOSED"
    n_workstations: Optional[int] = None
    target_rate_per_hour: Optional[float] = None
    target_rate_per_day: Optional[float] = None
    shift_hours: float = 8.0


class LineBalanceOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    method: str
    n_operations: int
    total_smv_min: float
    bottleneck_workstation: int
    bottleneck_smv_min: float
    theoretical_efficiency: float


class CostingRequest(BaseModel):
    allowance_profile: str = "WOVEN_TOPS_DECOMPOSED"
    labour_rate_per_hour: float
    efficiency: float = Field(0.85, gt=0.0, le=1.0)
    n_operators: Optional[float] = None
    target_output_per_hour: Optional[float] = None
    target_output_per_day: Optional[float] = None
    shift_hours: float = 8.0


class WhatIfRequest(BaseModel):
    allowance_profile: str = "WOVEN_TOPS_DECOMPOSED"
    operation_name: str
    changes: dict[str, Any]
    step_kind: Optional[str] = None
    element: Optional[str] = None
    step_index: Optional[int] = None
    match: str = "exact"
    n_workstations: Optional[int] = None
    target_rate_per_hour: Optional[float] = None
    labour_rate_per_hour: Optional[float] = None
    line_efficiency: float = Field(0.85, gt=0.0, le=1.0)
