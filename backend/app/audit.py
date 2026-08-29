"""
audit.py -- change_log writer, factored into one small helper so route
handlers never hand-roll audit rows themselves.

Two entry points:
  * `diff_and_log(db, entity_type, entity_id, style_id, user, before, after,
                   ignore_fields=...)`
        Compares two plain-dict snapshots of an ORM object field-by-field and
        writes one change_log row PER CHANGED FIELD. Use for UPDATE.
  * `log_create(db, entity_type, entity_id, style_id, user, snapshot)` /
    `log_delete(db, entity_type, entity_id, style_id, user, snapshot)`
        Write a single whole-entity change_log row (field="*") for CREATE/DELETE.

Values are JSON-stringified so change_log.prior_value/new_value stay
plain TEXT regardless of dialect (no JSONB round-tripping needed for an
audit trail that's read, not queried structurally).
"""
from __future__ import annotations

import datetime
import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models


def _jsonable(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return json.dumps(str(value))


def _write(db: Session, *, entity_type: str, entity_id: str, style_id: Optional[str],
           user_id: Optional[str], action: str, field: str,
           prior_value: Optional[str], new_value: Optional[str]) -> models.ChangeLog:
    row = models.ChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        style_id=style_id,
        user_id=user_id,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        action=action,
        field=field,
        prior_value=prior_value,
        new_value=new_value,
    )
    db.add(row)
    return row


def log_create(db: Session, *, entity_type: str, entity_id: str,
               style_id: Optional[str], user, snapshot: dict) -> models.ChangeLog:
    user_id = getattr(user, "id", None)
    return _write(db, entity_type=entity_type, entity_id=entity_id, style_id=style_id,
                  user_id=user_id, action="create", field="*",
                  prior_value=None, new_value=_jsonable(snapshot))


def log_delete(db: Session, *, entity_type: str, entity_id: str,
               style_id: Optional[str], user, snapshot: dict) -> models.ChangeLog:
    user_id = getattr(user, "id", None)
    return _write(db, entity_type=entity_type, entity_id=entity_id, style_id=style_id,
                  user_id=user_id, action="delete", field="*",
                  prior_value=_jsonable(snapshot), new_value=None)


def diff_and_log(db: Session, *, entity_type: str, entity_id: str,
                  style_id: Optional[str], user, before: dict, after: dict,
                  ignore_fields: tuple = ("updated_at", "created_at")) -> list[models.ChangeLog]:
    """Writes one change_log row per field whose value differs between
    `before` and `after`. Returns the list of rows written (may be empty
    if nothing actually changed -- callers should treat a no-op update as
    NOT producing a change_log row, which is the correct audit semantics)."""
    user_id = getattr(user, "id", None)
    rows = []
    keys = set(before.keys()) | set(after.keys())
    for key in sorted(keys):
        if key in ignore_fields:
            continue
        old = before.get(key)
        new = after.get(key)
        if old == new:
            continue
        rows.append(_write(
            db, entity_type=entity_type, entity_id=entity_id, style_id=style_id,
            user_id=user_id, action="update", field=key,
            prior_value=_jsonable(old), new_value=_jsonable(new),
        ))
    return rows


def snapshot(obj, fields: list[str]) -> dict:
    """Plain-dict snapshot of an ORM object's fields, taken BEFORE a mutation,
    for later diff_and_log() comparison."""
    return {f: getattr(obj, f) for f in fields}
