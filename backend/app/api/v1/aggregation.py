"""Aggregation & quality (SRS §3.8): farmer intake → batch → inspection → clearance into stock, plus traceability.

Offline capture: intake and inspection accept a `client_ref` generated on the device. Re-sending the same
client_ref returns the record already stored instead of creating a duplicate (safe to retry after reconnecting)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, ensure_in_scope, require, require_any, scope_any, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (Batch, BatchStatus, Commodity, Dispatch, DispatchLine, InspectionResult, Intake, MovementType,
                        Organization, OrgType, ProofOfDelivery, QualityInspection, StockMovement, Supplier, User)
from app.services import audit, exceptions as exc, notifications as note, stock, storage
from app.services.refs import next_ref

router = APIRouter(tags=["aggregation & quality"])
Q = Decimal("0.01")
FIELD_TYPES = (OrgType.aggregation_centre, OrgType.warehouse, OrgType.school)


# ---------------- helpers ----------------
def supplier_for_location(db: Session, org_id) -> Supplier | None:
    o = db.get(Organization, org_id)
    for _ in range(8):
        if o is None:
            return None
        if o.type == OrgType.supplier:
            return db.scalar(select(Supplier).where(Supplier.organization_id == o.id))
        o = db.get(Organization, o.parent_id) if o.parent_id else None
    return None


def _comm_names(db):
    return {c.code: c for c in db.scalars(select(Commodity)).all()}


def intake_out(i: Intake) -> dict:
    return {"id": i.id, "reference": i.reference, "batch_id": i.batch_id, "producer_name": i.producer_name,
            "producer_phone": i.producer_phone, "producer_group": i.producer_group, "producer_gender": i.producer_gender,
            "producer_youth": i.producer_youth, "commodity_code": i.commodity_code, "variety": i.variety,
            "quantity": i.quantity, "unit": i.unit, "source_location": i.source_location, "received_at": i.received_at,
            "client_ref": i.client_ref}


def inspection_out(db, x: QualityInspection) -> dict:
    u = db.get(User, x.inspector_id)
    return {"id": x.id, "batch_id": x.batch_id, "inspector": u.full_name if u else "", "inspected_at": x.inspected_at,
            "parameters": x.parameters, "checks": x.checks, "grade": x.grade, "result": x.result.value,
            "accepted_qty": x.accepted_qty, "rejected_qty": x.rejected_qty, "reason": x.reason,
            "corrective_action": x.corrective_action, "photos": x.photos, "captured_offline": x.captured_offline}


def batch_out(db: Session, b: Batch, detail: bool = False) -> dict:
    comms = _comm_names(db)
    c = comms.get(b.commodity_code)
    sup = db.get(Supplier, b.supplier_id) if b.supplier_id else None
    out = {"id": b.id, "code": b.code, "location_id": b.location_id, "location": b.location.name if b.location else "",
           "supplier": sup.legal_name if sup else None, "commodity_code": b.commodity_code,
           "commodity": c.name if c else b.commodity_code, "variety": b.variety, "unit": b.unit,
           "intake_qty": b.intake_qty, "accepted_qty": b.accepted_qty, "rejected_qty": b.rejected_qty, "grade": b.grade,
           "expiry_date": b.expiry_date, "status": b.status.value, "recalled_at": b.recalled_at, "recall_reason": b.recall_reason, "intake_count": len(b.intakes), "created_at": b.created_at,
           "on_hand": stock.balance(db, b.location_id, b.id)}
    if detail:
        out["intakes"] = [intake_out(i) for i in b.intakes]
        out["inspections"] = [inspection_out(db, x) for x in db.scalars(
            select(QualityInspection).where(QualityInspection.batch_id == b.id).order_by(QualityInspection.inspected_at)).all()]
        out["quality_spec"] = c.quality_spec if c else {}
    return out


def _load_batch(db, bid) -> Batch:
    b = db.scalar(select(Batch).where(Batch.id == bid).options(selectinload(Batch.intakes), selectinload(Batch.location)))
    if b is None:
        raise AppError(404, "NOT_FOUND", "Batch not found.")
    return b


# ---------------- locations ----------------
@router.get("/fulfilment/locations")
def locations(type: str | None = None, p: Principal = Depends(require_any("agg:view", "inv:view", "log:view")),
              db: Session = Depends(get_db)):
    allowed = scope_any(db, p, "agg:view", "inv:view", "log:view")
    q = select(Organization).where(Organization.type.in_(FIELD_TYPES), Organization.is_active)
    if type:
        q = q.where(Organization.type == OrgType(type))
    if allowed is not None:
        q = q.where(Organization.id.in_(allowed))
    return [{"id": o.id, "name": o.name, "code": o.code, "type": o.type.value, "parent_id": o.parent_id}
            for o in db.scalars(q.order_by(Organization.type, Organization.name)).all()]


# ---------------- intake & batches ----------------
class IntakeIn(BaseModel):
    location_id: uuid.UUID
    producer_name: str = Field(min_length=2, max_length=160)
    producer_phone: str = ""
    producer_group: str = ""
    producer_gender: str = ""          # female | male | other | "" (optional, for inclusion reporting)
    producer_youth: bool | None = None
    commodity_code: str
    variety: str = ""
    quantity: Decimal = Field(gt=0)
    source_location: str = ""
    received_at: datetime | None = None
    batch_id: uuid.UUID | None = None
    client_ref: str | None = Field(default=None, max_length=64)


@router.post("/intakes", status_code=201)
def create_intake(body: IntakeIn, request: Request, p: Principal = Depends(require("agg:create")),
                  db: Session = Depends(get_db)):
    if body.client_ref:
        prev = db.scalar(select(Intake).where(Intake.client_ref == body.client_ref))
        if prev:
            return {**intake_out(prev), "duplicate": True, "batch": batch_out(db, _load_batch(db, prev.batch_id))}
    hub = db.get(Organization, body.location_id)
    if hub is None or hub.type != OrgType.aggregation_centre:
        raise AppError(422, "VALIDATION_ERROR", "Choose an aggregation hub.", [{"field": "location_id", "message": "Not a hub"}])
    ensure_in_scope(db, p, "agg:create", hub.id)
    c = db.scalar(select(Commodity).where(Commodity.code == body.commodity_code, Commodity.is_active))
    if c is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown commodity.", [{"field": "commodity_code", "message": "Unknown"}])
    if body.batch_id:
        b = _load_batch(db, body.batch_id)
        if b.location_id != hub.id or b.commodity_code != c.code:
            raise AppError(409, "BATCH_MISMATCH", "That batch is for a different hub or commodity.")
    else:
        b = db.scalar(select(Batch).options(selectinload(Batch.intakes), selectinload(Batch.location)).where(
            Batch.location_id == hub.id, Batch.commodity_code == c.code, Batch.variety == body.variety.strip(),
            Batch.status == BatchStatus.open))
    if b is None:
        sup = supplier_for_location(db, hub.id)
        b = Batch(code=next_ref(db, Batch, "BATCH", 6), location_id=hub.id, supplier_id=sup.id if sup else None,
                  commodity_code=c.code, variety=body.variety.strip(), unit=c.unit, intake_qty=Decimal(0), created_by=p.id)
        db.add(b)
        db.flush()
        db.refresh(b)
    if b.status != BatchStatus.open:
        raise AppError(409, "BATCH_CLOSED", "This batch is closed for intake. Start a new batch.")
    i = Intake(reference=next_ref(db, Intake, "INT", 6), batch_id=b.id, location_id=hub.id,
               producer_name=body.producer_name.strip(), producer_phone=body.producer_phone.strip(),
               producer_group=body.producer_group.strip(), producer_gender=body.producer_gender,
               producer_youth=body.producer_youth, commodity_code=c.code, variety=body.variety.strip(),
               quantity=body.quantity.quantize(Q), unit=c.unit, source_location=body.source_location.strip(),
               received_at=body.received_at or utcnow(), client_ref=body.client_ref or None, created_by=p.id)
    db.add(i)
    b.intake_qty = Decimal(b.intake_qty or 0) + i.quantity
    db.flush()
    audit.record(db, action="INTAKE", entity="batch", entity_id=b.id, user=p.user,
                 after={"intake": i.reference, "producer": i.producer_name, "qty": i.quantity, "batch": b.code}, request=request)
    db.commit()
    return {**intake_out(i), "duplicate": False, "batch": batch_out(db, _load_batch(db, b.id))}


@router.get("/batches")
def list_batches(status: str | None = None, location_id: uuid.UUID | None = None,
                 p: Principal = Depends(require("agg:view")), db: Session = Depends(get_db)):
    q = select(Batch).options(selectinload(Batch.intakes), selectinload(Batch.location))
    allowed = scope_for(db, p, "agg:view")
    if allowed is not None:
        q = q.where(Batch.location_id.in_(allowed))
    if status:
        q = q.where(Batch.status.in_([BatchStatus(s) for s in status.split(",")]))
    if location_id:
        q = q.where(Batch.location_id == location_id)
    return [batch_out(db, b) for b in db.scalars(q.order_by(Batch.created_at.desc()).limit(300)).all()]


@router.get("/batches/{bid}")
def get_batch(bid: uuid.UUID, p: Principal = Depends(require("agg:view")), db: Session = Depends(get_db)):
    b = _load_batch(db, bid)
    ensure_in_scope(db, p, "agg:view", b.location_id)
    out = batch_out(db, b, detail=True)
    out["can_inspect"], out["why_not_inspect"] = _can_inspect(db, p, b)
    return out


@router.post("/batches/{bid}/request-inspection")
def request_inspection(bid: uuid.UUID, request: Request, p: Principal = Depends(require("agg:submit")),
                       db: Session = Depends(get_db)):
    b = _load_batch(db, bid)
    ensure_in_scope(db, p, "agg:submit", b.location_id)
    if b.status != BatchStatus.open:
        raise AppError(409, "INVALID_STATE", "Only an open batch can be sent for inspection.")
    if not b.intakes:
        raise AppError(409, "EMPTY_BATCH", "Record at least one intake first.")
    b.status = BatchStatus.awaiting_inspection
    county = stock.county_of(db, b.location_id)
    note.to_users(db, note.users_with_role(db, "quality_inspector", county) if county else [],
                  f"Batch {b.code} ready for inspection", f"{b.intake_qty} {b.unit} at {b.location.name}.",
                  f"/app/quality?batch={b.id}", "inspection")
    audit.record(db, action="REQUEST_INSPECTION", entity="batch", entity_id=b.id, user=p.user, after={"code": b.code},
                 request=request)
    db.commit()
    return batch_out(db, b, detail=True)


# ---------------- quality inspection ----------------
def _can_inspect(db, p: Principal, b: Batch) -> tuple[bool, str]:
    if not p.can("agg:verify"):
        return False, "Inspection needs the quality-inspector permission."
    allowed = scope_for(db, p, "agg:verify")
    if allowed is not None and b.location_id not in allowed:
        return False, "This hub is outside your assigned area."
    if b.status != BatchStatus.awaiting_inspection:
        return False, "The batch is not waiting for inspection."
    if b.created_by == p.id or any(i.created_by == p.id for i in b.intakes):
        return False, "You recorded intake for this batch, so you cannot inspect it (segregation of duties)."
    return True, ""


def run_checks(spec: dict, params: dict) -> list[dict]:
    """Compare measured parameters against the commodity quality specification, e.g. {"max_moisture_pct": 13.5}."""
    out = []
    for key, limit in (spec or {}).items():
        if key.startswith(("max_", "min_")):
            param = key[4:]
            val = params.get(param)
            if val in (None, ""):
                out.append({"param": param, "value": None, "limit": limit, "rule": key[:3], "pass": None})
                continue
            v = float(val)
            ok = v <= float(limit) if key.startswith("max_") else v >= float(limit)
            out.append({"param": param, "value": v, "limit": limit, "rule": key[:3], "pass": ok})
    return out


class InspectionIn(BaseModel):
    parameters: dict = {}
    visual_checks: dict = {}          # {"pests": false, "foreign_matter": false, "mould": false}
    grade: str = ""
    result: InspectionResult
    accepted_qty: Decimal = Field(ge=0)
    rejected_qty: Decimal = Field(ge=0)
    reason: str = ""
    corrective_action: str = ""
    photos: list[str] = []
    expiry_date: date | None = None
    inspected_at: datetime | None = None
    captured_offline: bool = False
    client_ref: str | None = Field(default=None, max_length=64)


@router.post("/batches/{bid}/inspections", status_code=201)
def inspect(bid: uuid.UUID, body: InspectionIn, request: Request, p: Principal = Depends(require("agg:verify")),
            db: Session = Depends(get_db)):
    if body.client_ref:
        prev = db.scalar(select(QualityInspection).where(QualityInspection.client_ref == body.client_ref))
        if prev:
            return {**inspection_out(db, prev), "duplicate": True}
    b = _load_batch(db, bid)
    ok, why = _can_inspect(db, p, b)
    if not ok:
        raise AppError(403 if "segregation" in why or "outside" in why else 409, "CANNOT_INSPECT", why)
    total = Decimal(b.intake_qty)
    if (body.accepted_qty + body.rejected_qty).quantize(Q) != total.quantize(Q):
        raise AppError(422, "VALIDATION_ERROR", f"Accepted plus rejected must equal the batch quantity ({total} {b.unit}).",
                       [{"field": "accepted_qty", "message": f"Must add up to {total}"}])
    c = db.scalar(select(Commodity).where(Commodity.code == b.commodity_code))
    checks = run_checks(c.quality_spec if c else {}, body.parameters)
    for k, v in body.visual_checks.items():
        checks.append({"param": k, "value": bool(v), "limit": False, "rule": "visual", "pass": not bool(v)})
    failed = [x for x in checks if x["pass"] is False]
    r = body.result
    expected = {InspectionResult.accepted: lambda: body.rejected_qty == 0 and body.accepted_qty > 0,
                InspectionResult.rejected: lambda: body.accepted_qty == 0,
                InspectionResult.partially_accepted: lambda: body.accepted_qty > 0 and body.rejected_qty > 0,
                InspectionResult.downgraded: lambda: body.accepted_qty > 0}[r]()
    if not expected:
        raise AppError(422, "VALIDATION_ERROR", "The quantities don't match the result you chose.",
                       [{"field": "result", "message": "Check accepted / rejected quantities"}])
    if failed and r == InspectionResult.accepted:
        raise AppError(422, "QUALITY_FAILED", "Some checks failed. Record the batch as downgraded, partially accepted or rejected.",
                       [{"field": "result", "message": ", ".join(x["param"] for x in failed) + " failed"}])
    if r != InspectionResult.accepted and not body.reason.strip():
        raise AppError(422, "VALIDATION_ERROR", "Give the reason for the decision.", [{"field": "reason", "message": "Required"}])
    if r == InspectionResult.downgraded and not body.grade.strip():
        raise AppError(422, "VALIDATION_ERROR", "Give the new grade.", [{"field": "grade", "message": "Required"}])
    x = QualityInspection(batch_id=b.id, inspector_id=p.id, inspected_at=body.inspected_at or utcnow(),
                          parameters={**body.parameters, **{f"visual_{k}": v for k, v in body.visual_checks.items()}},
                          checks=checks, grade=body.grade.strip() or "Grade 1", result=r,
                          accepted_qty=body.accepted_qty.quantize(Q), rejected_qty=body.rejected_qty.quantize(Q),
                          reason=body.reason.strip(), corrective_action=body.corrective_action.strip(), photos=body.photos[:10],
                          captured_offline=body.captured_offline, client_ref=body.client_ref or None, created_by=p.id)
    db.add(x)
    b.accepted_qty, b.rejected_qty, b.grade = x.accepted_qty, x.rejected_qty, x.grade
    if body.expiry_date:
        b.expiry_date = body.expiry_date
    b.status = BatchStatus.rejected if r == InspectionResult.rejected else BatchStatus.cleared
    if x.accepted_qty > 0:
        stock.post(db, location_id=b.location_id, batch_id=b.id, commodity_code=b.commodity_code, unit=b.unit,
                   quantity=x.accepted_qty, type_=MovementType.receipt, source_entity="inspection", source_ref=b.code,
                   reason=f"Cleared by inspection ({r.value})", user_id=p.id)
    county = stock.county_of(db, b.location_id)
    if x.rejected_qty > 0:
        exc.raise_case(db, category="quality_rejection", severity="high" if r == InspectionResult.rejected else "medium",
                       entity="batch", entity_id=b.id, entity_ref=b.code, org_id=county, supplier_id=b.supplier_id,
                       title=f"{x.rejected_qty} {b.unit} rejected at inspection",
                       detail=f"{b.code} at {b.location.name}: {x.reason}", user_id=p.id)
    if b.supplier_id:
        sup = db.get(Supplier, b.supplier_id)
        note.to_users(db, note.users_of_org(db, sup.organization_id), f"Inspection result for {b.code}: {r.value.replace('_', ' ')}",
                      f"Accepted {x.accepted_qty} {b.unit}, rejected {x.rejected_qty} {b.unit}. {x.reason}"[:280],
                      f"/app/aggregation?batch={b.id}", "inspection", sms=True)
    db.flush()
    audit.record(db, action="INSPECT", entity="batch", entity_id=b.id, user=p.user,
                 after={"result": r.value, "accepted": x.accepted_qty, "rejected": x.rejected_qty, "grade": x.grade,
                        "offline": body.captured_offline}, reason=x.reason, request=request)
    db.commit()
    return {**inspection_out(db, x), "duplicate": False}


# ---------------- QR labels & recall (Phase 6) ----------------
@router.get("/batches/{bid}/qr.svg")
def batch_qr(bid: uuid.UUID, p: Principal = Depends(require("agg:view")), db: Session = Depends(get_db)):
    """QR code for the batch label. It encodes the public verification link, so anyone can scan it with a phone camera."""
    import io
    import segno
    from fastapi.responses import Response
    from app.core.config import settings
    b = _load_batch(db, bid)
    ensure_in_scope(db, p, "agg:view", b.location_id)
    buf = io.BytesIO()
    segno.make(f"{settings.public_site_url.rstrip('/')}/t/{b.code}", error="m").save(buf, kind="svg", scale=6, border=2, dark="#1F3A12")
    return Response(buf.getvalue(), media_type="image/svg+xml")


class RecallIn(BaseModel):
    reason: str = Field(min_length=10)


@router.post("/batches/{bid}/recall")
def recall(bid: uuid.UUID, body: RecallIn, request: Request, p: Principal = Depends(require_any("agg:approve", "rsk:approve", "rsk:edit")),
           db: Session = Depends(get_db)):
    """Withdraw a batch everywhere it is: blocks dispatch, transfer and use; alerts every school that received it."""
    b = _load_batch(db, bid)
    code = next(c for c in ("agg:approve", "rsk:edit", "rsk:approve") if p.can(c))
    ensure_in_scope(db, p, code, b.location_id, stock.county_of(db, b.location_id))
    if b.status == BatchStatus.recalled:
        raise AppError(409, "ALREADY_RECALLED", "This batch is already recalled.")
    before = b.status.value
    b.status, b.recalled_at, b.recall_reason = BatchStatus.recalled, utcnow(), body.reason.strip()
    lines = db.scalars(select(DispatchLine).where(DispatchLine.batch_id == b.id)).all()
    schools = {ln.school_id for ln in lines}
    holders = {m.location_id for m in db.scalars(select(StockMovement).where(StockMovement.batch_id == b.id)).all()}
    msg = f"Stop using batch {b.code} ({b.commodity_code}). Keep it aside and wait for instructions. Reason: {body.reason.strip()}"
    for org_id in schools | holders:
        note.to_users(db, note.users_of_org(db, org_id), f"RECALL: batch {b.code}", msg[:280], f"/app/trace/{b.code}", "recall", sms=True)
    if b.supplier_id:
        sup = db.get(Supplier, b.supplier_id)
        note.to_users(db, note.users_of_org(db, sup.organization_id), f"RECALL: batch {b.code}", msg[:280], f"/app/trace/{b.code}", "recall", sms=True)
    exc.raise_case(db, category="batch_recall", severity="high", entity="batch", entity_id=b.id, entity_ref=b.code,
                   org_id=stock.county_of(db, b.location_id), supplier_id=b.supplier_id, title=f"Batch {b.code} recalled",
                   detail=f"{body.reason.strip()} · reached {len(schools)} school(s) and {len(holders)} stock location(s).", user_id=p.id)
    audit.record(db, action="RECALL", entity="batch", entity_id=b.id, user=p.user, before={"status": before},
                 after={"status": "recalled", "schools": len(schools)}, reason=body.reason, request=request)
    db.commit()
    return {**batch_out(db, _load_batch(db, b.id), detail=True), "schools_notified": len(schools), "locations_notified": len(holders)}


# ---------------- field uploads (inspection photos, POD photos) ----------------
@router.post("/fulfilment/uploads", status_code=201)
async def upload(file: UploadFile = File(...), p: Principal = Depends(require_any("agg:create", "agg:verify", "log:approve", "log:edit")),
                 db: Session = Depends(get_db)):
    meta = await storage.save_upload(file, f"field/{utcnow():%Y%m}")
    return {"file_key": meta["file_key"], "content_type": meta["content_type"], "size_bytes": meta["size_bytes"]}


@router.get("/fulfilment/files/{key:path}")
def field_file(key: str, p: Principal = Depends(require_any("agg:view", "log:view", "inv:view"))):
    if not key.startswith("field/"):
        raise AppError(404, "NOT_FOUND", "File not found.")
    return FileResponse(storage.open_path(key))


# ---------------- traceability ----------------
@router.get("/trace/{code}")
def trace(code: str, p: Principal = Depends(require_any("agg:view", "log:view", "inv:view", "meal:view")),
          db: Session = Depends(get_db)):
    """Farm → hub → inspection → stock → dispatch → school, for one batch (FR-AGG-05)."""
    b = db.scalar(select(Batch).options(selectinload(Batch.intakes), selectinload(Batch.location)).where(Batch.code == code.strip().upper()))
    if b is None:
        raise AppError(404, "NOT_FOUND", "No batch with that code.")
    allowed = scope_any(db, p, "agg:view", "log:view", "inv:view", "meal:view")
    lines = db.scalars(select(DispatchLine).options(selectinload(DispatchLine.dispatch), selectinload(DispatchLine.school))
                       .where(DispatchLine.batch_id == b.id)).all()
    if allowed is not None and b.location_id not in allowed and not any(ln.school_id in allowed for ln in lines):
        raise AppError(403, "OUT_OF_SCOPE", "This batch is outside your assigned area.")
    out = batch_out(db, b, detail=True)
    women = sum(1 for i in b.intakes if i.producer_gender == "female")
    youth = sum(1 for i in b.intakes if i.producer_youth)
    producers = {i.producer_name for i in b.intakes}
    out["producer_summary"] = {"producers": len(producers), "women": women, "youth": youth, "intakes": len(b.intakes)}
    movs = db.scalars(select(StockMovement).where(StockMovement.batch_id == b.id).order_by(StockMovement.at)).all()
    locs = {o.id: o.name for o in db.scalars(select(Organization).where(Organization.id.in_({m.location_id for m in movs} or {b.location_id}))).all()}
    out["movements"] = [{"at": m.at, "location": locs.get(m.location_id, ""), "type": m.type.value, "quantity": m.quantity,
                         "status": m.status.value, "source_ref": m.source_ref, "reason": m.reason} for m in movs]
    pods = {(pd.dispatch_id, pd.school_id): pd for pd in db.scalars(select(ProofOfDelivery).where(
        ProofOfDelivery.dispatch_id.in_({ln.dispatch_id for ln in lines} or {uuid.uuid4()}))).all()}
    out["deliveries"] = [{"dispatch": ln.dispatch.reference, "dispatch_id": ln.dispatch_id, "school": ln.school.name,
                          "quantity": ln.quantity, "accepted_qty": ln.accepted_qty, "rejected_qty": ln.rejected_qty,
                          "status": ln.dispatch.status.value,
                          "received_at": pods[(ln.dispatch_id, ln.school_id)].received_at if (ln.dispatch_id, ln.school_id) in pods else None,
                          "receiver": pods[(ln.dispatch_id, ln.school_id)].receiver_name if (ln.dispatch_id, ln.school_id) in pods else None}
                         for ln in lines]
    return out
