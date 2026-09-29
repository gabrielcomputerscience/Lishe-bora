"""Finance (SRS §3.11): supplier invoices with an automatic three-way match (PO ↔ goods accepted at schools ↔ invoice),
verification and approval, payment recording, and budget movement held → invoiced → paid.

Segregation of duties (SoD-07/08): whoever verifies, approves and pays an invoice must be three different people,
and none of them can be the person who captured it."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (CaseStatus, CommitmentStatus, Commodity, ExceptionCase, Invoice, InvoiceLine,
                        InvoiceStatus, Payment, POStatus, PurchaseOrder, Supplier, WorkflowInstance)
from app.services import audit, budget, exceptions as exc, notifications as note, storage, workflow as wf
from app.services.refs import next_ref

router = APIRouter(tags=["finance"])
Q = Decimal("0.01")
LIVE = (InvoiceStatus.submitted, InvoiceStatus.verified, InvoiceStatus.approved, InvoiceStatus.partially_paid, InvoiceStatus.paid)
PAYABLE = (InvoiceStatus.approved, InvoiceStatus.partially_paid)


# ---------------- helpers ----------------
def _my_supplier(db: Session, p: Principal) -> Supplier | None:
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    return db.scalar(select(Supplier).where(Supplier.organization_id.in_(orgs))) if orgs else None


def invoiced_by_line(db: Session, po_line_ids, exclude_invoice=None) -> dict:
    q = (select(InvoiceLine.po_line_id, func.coalesce(func.sum(InvoiceLine.quantity), 0))
         .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
         .where(InvoiceLine.po_line_id.in_(list(po_line_ids) or [uuid.uuid4()]), Invoice.status.in_(LIVE)))
    if exclude_invoice is not None:
        q = q.where(Invoice.id != exclude_invoice)
    return {k: Decimal(v) for k, v in db.execute(q.group_by(InvoiceLine.po_line_id)).all()}


def billable(db: Session, po: PurchaseOrder) -> list[dict]:
    comms = {c.code: c.name for c in db.scalars(select(Commodity)).all()}
    done = invoiced_by_line(db, [ln.id for ln in po.lines])
    out = []
    for ln in po.lines:
        acc, inv = Decimal(ln.accepted_qty or 0), done.get(ln.id, Decimal(0))
        out.append({"po_line_id": ln.id, "commodity_code": ln.commodity_code, "commodity": comms.get(ln.commodity_code, ln.commodity_code),
                    "unit": ln.unit, "ordered_qty": ln.quantity, "accepted_qty": acc, "rejected_qty": ln.rejected_qty or 0,
                    "invoiced_qty": inv, "billable_qty": max(acc - inv, Decimal(0)), "unit_price": ln.unit_price})
    return out


def three_way_match(db: Session, po: PurchaseOrder, lines: list[dict], exclude_invoice=None) -> dict:
    """lines: [{po_line_id, quantity, unit_price}] → evidence per line and an overall result."""
    pol = {ln.id: ln for ln in po.lines}
    done = invoiced_by_line(db, list(pol), exclude_invoice)
    tol = Decimal(str(settings.invoice_price_tolerance_pct)) / 100
    rows, ok = [], True
    for li in lines:
        ln = pol.get(li["po_line_id"])
        if ln is None:
            raise AppError(422, "VALIDATION_ERROR", "That line is not on this purchase order.")
        qty, price = Decimal(li["quantity"]), Decimal(li["unit_price"])
        acc, prev = Decimal(ln.accepted_qty or 0), done.get(ln.id, Decimal(0))
        issues = []
        if prev + qty > acc:
            issues.append(f"Invoiced {prev + qty} exceeds the {acc} {ln.unit} accepted by schools")
        if prev + qty > Decimal(ln.quantity):
            issues.append(f"Invoiced {prev + qty} exceeds the {ln.quantity} {ln.unit} ordered")
        if price > Decimal(ln.unit_price) * (1 + tol):
            issues.append(f"Unit price {price} is above the contract price {ln.unit_price}")
        ok = ok and not issues
        rows.append({"po_line_id": str(ln.id), "commodity_code": ln.commodity_code, "unit": ln.unit,
                     "ordered_qty": str(ln.quantity), "po_price": str(ln.unit_price), "accepted_qty": str(acc),
                     "previously_invoiced": str(prev), "invoiced_qty": str(qty), "invoiced_price": str(price),
                     "result": "match" if not issues else "variance", "issues": issues})
    return {"result": "matched" if ok else "variance", "tolerance_pct": float(tol * 100), "checked_at": utcnow().isoformat(), "lines": rows}


def _actors(inst: WorkflowInstance | None) -> set:
    return {a.actor_id for a in inst.actions if a.actor_id} if inst else set()


def _inst(db, inv: Invoice) -> WorkflowInstance | None:
    return db.scalar(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions))
                     .where(WorkflowInstance.entity == "invoice", WorkflowInstance.entity_id == inv.id)
                     .order_by(WorkflowInstance.started_at.desc()).limit(1))


def can_pay(db, p: Principal, inv: Invoice) -> tuple[bool, str]:
    if inv.status not in PAYABLE:
        return False, "Only approved invoices can be paid."
    if not p.can("fin:pay"):
        return False, "Recording payments needs the payment permission."
    allowed = scope_for(db, p, "fin:pay")
    if allowed is not None and inv.county_id not in allowed:
        return False, "This invoice is outside your assigned area."
    if p.id == inv.created_by or p.id in _actors(_inst(db, inv)):
        return False, "You verified, approved or captured this invoice, so someone else must pay it (segregation of duties)."
    return True, ""


def invoice_out(db: Session, inv: Invoice, p: Principal | None = None, detail: bool = False) -> dict:
    comms = {c.code: c.name for c in db.scalars(select(Commodity)).all()}
    days = None
    if inv.paid_at:
        days = (as_utc(inv.paid_at) - as_utc(inv.submitted_at)).days
    out = {"id": inv.id, "reference": inv.reference, "supplier_invoice_no": inv.supplier_invoice_no, "supplier_id": inv.supplier_id,
           "supplier": inv.supplier.legal_name if inv.supplier else "", "po_id": inv.po_id, "po": inv.po.reference if inv.po else "",
           "invoice_date": inv.invoice_date, "subtotal": inv.subtotal, "tax_amount": inv.tax_amount, "total": inv.total,
           "paid_amount": inv.paid_amount, "balance": (Decimal(inv.total) - Decimal(inv.paid_amount or 0)).quantize(Q),
           "status": inv.status.value, "match_result": (inv.match or {}).get("result"), "submitted_at": inv.submitted_at,
           "approved_at": inv.approved_at, "paid_at": inv.paid_at, "days_to_pay": days, "has_document": bool(inv.document_key)}
    if detail:
        out["lines"] = [{"id": ln.id, "po_line_id": ln.po_line_id, "commodity": comms.get(ln.commodity_code, ln.commodity_code), "unit": ln.unit,
                         "quantity": ln.quantity, "unit_price": ln.unit_price, "amount": ln.amount} for ln in inv.lines]
        out["match"] = inv.match
        out["notes"] = inv.notes
        out["payments"] = [{"id": x.id, "reference": x.reference, "amount": x.amount, "method": x.method, "transaction_ref": x.transaction_ref,
                            "paid_on": x.paid_on, "status": x.status.value, "note": x.note} for x in db.scalars(
                                select(Payment).where(Payment.invoice_id == inv.id).order_by(Payment.created_at)).all()]
        inst = _inst(db, inv)
        out["workflow"] = wf.serialize(inst, p, db) if inst else None
        if p is not None:
            out["can_pay"], out["why_not_pay"] = can_pay(db, p, inv)
    return out


def _load(db, iid) -> Invoice:
    inv = db.scalar(select(Invoice).where(Invoice.id == iid).options(
        selectinload(Invoice.lines), selectinload(Invoice.supplier), selectinload(Invoice.po)))
    if inv is None:
        raise AppError(404, "NOT_FOUND", "Invoice not found.")
    return inv


def _visible(db, p: Principal, inv: Invoice, code="fin:view"):
    allowed = scope_for(db, p, code)
    if allowed is None:
        return
    sup_org = inv.supplier.organization_id if inv.supplier else None
    if inv.county_id not in allowed and sup_org not in allowed:
        raise AppError(403, "OUT_OF_SCOPE", "This invoice is outside your assigned area.")


# ---------------- invoicing ----------------
@router.get("/invoices/billable")
def billable_orders(p: Principal = Depends(require("fin:create")), db: Session = Depends(get_db)):
    """Orders with goods accepted by schools that have not been invoiced yet."""
    q = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier)).where(
        PurchaseOrder.status.in_([POStatus.acknowledged, POStatus.partially_fulfilled, POStatus.fulfilled]))
    sup = _my_supplier(db, p)
    if sup:
        q = q.where(PurchaseOrder.supplier_id == sup.id)
    else:
        allowed = scope_for(db, p, "fin:create")
        if allowed is not None:
            q = q.where(PurchaseOrder.county_id.in_(allowed))
    out = []
    for po in db.scalars(q.order_by(PurchaseOrder.issued_at.desc())).all():
        lines = billable(db, po)
        out.append({"id": po.id, "reference": po.reference, "supplier": po.supplier.legal_name if po.supplier else "",
                    "status": po.status.value, "lines": lines,
                    "billable_value": sum((ln["billable_qty"] * ln["unit_price"] for ln in lines), Decimal(0)).quantize(Q)})
    return out


class InvLineIn(BaseModel):
    po_line_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, gt=0)


class InvoiceIn(BaseModel):
    po_id: uuid.UUID
    supplier_invoice_no: str = Field(min_length=1, max_length=60)
    invoice_date: date
    tax_amount: Decimal = Field(default=Decimal(0), ge=0)
    notes: str = ""
    lines: list[InvLineIn] = Field(min_length=1)


@router.post("/invoices", status_code=201)
def create_invoice(body: InvoiceIn, request: Request, p: Principal = Depends(require("fin:create")), db: Session = Depends(get_db)):
    po = db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier))
                   .where(PurchaseOrder.id == body.po_id))
    if po is None:
        raise AppError(404, "NOT_FOUND", "Purchase order not found.")
    sup = _my_supplier(db, p)
    if sup:
        if sup.id != po.supplier_id:
            raise AppError(403, "OUT_OF_SCOPE", "This order belongs to another supplier.")
        if not p.can("fin:submit"):
            raise AppError(403, "FORBIDDEN", "Your account can view invoices but not submit them.")
    else:
        ensure_in_scope(db, p, "fin:create", po.county_id)
    if body.invoice_date > date.today():
        raise AppError(422, "VALIDATION_ERROR", "The invoice date cannot be in the future.", [{"field": "invoice_date", "message": "Future date"}])
    dup = db.scalar(select(Invoice.reference).where(Invoice.supplier_id == po.supplier_id,
                                                    func.lower(Invoice.supplier_invoice_no) == body.supplier_invoice_no.strip().lower(),
                                                    Invoice.status.in_(LIVE)))
    if dup:
        raise AppError(409, "DUPLICATE_INVOICE", f"Invoice number {body.supplier_invoice_no} was already submitted ({dup}).",
                       [{"field": "supplier_invoice_no", "message": "Already used"}])
    pol = {ln.id: ln for ln in po.lines}
    seen = set()
    for li in body.lines:
        if li.po_line_id in seen:
            raise AppError(422, "VALIDATION_ERROR", "Each order line can appear once per invoice.")
        seen.add(li.po_line_id)
    lines = [{"po_line_id": li.po_line_id, "quantity": li.quantity,
              "unit_price": li.unit_price if li.unit_price is not None else (pol[li.po_line_id].unit_price if li.po_line_id in pol else 0)}
             for li in body.lines]
    match = three_way_match(db, po, lines)
    if match["result"] != "matched":
        raise AppError(409, "MATCH_FAILED", "The invoice does not match the order and the goods received by schools.",
                       [{"line": r["commodity_code"], "issues": r["issues"]} for r in match["lines"] if r["issues"]])
    inv = Invoice(reference=next_ref(db, Invoice, "INV"), supplier_invoice_no=body.supplier_invoice_no.strip(), supplier_id=po.supplier_id,
                  po_id=po.id, contract_id=po.contract_id, county_id=po.county_id, invoice_date=body.invoice_date,
                  subtotal=Decimal(0), tax_amount=body.tax_amount.quantize(Q), total=Decimal(0), paid_amount=Decimal(0),
                  match=match, notes=body.notes.strip(), submitted_at=utcnow(), created_by=p.id)
    for li in lines:
        ln = pol[li["po_line_id"]]
        amt = (Decimal(li["quantity"]) * Decimal(li["unit_price"])).quantize(Q)
        inv.lines.append(InvoiceLine(po_line_id=ln.id, commodity_code=ln.commodity_code, unit=ln.unit, quantity=Decimal(li["quantity"]).quantize(Q),
                                     unit_price=Decimal(li["unit_price"]).quantize(Q), amount=amt))
        inv.subtotal += amt
    inv.total = (inv.subtotal + inv.tax_amount).quantize(Q)
    db.add(inv)
    db.flush()
    wf.start(db, "invoice", entity="invoice", entity_id=inv.id, entity_ref=f"{inv.reference} · {po.supplier.legal_name}",
             title=f"Invoice {inv.supplier_invoice_no} · KSh {inv.total:,.0f}", scope_org_id=po.county_id, initiator=p,
             amount=float(inv.total))
    verifiers = note.users_with_role(db, "finance_officer", po.county_id) + note.users_with_role(db, "county_finance_officer", po.county_id)
    note.to_users(db, verifiers, f"Invoice {inv.reference} to verify", f"{po.supplier.legal_name} · KSh {inv.total:,.0f} · three-way match passed.",
                  f"/app/invoices/{inv.id}", "invoice")
    audit.record(db, action="INVOICE_SUBMIT", entity="invoice", entity_id=inv.id, user=p.user,
                 after={"po": po.reference, "total": inv.total, "supplier_no": inv.supplier_invoice_no}, request=request)
    db.commit()
    return invoice_out(db, _load(db, inv.id), p, detail=True)


@router.post("/invoices/{iid}/document")
async def upload_invoice(iid: uuid.UUID, request: Request, file: UploadFile = File(...), p: Principal = Depends(require("fin:create")),
                         db: Session = Depends(get_db)):
    inv = _load(db, iid)
    _visible(db, p, inv, "fin:create")
    if inv.status not in (InvoiceStatus.submitted, InvoiceStatus.verified):
        raise AppError(409, "INVALID_STATE", "The invoice copy can only be changed before approval.")
    meta = await storage.save_upload(file, f"invoices/{inv.id}")
    inv.document_key = meta["file_key"]
    audit.record(db, action="INVOICE_DOCUMENT", entity="invoice", entity_id=inv.id, user=p.user, after={"sha256": meta["sha256"]}, request=request)
    db.commit()
    return {"ok": True}


@router.get("/invoices/{iid}/document")
def invoice_document(iid: uuid.UUID, p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    inv = _load(db, iid)
    _visible(db, p, inv)
    if not inv.document_key:
        raise AppError(404, "NOT_FOUND", "No invoice copy uploaded.")
    return FileResponse(storage.open_path(inv.document_key), filename=f"{inv.reference}.pdf")


@router.get("/invoices")
def list_invoices(status: str | None = None, p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    q = select(Invoice).options(selectinload(Invoice.lines), selectinload(Invoice.supplier), selectinload(Invoice.po))
    if status:
        q = q.where(Invoice.status.in_([InvoiceStatus(s) for s in status.split(",")]))
    allowed = scope_for(db, p, "fin:view")
    if allowed is not None:
        sup_ids = list(db.scalars(select(Supplier.id).where(Supplier.organization_id.in_(allowed))))
        q = q.where((Invoice.county_id.in_(allowed)) | (Invoice.supplier_id.in_(sup_ids or [uuid.uuid4()])))
    rows = db.scalars(q.order_by(Invoice.submitted_at.desc()).limit(300)).all()
    return [invoice_out(db, i) for i in rows]


@router.get("/invoices/{iid}")
def get_invoice(iid: uuid.UUID, p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    inv = _load(db, iid)
    _visible(db, p, inv)
    return invoice_out(db, inv, p, detail=True)


# workflow hooks
def _on_advance(db, inst, p, note_):
    inv = _load(db, inst.entity_id)
    po = db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.id == inv.po_id))
    m = three_way_match(db, po, [{"po_line_id": ln.po_line_id, "quantity": ln.quantity, "unit_price": ln.unit_price} for ln in inv.lines],
                        exclude_invoice=inv.id)
    if m["result"] != "matched":
        raise AppError(409, "MATCH_FAILED", "The match no longer holds (goods or quantities changed). Return the invoice to the supplier.")
    inv.match = {**m, "verified_by": p.user.full_name}
    inv.status = InvoiceStatus.verified


def _on_complete(db, inst, p, note_):
    inv = _load(db, inst.entity_id)
    inv.status, inv.approved_at = InvoiceStatus.approved, utcnow()
    budget.convert(db, from_entity="contract", from_id=inv.contract_id, from_status=CommitmentStatus.held, to_status=CommitmentStatus.invoiced,
                   amount=inv.total, new_entity="invoice", new_id=inv.id, new_ref=inv.reference, actor_id=p.id)
    payers = note.users_with_role(db, "finance_officer", inv.county_id)
    note.to_users(db, payers, f"Invoice {inv.reference} approved for payment", f"KSh {inv.total:,.0f} to {inv.supplier.legal_name}.",
                  f"/app/invoices/{inv.id}", "invoice")
    note.to_users(db, note.users_of_org(db, inv.supplier.organization_id), f"Invoice {inv.supplier_invoice_no} approved",
                  f"KSh {inv.total:,.0f} is approved for payment.", "/app/invoices", "invoice", sms=True)


def _on_end(status):
    def hook(db, inst, p, note_):
        inv = _load(db, inst.entity_id)
        inv.status = status
        note.to_users(db, note.users_of_org(db, inv.supplier.organization_id),
                      f"Invoice {inv.supplier_invoice_no} {'returned for correction' if status == InvoiceStatus.returned else 'rejected'}",
                      note_[:200], f"/app/invoices/{inv.id}", "invoice", sms=True)
    return hook


wf.DEFINITIONS["invoice"].hooks.update(advance=_on_advance, complete=_on_complete, reject=_on_end(InvoiceStatus.rejected),
                                       **{"return": _on_end(InvoiceStatus.returned)})


# ---------------- payments ----------------
class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(pattern="^(bank|mpesa|cheque|ifmis)$")
    transaction_ref: str = Field(min_length=3, max_length=80)
    paid_on: date
    note: str = ""


def apply_payment(db: Session, inv: Invoice, *, amount: Decimal, method: str, transaction_ref: str, paid_on: date, note_: str = "",
                  actor: Principal | None = None, request: Request | None = None, source: str = "manual") -> Payment:
    """Shared by manual entry, bank/M-Pesa statement import and payment callbacks. Callers check permissions and SoD."""
    balance = Decimal(inv.total) - Decimal(inv.paid_amount or 0)
    amount = Decimal(amount)
    if amount <= 0 or amount > balance:
        raise AppError(422, "VALIDATION_ERROR", f"The balance due is KSh {balance:,.2f}.", [{"field": "amount", "message": f"Max {balance}"}])
    if paid_on > date.today():
        raise AppError(422, "VALIDATION_ERROR", "The payment date cannot be in the future.", [{"field": "paid_on", "message": "Future date"}])
    if db.scalar(select(Payment.id).where(Payment.method == method, Payment.transaction_ref == transaction_ref.strip())):
        raise AppError(409, "DUPLICATE_PAYMENT", "This transaction reference is already recorded.", [{"field": "transaction_ref", "message": "Already used"}])
    pay = Payment(reference=next_ref(db, Payment, "PAY"), invoice_id=inv.id, supplier_id=inv.supplier_id, amount=amount.quantize(Q),
                  method=method, transaction_ref=transaction_ref.strip(), paid_on=paid_on, note=(note_ or "").strip() or (f"via {source}" if source != "manual" else ""),
                  created_by=actor.id if actor else None)
    db.add(pay)
    inv.paid_amount = (Decimal(inv.paid_amount or 0) + pay.amount).quantize(Q)
    if inv.paid_amount >= Decimal(inv.total):
        inv.status, inv.paid_at = InvoiceStatus.paid, utcnow()
        for c in db.scalars(select(ExceptionCase).where(ExceptionCase.entity == "invoice", ExceptionCase.entity_id == inv.id,
                                                        ExceptionCase.category == "late_payment", ExceptionCase.status.in_([CaseStatus.open, CaseStatus.in_progress]))):
            c.status, c.resolution, c.resolved_by, c.resolved_at = CaseStatus.resolved, f"Paid ({pay.reference})", actor.id if actor else None, utcnow()
    else:
        inv.status = InvoiceStatus.partially_paid
    db.flush()
    budget.convert(db, from_entity="invoice", from_id=inv.id, from_status=CommitmentStatus.invoiced, to_status=CommitmentStatus.paid,
                   amount=pay.amount, new_entity="payment", new_id=pay.id, new_ref=pay.reference, actor_id=actor.id if actor else None)
    note.to_users(db, note.users_of_org(db, inv.supplier.organization_id), f"Payment sent: KSh {pay.amount:,.0f}",
                  f"For invoice {inv.supplier_invoice_no} ({inv.reference}) by {pay.method.upper()} ref {pay.transaction_ref}.",
                  "/app/invoices", "payment", sms=True)
    audit.record(db, action="PAYMENT", entity="invoice", entity_id=inv.id, user=actor.user if actor else None,
                 after={"payment": pay.reference, "amount": pay.amount, "method": pay.method, "txn": pay.transaction_ref, "source": source},
                 request=request)
    return pay


@router.post("/invoices/{iid}/payments", status_code=201)
def record_payment(iid: uuid.UUID, body: PaymentIn, request: Request, p: Principal = Depends(require("fin:pay")),
                   db: Session = Depends(get_db)):
    inv = _load(db, iid)
    ok, why = can_pay(db, p, inv)
    if not ok:
        raise AppError(403 if "segregation" in why or "outside" in why else 409, "CANNOT_PAY", why)
    apply_payment(db, inv, amount=body.amount, method=body.method, transaction_ref=body.transaction_ref, paid_on=body.paid_on,
                  note_=body.note, actor=p, request=request)
    db.commit()
    return invoice_out(db, _load(db, inv.id), p, detail=True)


@router.get("/payments")
def list_payments(p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    q = select(Payment, Invoice).join(Invoice, Invoice.id == Payment.invoice_id)
    allowed = scope_for(db, p, "fin:view")
    if allowed is not None:
        sup_ids = list(db.scalars(select(Supplier.id).where(Supplier.organization_id.in_(allowed))))
        q = q.where((Invoice.county_id.in_(allowed)) | (Invoice.supplier_id.in_(sup_ids or [uuid.uuid4()])))
    sups = {s.id: s.legal_name for s in db.scalars(select(Supplier)).all()}
    return [{"id": pay.id, "reference": pay.reference, "invoice_id": inv.id, "invoice": inv.reference, "supplier": sups.get(pay.supplier_id, ""),
             "amount": pay.amount, "method": pay.method, "transaction_ref": pay.transaction_ref, "paid_on": pay.paid_on,
             "status": pay.status.value} for pay, inv in db.execute(q.order_by(Payment.created_at.desc()).limit(300)).all()]


# ---------------- late payment sweep ----------------
def sweep_late_payments(db: Session):
    """Approved invoices still unpaid after the payment target open a late-payment exception (once)."""
    limit = utcnow() - timedelta(days=settings.payment_target_days)
    rows = db.scalars(select(Invoice).options(selectinload(Invoice.supplier)).where(Invoice.status.in_(PAYABLE))).all()
    raised = 0
    for inv in rows:
        if not inv.approved_at or as_utc(inv.approved_at) > limit:
            continue
        if db.scalar(select(ExceptionCase.id).where(ExceptionCase.entity == "invoice", ExceptionCase.entity_id == inv.id,
                                                    ExceptionCase.category == "late_payment")):
            continue
        exc.raise_case(db, category="late_payment", severity="high", entity="invoice", entity_id=inv.id, entity_ref=inv.reference,
                       org_id=inv.county_id, supplier_id=inv.supplier_id, title=f"Invoice unpaid after {settings.payment_target_days} days",
                       detail=f"{inv.supplier.legal_name} · KSh {Decimal(inv.total) - Decimal(inv.paid_amount or 0):,.0f} outstanding on {inv.reference}.")
        raised += 1
    if raised:
        db.commit()
    return raised
