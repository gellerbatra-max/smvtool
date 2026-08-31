"""
models.py -- SQLAlchemy ORM models for the SMV application backend.

See SCHEMA.md for the full entity-relationship description and design
rationale. Summary of tables:

  users               - login accounts, role-based (ie_engineer/viewer/administrator)
  allowance_policies  - versioned snapshots of allowance_policy.json profiles;
                        every smv_results row stamps the policy VERSION it used
                        so historical SMVs stay reproducible even after a
                        factory edits its allowance policy
  styles              - a garment style: type/variant/size/name
  operations          - one row per operation belonging to a style; stores the
                        raw `steps` list (smv_assembly.Operation-shaped JSON)
                        needed to recompute via the engine
  smv_results         - one row per computed operation SMV: the engine's
                        output (ST_op_s/min, full per-step audit trail JSON),
                        plus which allowance_policy version and which engine/
                        calibration version stamp produced it
  change_log          - append-only audit trail: every write to styles/
                        operations/allowance_policies gets a row here (user,
                        timestamp, field, prior_value, new_value)

IP note: no SMV numbers, coefficients, or lookup tables are stored as static
data anywhere in this file -- `operations.steps` records only geometry/
element-selection INPUTS to the engine (path lengths, element codes, machine
classes, etc., all of which come from the caller / shirt_library.py), and
`smv_results` stores only the engine's own OUTPUT for a given input, never a
substitute for calling the engine.
"""
from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, ForeignKey, DateTime, Enum, UniqueConstraint,
    Boolean, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base, JSONBType


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class UserRole(str, enum.Enum):
    ie_engineer = "ie_engineer"
    viewer = "viewer"
    administrator = "administrator"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.viewer)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class AllowancePolicy(Base):
    """Versioned snapshot of an allowance-policy document (the JSON shape
    produced/consumed by allowance.AllowancePolicy / allowance_policy.json).
    A factory may edit its allowance policy over time; each edit creates a
    NEW row (version = previous max + 1 for that policy_name) rather than
    mutating an existing one, so smv_results rows that stamped an earlier
    version remain exactly reproducible."""
    __tablename__ = "allowance_policies"

    id = Column(String, primary_key=True, default=_uuid)
    policy_name = Column(String, nullable=False, index=True)  # e.g. "wt-allowance-policy"
    version = Column(Integer, nullable=False)  # monotonically increasing per policy_name
    document = Column(JSONBType, nullable=False)  # full policy JSON (spec/categories/profiles/...)
    is_active = Column(Boolean, nullable=False, default=True)  # the current one new computes use
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=True)

    created_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("policy_name", "version", name="uq_allowance_policy_version"),
    )


class Style(Base):
    __tablename__ = "styles"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    garment_type = Column(String, nullable=False, default="woven_shirt")
    variant = Column(String, nullable=False, default="CLASSIC")  # CLASSIC/SHORT_SLEEVE/BLOUSE_COLLARLESS
    size = Column(String, nullable=False, default="M")  # S/M/L/XL/XXL
    bundle_size = Column(Integer, nullable=False, default=20)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=True)

    created_by = relationship("User")
    operations = relationship("Operation", back_populates="style",
                               cascade="all, delete-orphan", order_by="Operation.sequence")

    def __repr__(self):
        return f"<Style {self.name} {self.variant}/{self.size}>"


class Operation(Base):
    """One operation belonging to a style. `steps` is the raw step-list
    (smv_assembly.Operation.steps-shaped JSON: handling/bundle/seam/cycle
    step dicts) needed to recompute this operation's SMV by calling
    smv_assembly.assemble_operation() -- never a stored SMV number itself."""
    __tablename__ = "operations"

    id = Column(String, primary_key=True, default=_uuid)
    style_id = Column(String, ForeignKey("styles.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False, default=0)  # position in the operation bulletin
    bundle_size = Column(Integer, nullable=False, default=20)
    steps = Column(JSONBType, nullable=False)  # list[dict] -- see smv_assembly.py step dict shapes

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    style = relationship("Style", back_populates="operations")
    results = relationship("SMVResult", back_populates="operation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Operation {self.name} (style={self.style_id})>"


class SMVResult(Base):
    """One computed-SMV record for an operation. Immutable once written --
    a recompute (e.g. after editing steps, or after an allowance-policy
    version bump) creates a NEW row, never an in-place update, so the
    history of what a given operation's SMV was at any point in time is
    preserved for payroll/incentive audit."""
    __tablename__ = "smv_results"

    id = Column(String, primary_key=True, default=_uuid)
    operation_id = Column(String, ForeignKey("operations.id"), nullable=False, index=True)
    style_id = Column(String, ForeignKey("styles.id"), nullable=False, index=True)

    st_op_s = Column(Float, nullable=False)
    st_op_min = Column(Float, nullable=False)
    bt_op_s = Column(Float, nullable=False)
    bt_op_min = Column(Float, nullable=False)

    audit_trail = Column(JSONBType, nullable=False)  # full assemble_operation() step_records + warnings
    allowance_profile = Column(String, nullable=False)  # profile name applied, e.g. WOVEN_TOPS_DECOMPOSED
    allowance_policy_version_id = Column(String, ForeignKey("allowance_policies.id"), nullable=True)

    engine_version = Column(String, nullable=False, default="unversioned")
    calibration_version = Column(String, nullable=True)  # None => shipped defaults, no calibration applied

    computed_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    computed_by_id = Column(String, ForeignKey("users.id"), nullable=True)

    operation = relationship("Operation", back_populates="results")
    computed_by = relationship("User")


class ChangeLog(Base):
    """Append-only audit trail. One row per changed field per write.
    Written by app.audit.record_change / the audit-logging decorator, never
    hand-rolled inside a route handler, so coverage is uniform across every
    mutating endpoint."""
    __tablename__ = "change_log"

    id = Column(String, primary_key=True, default=_uuid)
    entity_type = Column(String, nullable=False)  # "style" | "operation" | "allowance_policy" | "user"
    entity_id = Column(String, nullable=False, index=True)
    # Denormalized for fast per-style audit queries. ondelete=SET NULL rather
    # than the default RESTRICT: this is an append-only audit trail, so
    # deleting a style must not either block the delete or silently erase its
    # history -- the row survives with style_id nulled out. (SQLite doesn't
    # enforce FKs by default, which is why deleting a style with change-log
    # rows worked in the SQLite-only test suite but raised a
    # ForeignKeyViolation the first time this was run against real Postgres.)
    style_id = Column(String, ForeignKey("styles.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    action = Column(String, nullable=False)  # "create" | "update" | "delete"
    field = Column(String, nullable=False)  # field name, or "*" for whole-entity create/delete
    prior_value = Column(Text, nullable=True)  # JSON-stringified
    new_value = Column(Text, nullable=True)  # JSON-stringified

    user = relationship("User")
