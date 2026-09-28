from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, models, schemas, audit, policy_service
from app.database import get_db

router = APIRouter(prefix="/allowance-policies", tags=["allowance-policies"])


@router.get("", response_model=list[schemas.AllowancePolicyOut])
def list_policies(db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_any_authenticated)):
    policy_service.ensure_seeded(db)
    db.commit()
    return db.query(models.AllowancePolicy).order_by(
        models.AllowancePolicy.policy_name, models.AllowancePolicy.version.desc()
    ).all()


@router.get("/active", response_model=schemas.AllowancePolicyOut)
def get_active_policy(db: Session = Depends(get_db),
                       user: models.User = Depends(auth.require_any_authenticated)):
    row = policy_service.get_active(db)
    db.commit()
    return row


@router.get("/{policy_id}", response_model=schemas.AllowancePolicyDetailOut)
def get_policy_document(policy_id: str, db: Session = Depends(get_db),
                         user: models.User = Depends(auth.require_any_authenticated)):
    """Unlike the list endpoint above, this returns the full `document` --
    needed to derive a new version from an existing one (e.g. tooling that
    edits a policy) without hand-retyping it from the vendored engine JSON."""
    row = policy_service.get_by_id(db, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="allowance policy not found")
    return row


@router.post("", response_model=schemas.AllowancePolicyOut, status_code=201)
def create_policy_version(payload: schemas.AllowancePolicyCreate, db: Session = Depends(get_db),
                           user: models.User = Depends(auth.require_admin)):
    """Factories may edit their allowance policy over time (e.g. a revised
    ILO-floor profile). This ALWAYS inserts a new version -- it never
    mutates an existing row -- so smv_results computed against an earlier
    version remain exactly reproducible against the policy document that
    produced them."""
    row = policy_service.create_new_version(db, payload.policy_name, payload.document, user=user)
    audit.log_create(db, entity_type="allowance_policy", entity_id=row.id, style_id=None,
                      user=user, snapshot={"policy_name": row.policy_name, "version": row.version})
    db.commit()
    db.refresh(row)
    return row
