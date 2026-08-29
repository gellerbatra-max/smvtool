from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth, models, schemas, audit
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])


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
