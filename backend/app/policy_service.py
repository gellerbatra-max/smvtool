"""policy_service.py -- allowance_policies bookkeeping.

Keeps exactly one row per policy_name marked is_active=True at a time.
Editing a policy never mutates an existing row (so past smv_results stay
reproducible against the exact document that produced them) -- it inserts
a new row with version = max(version)+1 and flips is_active.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models, engine_bridge

DEFAULT_POLICY_NAME = "wt-allowance-policy"  # matches allowance_policy.json's spec.id


def ensure_seeded(db: Session, user=None) -> models.AllowancePolicy:
    """Idempotently seed version 1 of the default policy from the vendored
    engine's shipped allowance_policy.json, if no policy rows exist yet."""
    existing = db.query(models.AllowancePolicy).filter(
        models.AllowancePolicy.policy_name == DEFAULT_POLICY_NAME
    ).first()
    if existing:
        return get_active(db, DEFAULT_POLICY_NAME)
    doc = engine_bridge.get_default_allowance_policy_document()
    row = models.AllowancePolicy(
        policy_name=DEFAULT_POLICY_NAME, version=1, document=doc, is_active=True,
        created_by_id=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def get_active(db: Session, policy_name: str = DEFAULT_POLICY_NAME) -> models.AllowancePolicy:
    row = db.query(models.AllowancePolicy).filter(
        models.AllowancePolicy.policy_name == policy_name,
        models.AllowancePolicy.is_active == True,  # noqa: E712
    ).first()
    if row is None:
        row = ensure_seeded(db)
    return row


def get_by_id(db: Session, policy_id: str) -> models.AllowancePolicy | None:
    return db.query(models.AllowancePolicy).filter(models.AllowancePolicy.id == policy_id).first()


def create_new_version(db: Session, policy_name: str, document: dict, user=None) -> models.AllowancePolicy:
    current_max = db.query(models.AllowancePolicy).filter(
        models.AllowancePolicy.policy_name == policy_name
    ).order_by(models.AllowancePolicy.version.desc()).first()
    new_version = (current_max.version + 1) if current_max else 1
    # deactivate previous
    if current_max is not None:
        db.query(models.AllowancePolicy).filter(
            models.AllowancePolicy.policy_name == policy_name,
            models.AllowancePolicy.is_active == True,  # noqa: E712
        ).update({"is_active": False})
    row = models.AllowancePolicy(
        policy_name=policy_name, version=new_version, document=document, is_active=True,
        created_by_id=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row
