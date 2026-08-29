"""
auth.py -- JWT login/session + password hashing + role-based dependencies.

Three roles (models.UserRole):
    ie_engineer    - create/edit styles, operations, run computes
    viewer         - read-only
    administrator  - everything ie_engineer can do, plus user management
                     and allowance-policy edits
"""
from __future__ import annotations

import datetime
import os
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

SECRET_KEY = os.environ.get("SMV_JWT_SECRET", "dev-only-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Password hashing goes straight to the `bcrypt` library rather than through
# passlib.CryptContext: passlib 1.7.x's bcrypt backend self-test is
# incompatible with bcrypt>=4.1's stricter 72-byte-secret handling (raises
# ValueError during passlib's own internal "wrap bug" detection probe on
# import), a known upstream passlib/bcrypt interaction issue. bcrypt's raw
# API has no such issue and is what passlib wraps anyway.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw_bytes = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: models.User) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user.id, "username": user.username, "role": user.role.value, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*roles: str):
    """FastAPI dependency factory: require_roles("ie_engineer", "administrator")."""
    def _dep(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role.value}' is not permitted to perform this action "
                       f"(requires one of {roles})",
            )
        return user
    return _dep


# Convenience dependencies used throughout the routers
require_writer = require_roles("ie_engineer", "administrator")   # create/edit styles & operations
require_admin = require_roles("administrator")                    # user mgmt, allowance policy edits
require_any_authenticated = get_current_user                      # any logged-in role, including viewer
