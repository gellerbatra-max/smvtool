from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth, models, schemas, audit
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])

USER_SNAPSHOT_FIELDS = ["full_name", "role", "is_active"]


def _get_user_or_404(db: Session, user_id: str) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.require_admin)):
    if payload.role not in [r.value for r in models.UserRole]:
        raise HTTPException(status_code=400, detail=f"invalid role {payload.role!r}")
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="username already exists")
    user = models.User(
        username=payload.username,
        full_name=payload.full_name,
        role=models.UserRole(payload.role),
        password_hash=auth.hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    audit.log_create(db, entity_type="user", entity_id=user.id, style_id=None,
                      user=current_user, snapshot={"username": user.username, "role": user.role.value})
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db),
               current_user: models.User = Depends(auth.require_admin)):
    return db.query(models.User).order_by(models.User.username).all()


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: str, payload: schemas.UserUpdate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.require_admin)):
    user = _get_user_or_404(db, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in [r.value for r in models.UserRole]:
        raise HTTPException(status_code=400, detail=f"invalid role {updates['role']!r}")
    if updates.get("is_active") is False and user.id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot deactivate your own account")

    before = audit.snapshot(user, USER_SNAPSHOT_FIELDS)
    for field, value in updates.items():
        setattr(user, field, models.UserRole(value) if field == "role" else value)
    db.flush()
    after = audit.snapshot(user, USER_SNAPSHOT_FIELDS)
    audit.diff_and_log(db, entity_type="user", entity_id=user.id, style_id=None,
                        user=current_user, before=before, after=after)
    db.commit()
    db.refresh(user)
    return user
