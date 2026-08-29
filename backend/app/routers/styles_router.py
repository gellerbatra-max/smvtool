from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app import auth, models, schemas, audit, engine_bridge, policy_service
from app.database import get_db

router = APIRouter(prefix="/styles", tags=["styles"])

STYLE_SNAPSHOT_FIELDS = ["name", "garment_type", "variant", "size", "bundle_size", "notes"]


def _get_style_or_404(db: Session, style_id: str) -> models.Style:
    style = db.query(models.Style).filter(models.Style.id == style_id).first()
    if style is None:
        raise HTTPException(status_code=404, detail="style not found")
    return style


# ---------------------------------------------------------------- CRUD ----

@router.post("", response_model=schemas.StyleDetailOut, status_code=status.HTTP_201_CREATED)
def create_style(payload: schemas.StyleCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_writer)):
    style = models.Style(
        name=payload.name, garment_type=payload.garment_type, variant=payload.variant,
        size=payload.size, bundle_size=payload.bundle_size, notes=payload.notes,
        created_by_id=user.id,
    )
    db.add(style)
    db.flush()

    if payload.seed_from_library:
        raw_ops = engine_bridge.library_style_operations_raw(
            size=payload.size, variant=payload.variant, bundle_size=payload.bundle_size,
        )
        for i, o in enumerate(raw_ops):
            op = models.Operation(style_id=style.id, name=o["name"], sequence=i,
                                   bundle_size=o["bundle_size"], steps=o["steps"])
            db.add(op)

    audit.log_create(db, entity_type="style", entity_id=style.id, style_id=style.id, user=user,
                      snapshot=audit.snapshot(style, STYLE_SNAPSHOT_FIELDS))
    db.commit()
    db.refresh(style)
    return style


@router.get("", response_model=list[schemas.StyleOut])
def list_styles(db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_any_authenticated)):
    return db.query(models.Style).order_by(models.Style.created_at.desc()).all()


@router.get("/{style_id}", response_model=schemas.StyleDetailOut)
def get_style(style_id: str, db: Session = Depends(get_db),
              user: models.User = Depends(auth.require_any_authenticated)):
    style = db.query(models.Style).options(joinedload(models.Style.operations)).filter(
        models.Style.id == style_id
    ).first()
    if style is None:
        raise HTTPException(status_code=404, detail="style not found")
    return style


@router.put("/{style_id}", response_model=schemas.StyleDetailOut)
def update_style(style_id: str, payload: schemas.StyleUpdate, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_writer)):
    style = _get_style_or_404(db, style_id)
    before = audit.snapshot(style, STYLE_SNAPSHOT_FIELDS)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(style, field, value)
    db.flush()
    after = audit.snapshot(style, STYLE_SNAPSHOT_FIELDS)
    audit.diff_and_log(db, entity_type="style", entity_id=style.id, style_id=style.id,
                        user=user, before=before, after=after)
    db.commit()
    db.refresh(style)
    return style


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_style(style_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_writer)):
    style = _get_style_or_404(db, style_id)
    snap = audit.snapshot(style, STYLE_SNAPSHOT_FIELDS)
    audit.log_delete(db, entity_type="style", entity_id=style.id, style_id=style.id,
                      user=user, snapshot=snap)
    db.delete(style)
    db.commit()
    return None


# ---------------------------------------------------------- operations ----

@router.post("/{style_id}/operations", response_model=schemas.OperationOut,
             status_code=status.HTTP_201_CREATED)
def add_operation(style_id: str, payload: schemas.OperationIn, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_writer)):
    style = _get_style_or_404(db, style_id)
    op = models.Operation(style_id=style.id, name=payload.name, sequence=payload.sequence,
                           bundle_size=payload.bundle_size, steps=payload.steps)
    db.add(op)
    db.flush()
    audit.log_create(db, entity_type="operation", entity_id=op.id, style_id=style.id, user=user,
                      snapshot={"name": op.name, "sequence": op.sequence,
                                "bundle_size": op.bundle_size, "steps": op.steps})
    db.commit()
    db.refresh(op)
    return op


@router.put("/{style_id}/operations/{operation_id}", response_model=schemas.OperationOut)
def update_operation(style_id: str, operation_id: str, payload: schemas.OperationIn,
                      db: Session = Depends(get_db), user: models.User = Depends(auth.require_writer)):
    op = db.query(models.Operation).filter(models.Operation.id == operation_id,
                                            models.Operation.style_id == style_id).first()
    if op is None:
        raise HTTPException(status_code=404, detail="operation not found")
    fields = ["name", "sequence", "bundle_size", "steps"]
    before = audit.snapshot(op, fields)
    op.name = payload.name
    op.sequence = payload.sequence
    op.bundle_size = payload.bundle_size
    op.steps = payload.steps
    db.flush()
    after = audit.snapshot(op, fields)
    audit.diff_and_log(db, entity_type="operation", entity_id=op.id, style_id=style_id,
                        user=user, before=before, after=after)
    db.commit()
    db.refresh(op)
    return op


@router.delete("/{style_id}/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operation(style_id: str, operation_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(auth.require_writer)):
    op = db.query(models.Operation).filter(models.Operation.id == operation_id,
                                            models.Operation.style_id == style_id).first()
    if op is None:
        raise HTTPException(status_code=404, detail="operation not found")
    snap = {"name": op.name, "sequence": op.sequence, "bundle_size": op.bundle_size, "steps": op.steps}
    audit.log_delete(db, entity_type="operation", entity_id=op.id, style_id=style_id,
                      user=user, snapshot=snap)
    db.delete(op)
    db.commit()
    return None


# -------------------------------------------------------------- compute ---

@router.post("/{style_id}/compute", response_model=schemas.ComputeResponse)
def compute_style(style_id: str, payload: schemas.ComputeRequest, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_writer)):
    style = _get_style_or_404(db, style_id)
    ops = db.query(models.Operation).filter(models.Operation.style_id == style_id).order_by(
        models.Operation.sequence
    ).all()
    if not ops:
        raise HTTPException(status_code=400, detail="style has no operations to compute")

    policy_row = (policy_service.get_by_id(db, payload.allowance_policy_id)
                  if payload.allowance_policy_id else policy_service.get_active(db))
    if policy_row is None:
        raise HTTPException(status_code=400, detail="no allowance policy available")

    op_dicts = [{"name": o.name, "steps": o.steps, "bundle_size": o.bundle_size} for o in ops]
    result = engine_bridge.compute_style(op_dicts, policy_row.document, payload.allowance_profile)

    result_rows = []
    for op, op_result in zip(ops, result["operations"]):
        row = models.SMVResult(
            operation_id=op.id, style_id=style.id,
            st_op_s=op_result["ST_op_s"], st_op_min=op_result["ST_op_min"],
            bt_op_s=op_result["BT_op_s"], bt_op_min=op_result["BT_op_min"],
            audit_trail=op_result, allowance_profile=payload.allowance_profile,
            allowance_policy_version_id=policy_row.id,
            engine_version=engine_bridge.ENGINE_VERSION,
            calibration_version=None,
            computed_by_id=user.id,
        )
        db.add(row)
        result_rows.append(row)
    db.commit()
    for r in result_rows:
        db.refresh(r)

    return schemas.ComputeResponse(
        style_id=style.id, smv_min=result["SMV_min"], smv_tmu=result["SMV_tmu"],
        bt_style_min=result["BT_style_min"], allowance_profile=payload.allowance_profile,
        engine_version=engine_bridge.ENGINE_VERSION, warnings=result["all_warnings"],
        results=result_rows,
    )


@router.get("/{style_id}/bulletin", response_model=schemas.BulletinOut)
def get_bulletin(style_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_any_authenticated)):
    style = _get_style_or_404(db, style_id)
    ops = db.query(models.Operation).filter(models.Operation.style_id == style_id).order_by(
        models.Operation.sequence
    ).all()
    bulletin_ops = []
    smv_total_s = 0.0
    any_result = False
    for op in ops:
        latest = db.query(models.SMVResult).filter(models.SMVResult.operation_id == op.id).order_by(
            models.SMVResult.computed_at.desc()
        ).first()
        latest_dict = None
        if latest is not None:
            any_result = True
            smv_total_s += latest.st_op_s
            latest_dict = {
                "id": latest.id, "st_op_s": latest.st_op_s, "st_op_min": latest.st_op_min,
                "bt_op_s": latest.bt_op_s, "bt_op_min": latest.bt_op_min,
                "allowance_profile": latest.allowance_profile,
                "engine_version": latest.engine_version, "computed_at": latest.computed_at.isoformat(),
                "audit_trail": latest.audit_trail,
            }
        bulletin_ops.append(schemas.BulletinOperation(
            operation_id=op.id, name=op.name, sequence=op.sequence,
            bundle_size=op.bundle_size, latest_result=latest_dict,
        ))
    return schemas.BulletinOut(
        style=style, operations=bulletin_ops,
        smv_min=(smv_total_s / 60.0) if any_result else None,
        smv_tmu=(smv_total_s / 60.0 * 1666.6667) if any_result else None,
    )


@router.get("/{style_id}/change-log", response_model=list[schemas.ChangeLogOut])
def get_style_change_log(style_id: str, db: Session = Depends(get_db),
                          user: models.User = Depends(auth.require_any_authenticated)):
    _get_style_or_404(db, style_id)
    return db.query(models.ChangeLog).filter(models.ChangeLog.style_id == style_id).order_by(
        models.ChangeLog.timestamp.desc()
    ).all()
