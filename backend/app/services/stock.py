"""Stock ledger helpers (FR-INV-01…06). Balances are always derived from *posted* movements, never stored."""
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import Batch, MovementStatus, MovementType, Organization, OrgType, StockMovement

Q = Decimal("0.01")


def post(db: Session, *, location_id, commodity_code: str, quantity: Decimal, type_: MovementType, batch_id=None,
         unit="kg", source_entity="", source_ref="", reason="", user_id=None,
         status: MovementStatus = MovementStatus.posted, meta: dict | None = None) -> StockMovement:
    m = StockMovement(meta=meta, location_id=location_id, batch_id=batch_id, commodity_code=commodity_code, unit=unit,
                      quantity=Decimal(quantity).quantize(Q), type=type_, status=status, source_entity=source_entity,
                      source_ref=source_ref, reason=reason, at=utcnow(), created_by=user_id)
    db.add(m)
    db.flush()
    return m


def balance(db: Session, location_id, batch_id=None, commodity_code: str | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
        StockMovement.location_id == location_id, StockMovement.status == MovementStatus.posted)
    if batch_id is not None:
        q = q.where(StockMovement.batch_id == batch_id)
    if commodity_code is not None:
        q = q.where(StockMovement.commodity_code == commodity_code)
    return Decimal(db.scalar(q) or 0).quantize(Q)


def ensure_available(db: Session, location_id, batch_id, qty: Decimal, label: str = "this batch"):
    have = balance(db, location_id, batch_id)
    if Decimal(qty) > have:
        raise AppError(409, "INSUFFICIENT_STOCK", f"Only {have} available in {label} at this location.",
                       [{"available": str(have)}])


def balances(db: Session, location_ids: set[uuid.UUID] | None) -> list[dict]:
    """Per location + batch + commodity balances (posted only), with pending adjustments shown alongside."""
    q = (select(StockMovement.location_id, StockMovement.batch_id, StockMovement.commodity_code, StockMovement.unit,
                StockMovement.status, func.sum(StockMovement.quantity))
         .where(StockMovement.status.in_([MovementStatus.posted, MovementStatus.pending_approval]))
         .group_by(StockMovement.location_id, StockMovement.batch_id, StockMovement.commodity_code, StockMovement.unit,
                   StockMovement.status))
    if location_ids is not None:
        q = q.where(StockMovement.location_id.in_(location_ids))
    agg: dict[tuple, dict] = defaultdict(lambda: {"on_hand": Decimal(0), "pending": Decimal(0)})
    for loc, batch, comm, unit, st, total in db.execute(q):
        a = agg[(loc, batch, comm, unit)]
        a["on_hand" if st == MovementStatus.posted else "pending"] += Decimal(total or 0)
    if not agg:
        return []
    locs = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_({k[0] for k in agg}))).all()}
    batches = {b.id: b for b in db.scalars(select(Batch).where(Batch.id.in_({k[1] for k in agg if k[1]}))).all()}
    today = utcnow().date()
    out = []
    for (loc, batch, comm, unit), a in agg.items():
        if a["on_hand"] == 0 and a["pending"] == 0:
            continue
        b = batches.get(batch)
        alerts = []
        if b and b.status.value == "recalled":
            alerts.append("RECALLED: do not use")
        if b and b.expiry_date:
            days = (b.expiry_date - today).days
            if days < 0:
                alerts.append("Expired")
            elif days <= 30:
                alerts.append(f"Expires in {days} days")
        o = locs.get(loc)
        out.append({"location_id": loc, "location": o.name if o else "", "location_type": o.type.value if o else "",
                    "batch_id": batch, "batch_code": b.code if b else None, "grade": b.grade if b else "",
                    "expiry_date": b.expiry_date if b else None, "commodity_code": comm, "unit": unit,
                    "on_hand": a["on_hand"].quantize(Q), "pending_adjustment": a["pending"].quantize(Q), "alerts": alerts})
    return sorted(out, key=lambda r: (r["location"], r["commodity_code"], r["batch_code"] or ""))


def county_of(db: Session, org_id) -> uuid.UUID | None:
    """Walk up the hierarchy to the county (used to route exceptions and approvals)."""
    seen = 0
    o = db.get(Organization, org_id) if org_id else None
    while o is not None and seen < 12:
        if o.type == OrgType.county:
            return o.id
        o = db.get(Organization, o.parent_id) if o.parent_id else None
        seen += 1
    return None
