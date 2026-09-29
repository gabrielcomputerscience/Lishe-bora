"""Payment integrations (SRS §10.2, FR-FIN-06/07, FR-PLT-06): verified supplier payment details, bulk payment files for
bank / M-Pesa, statement import with automatic reconciliation, a signed M-Pesa callback, the IFMIS export, payment
ageing and the integration transaction log. Every file in or out is logged."""
import csv
import hashlib
import hmac
import io
import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, current_principal, require, require_any, scope_for
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (BudgetLine, Contract, FundingSource, IntegrationTransaction, Invoice, InvoiceStatus, Payment, Supplier)
from app.api.v1.finance import PAYABLE, _load, apply_payment, can_pay
from app.services import audit, notifications as note
from app.services.refs import next_ref

router = APIRouter(tags=["payment integrations"])
Q = Decimal("0.01")
INV_RE = re.compile(r"INV-\d{4}-\d{5}", re.I)


def _mask(v: str) -> str:
    v = (v or "").strip()
    return ("•" * max(0, len(v) - 4) + v[-4:]) if len(v) > 4 else v


def _details_out(d: dict | None, full: bool) -> dict | None:
    if not d:
        return None
    out = dict(d)
    if not full:
        for k in ("account_no", "mpesa_phone"):
            if out.get(k):
                out[k] = _mask(out[k])
    return out


def _my_supplier(db, p: Principal) -> Supplier:
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    s = db.scalar(select(Supplier).where(Supplier.organization_id.in_(orgs))) if orgs else None
    if s is None:
        raise AppError(403, "NOT_A_SUPPLIER", "Only supplier accounts can do this.")
    return s


def _log(db, *, direction, system, kind, county_id=None, count=0, total=0, file_key="", summary=None, note_="", status="completed", actor=None):
    t = IntegrationTransaction(reference=next_ref(db, IntegrationTransaction, "INT"), direction=direction, system=system, kind=kind, status=status,
                               county_id=county_id, record_count=count, total_amount=Decimal(total).quantize(Q), file_key=file_key,
                               summary=summary or {}, note=note_, created_by=actor.id if actor else None)
    db.add(t)
    db.flush()
    return t


# ---------------- supplier payment details ----------------
class DetailsIn(BaseModel):
    method: str = Field(pattern="^(mpesa|bank)$")
    account_name: str = Field(min_length=3, max_length=160)
    mpesa_phone: str = ""
    bank_name: str = ""
    branch: str = ""
    account_no: str = ""


@router.get("/suppliers/me/payment-details")
def my_details(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = _my_supplier(db, p)
    return {"active": _details_out(s.payment_details, False), "pending": _details_out(s.payment_details_pending, False)}


@router.put("/suppliers/me/payment-details")
def change_details(body: DetailsIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Changes never take effect directly: finance must verify them first (protects against payment-diversion fraud)."""
    s = _my_supplier(db, p)
    if body.method == "mpesa" and not re.fullmatch(r"(\+?254|0)7\d{8}|(\+?254|0)1\d{8}", body.mpesa_phone.replace(" ", "")):
        raise AppError(422, "VALIDATION_ERROR", "Enter a valid Safaricom number.", [{"field": "mpesa_phone", "message": "Invalid phone"}])
    if body.method == "bank" and (not body.bank_name.strip() or len(body.account_no.strip()) < 6):
        raise AppError(422, "VALIDATION_ERROR", "Enter the bank and account number.", [{"field": "account_no", "message": "Required"}])
    s.payment_details_pending = {**body.model_dump(), "mpesa_phone": body.mpesa_phone.replace(" ", ""), "submitted_at": utcnow().isoformat(),
                                 "submitted_by": p.user.full_name}
    audit.record(db, action="PAYMENT_DETAILS_CHANGE", entity="supplier", entity_id=s.id, user=p.user,
                 after={"method": body.method, "account": _mask(body.account_no or body.mpesa_phone)}, request=request)
    finance = note.users_with_role(db, "finance_officer", s.county_id) + note.users_with_role(db, "county_finance_officer", s.county_id)
    note.to_users(db, finance, f"Payment details to verify: {s.legal_name}", "Call the supplier on their registered number before approving.",
                  "/app/integrations?tab=details", "payment_details")
    db.commit()
    return my_details(p, db)


@router.get("/finance/payment-details/pending")
def pending_details(p: Principal = Depends(require("fin:verify")), db: Session = Depends(get_db)):
    allowed = scope_for(db, p, "fin:verify")
    q = select(Supplier).where(Supplier.payment_details_pending.is_not(None))
    rows = [s for s in db.scalars(q).all() if s.payment_details_pending and (allowed is None or s.county_id in allowed)]
    return [{"supplier_id": s.id, "supplier": s.legal_name, "registered_phone": s.phone, "current": _details_out(s.payment_details, False),
             "requested": _details_out(s.payment_details_pending, True)} for s in rows]


class VerifyIn(BaseModel):
    approve: bool
    note: str = Field(min_length=5)     # e.g. "Confirmed by phone call to registered number"


@router.post("/finance/payment-details/{sid}/verify")
def verify_details(sid: uuid.UUID, body: VerifyIn, request: Request, p: Principal = Depends(require("fin:verify")), db: Session = Depends(get_db)):
    s = db.get(Supplier, sid)
    if s is None or not s.payment_details_pending:
        raise AppError(404, "NOT_FOUND", "No change is waiting for verification.")
    allowed = scope_for(db, p, "fin:verify")
    if allowed is not None and s.county_id not in allowed:
        raise AppError(403, "OUT_OF_SCOPE", "This supplier is outside your assigned area.")
    if any(ur.org_id == s.organization_id for ur in p.user.roles):
        raise AppError(403, "FORBIDDEN", "You cannot verify your own organisation's details.")
    req = dict(s.payment_details_pending)
    if body.approve:
        s.payment_details = {**req, "verified_by": p.user.full_name, "verified_at": utcnow().isoformat(), "verification_note": body.note}
    s.payment_details_pending = None
    audit.record(db, action="PAYMENT_DETAILS_" + ("APPROVE" if body.approve else "REJECT"), entity="supplier", entity_id=s.id, user=p.user,
                 after={"method": req.get("method"), "account": _mask(req.get("account_no") or req.get("mpesa_phone", ""))}, reason=body.note, request=request)
    # alert on the registered contact so an unauthorised change is noticed
    note.to_users(db, note.users_of_org(db, s.organization_id), "Payment details " + ("updated" if body.approve else "change rejected"),
                  "If you did not request this, call the county finance office immediately.", "/app/my-supplier", "payment_details", sms=True)
    db.commit()
    return {"ok": True, "active": _details_out(s.payment_details, True)}


# ---------------- bulk payment files ----------------
class PaymentFileIn(BaseModel):
    invoice_ids: list[uuid.UUID] = Field(min_length=1)
    system: str = Field(pattern="^(mpesa|bank)$")


@router.post("/finance/payment-files", status_code=201)
def payment_file(body: PaymentFileIn, request: Request, p: Principal = Depends(require("fin:pay")), db: Session = Depends(get_db)):
    """Bulk file for the bank or M-Pesa B2C portal. Payments are recorded when the statement or callback confirms them."""
    rows, problems, total, county = [], [], Decimal(0), None
    for iid in body.invoice_ids:
        inv = _load(db, iid)
        ok, why = can_pay(db, p, inv)
        d = inv.supplier.payment_details or {}
        if not ok:
            problems.append(f"{inv.reference}: {why}")
        elif d.get("method") != body.system:
            problems.append(f"{inv.reference}: {inv.supplier.legal_name} has no verified {body.system.upper()} details")
        else:
            bal = (Decimal(inv.total) - Decimal(inv.paid_amount or 0)).quantize(Q)
            total += bal
            county = county or inv.county_id
            rows.append([d.get("account_name"), d.get("mpesa_phone") if body.system == "mpesa" else d.get("account_no"), d.get("bank_name", ""),
                         d.get("branch", ""), f"{bal:.2f}", inv.reference, f"LisheBora {inv.reference}"])
    if problems:
        raise AppError(409, "PAYMENT_FILE_BLOCKED", "Some invoices cannot be paid.", [{"issue": x} for x in problems])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["beneficiary_name", "phone" if body.system == "mpesa" else "account_no", "bank", "branch", "amount", "reference", "narrative"])
    w.writerows(rows)
    key = f"integrations/{utcnow():%Y%m}/{uuid.uuid4().hex}-{body.system}-payments.csv"
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")
    t = _log(db, direction="out", system=body.system, kind="payment_file", county_id=county, count=len(rows), total=total, file_key=key,
             summary={"invoices": [r[5] for r in rows], "sha256": hashlib.sha256(buf.getvalue().encode()).hexdigest()}, actor=p)
    audit.record(db, action="PAYMENT_FILE", entity="integration", entity_id=t.id, user=p.user, after={"ref": t.reference, "rows": len(rows), "total": total},
                 request=request)
    db.commit()
    return {"reference": t.reference, "id": t.id, "rows": len(rows), "total": total, "download": f"/api/v1/integrations/{t.id}/file"}


@router.get("/integrations/{tid}/file")
def integration_file(tid: uuid.UUID, p: Principal = Depends(require("fin:pay")), db: Session = Depends(get_db)):
    t = db.get(IntegrationTransaction, tid)
    if t is None or not t.file_key:
        raise AppError(404, "NOT_FOUND", "File not found.")
    allowed = scope_for(db, p, "fin:pay")
    if allowed is not None and t.county_id and t.county_id not in allowed:
        raise AppError(403, "OUT_OF_SCOPE", "This file is outside your assigned area.")
    return FileResponse(Path(settings.storage_dir) / t.file_key, filename=t.file_key.rsplit("/", 1)[-1], media_type="text/csv")


# ---------------- statement import & reconciliation ----------------
def _parse_amount(v: str) -> Decimal | None:
    try:
        return Decimal(str(v).replace(",", "").replace("KES", "").replace("KSh", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _parse_date(v: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


@router.post("/finance/statements", status_code=201)
async def import_statement(request: Request, system: str = Form(..., pattern="^(mpesa|bank)$"), file: UploadFile = File(...),
                           p: Principal = Depends(require("fin:pay")), db: Session = Depends(get_db)):
    """CSV with columns date, amount, transaction_ref and reference/narrative. Rows quoting an INV- reference are matched to
    approved invoices and recorded as payments; everything else is listed for manual follow-up."""
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise AppError(413, "FILE_TOO_LARGE", "Statements must be under 2 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
    need = {"date", "amount", "transaction_ref"}
    if not need <= set(cols) or not ({"reference", "narrative", "details"} & set(cols)):
        raise AppError(422, "VALIDATION_ERROR", "The file needs columns: date, amount, transaction_ref and reference (or narrative).")
    matched, unmatched, duplicates, errors, total = [], [], [], [], Decimal(0)
    for i, row in enumerate(reader, start=2):
        g = {k: (row.get(v) or "").strip() for k, v in cols.items()}
        amt, dt, txn = _parse_amount(g["amount"]), _parse_date(g["date"]), g["transaction_ref"]
        narrative = " ".join(g.get(k, "") for k in ("reference", "narrative", "details"))
        if not amt or amt <= 0 or not dt or not txn:
            errors.append({"line": i, "issue": "Missing or invalid date, amount or transaction reference"})
            continue
        if db.scalar(select(Payment.id).where(Payment.method == system, Payment.transaction_ref == txn)):
            duplicates.append({"line": i, "transaction_ref": txn})
            continue
        m = INV_RE.search(narrative)
        inv = db.scalar(select(Invoice).where(Invoice.reference == m.group(0).upper())) if m else None
        if inv is None:
            unmatched.append({"line": i, "transaction_ref": txn, "amount": str(amt), "narrative": narrative[:120], "issue": "No invoice reference found"})
            continue
        inv = _load(db, inv.id)
        ok, why = can_pay(db, p, inv)
        bal = Decimal(inv.total) - Decimal(inv.paid_amount or 0)
        if not ok or amt > bal:
            unmatched.append({"line": i, "transaction_ref": txn, "amount": str(amt), "invoice": inv.reference,
                              "issue": why if not ok else f"Amount is more than the balance ({bal:,.2f})"})
            continue
        try:
            pay = apply_payment(db, inv, amount=amt, method=system, transaction_ref=txn, paid_on=dt, actor=p, request=request, source=f"{system} statement")
        except AppError as e:
            unmatched.append({"line": i, "transaction_ref": txn, "amount": str(amt), "invoice": inv.reference, "issue": e.message})
            continue
        matched.append({"line": i, "transaction_ref": txn, "amount": str(amt), "invoice": inv.reference, "payment": pay.reference})
        total += amt
    key = f"integrations/{utcnow():%Y%m}/{uuid.uuid4().hex}-{system}-statement.csv"
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    status = "completed" if not (unmatched or errors) else "partial"
    t = _log(db, direction="in", system=system, kind="statement_import", count=len(matched), total=total, file_key=key, status=status,
             summary={"matched": matched, "unmatched": unmatched, "duplicates": duplicates, "errors": errors, "file_name": file.filename}, actor=p)
    audit.record(db, action="STATEMENT_IMPORT", entity="integration", entity_id=t.id, user=p.user,
                 after={"ref": t.reference, "matched": len(matched), "unmatched": len(unmatched)}, request=request)
    db.commit()
    return {"reference": t.reference, "status": status, "matched": matched, "unmatched": unmatched, "duplicates": duplicates, "errors": errors,
            "total_matched": total}


# ---------------- M-Pesa callback (signed) ----------------
@router.post("/integrations/mpesa/callback")
async def mpesa_callback(request: Request, db: Session = Depends(get_db)):
    """Payment confirmation from the M-Pesa gateway adapter. Body is HMAC-SHA256 signed with MPESA_CALLBACK_SECRET
    (header X-Signature, hex). Idempotent on TransID. Disabled until a secret is configured."""
    if not settings.mpesa_callback_secret:
        raise AppError(503, "DISABLED", "Payment callbacks are not configured.")
    raw = await request.body()
    sig = request.headers.get("x-signature", "")
    good = hmac.new(settings.mpesa_callback_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        _log(db, direction="in", system="mpesa", kind="callback", status="failed", note_="Bad signature")
        db.commit()
        raise AppError(401, "BAD_SIGNATURE", "Signature check failed.")
    try:
        data = json.loads(raw)
        txn, amt, ref = str(data["TransID"]), Decimal(str(data["TransAmount"])), str(data["BillRefNumber"]).upper()
        when = _parse_date(str(data.get("TransTime", ""))[:10]) or date.today()
    except (KeyError, ValueError, InvalidOperation, json.JSONDecodeError):
        raise AppError(422, "VALIDATION_ERROR", "Malformed callback.")
    if db.scalar(select(Payment.id).where(Payment.method == "mpesa", Payment.transaction_ref == txn)):
        return {"ResultCode": 0, "ResultDesc": "Already recorded"}
    inv = db.scalar(select(Invoice).where(Invoice.reference == ref))
    if inv is None or inv.status not in PAYABLE:
        _log(db, direction="in", system="mpesa", kind="callback", status="failed", count=0, total=amt, summary={"TransID": txn, "BillRefNumber": ref},
             note_="No approved invoice for this reference")
        db.commit()
        return {"ResultCode": 1, "ResultDesc": "No approved invoice for this reference; logged for follow-up"}
    inv = _load(db, inv.id)
    try:
        pay = apply_payment(db, inv, amount=amt, method="mpesa", transaction_ref=txn, paid_on=when, request=request, source="mpesa callback")
    except AppError as e:
        db.rollback()
        _log(db, direction="in", system="mpesa", kind="callback", status="failed", total=amt, summary={"TransID": txn, "BillRefNumber": ref}, note_=e.message)
        db.commit()
        return {"ResultCode": 1, "ResultDesc": e.message}
    _log(db, direction="in", system="mpesa", kind="callback", county_id=inv.county_id, count=1, total=amt,
         summary={"TransID": txn, "BillRefNumber": ref, "payment": pay.reference})
    db.commit()
    return {"ResultCode": 0, "ResultDesc": f"Recorded {pay.reference}"}


# ---------------- IFMIS export, ageing, log ----------------
@router.get("/finance/ifmis-export.csv")
def ifmis_export(request: Request, status: str = "paid", p: Principal = Depends(require_any("fin:export", "fin:approve")), db: Session = Depends(get_db)):
    """Structured file for the county financial system: one row per invoice with budget line, funding source and payments."""
    sts = [InvoiceStatus(s) for s in status.split(",")]
    code = "fin:export" if p.can("fin:export") else "fin:approve"
    allowed = scope_for(db, p, code)
    q = select(Invoice).options(selectinload(Invoice.supplier), selectinload(Invoice.po)).where(Invoice.status.in_(sts))
    if allowed is not None:
        q = q.where(Invoice.county_id.in_(allowed))
    invs = db.scalars(q.order_by(Invoice.submitted_at)).all()
    cons = {c.id: c for c in db.scalars(select(Contract)).all()}
    lines = {b.id: b for b in db.scalars(select(BudgetLine)).all()}
    funds = {f.id: f for f in db.scalars(select(FundingSource)).all()}
    pays = defaultdict(list)
    for x in db.scalars(select(Payment)).all():
        pays[x.invoice_id].append(x)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice_ref", "supplier_invoice_no", "supplier", "kra_pin", "po", "contract", "budget_line", "funding_source", "invoice_date",
                "amount", "paid_amount", "status", "approved_on", "payment_refs", "payment_methods", "paid_on"])
    total = Decimal(0)
    for i in invs:
        c = cons.get(i.contract_id)
        bl = lines.get(c.budget_line_id) if c and c.budget_line_id else None
        fs = funds.get(bl.funding_source_id) if bl else None
        ps = pays.get(i.id, [])
        total += Decimal(i.total)
        w.writerow([i.reference, i.supplier_invoice_no, i.supplier.legal_name, i.supplier.kra_pin, i.po.reference if i.po else "", c.reference if c else "",
                    bl.code if bl else "", fs.code if fs else "", i.invoice_date, f"{i.total:.2f}", f"{Decimal(i.paid_amount or 0):.2f}", i.status.value,
                    as_utc(i.approved_at).date() if i.approved_at else "", ";".join(x.transaction_ref for x in ps), ";".join(sorted({x.method for x in ps})),
                    max((x.paid_on for x in ps), default="")])
    _log(db, direction="out", system="ifmis", kind="ifmis_export", count=len(invs), total=total, summary={"status": status}, actor=p)
    audit.record(db, action="IFMIS_EXPORT", entity="dataset", entity_id="ifmis", user=p.user, after={"rows": len(invs)}, request=request)
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="lishebora_ifmis_{date.today():%Y%m%d}.csv"'})


@router.get("/finance/ageing")
def ageing(p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    """Approved but unpaid invoices by days since approval (payment ageing, FR-FIN reconciliation)."""
    allowed = scope_for(db, p, "fin:view")
    buckets = {"0-15": Decimal(0), "16-30": Decimal(0), "31-60": Decimal(0), "61+": Decimal(0)}
    counts = {k: 0 for k in buckets}
    rows = []
    now = utcnow()
    for i in db.scalars(select(Invoice).options(selectinload(Invoice.supplier)).where(Invoice.status.in_(PAYABLE))).all():
        if allowed is not None and i.county_id not in allowed and i.supplier.organization_id not in allowed:
            continue
        days = (now - as_utc(i.approved_at or i.submitted_at)).days
        k = "0-15" if days <= 15 else "16-30" if days <= 30 else "31-60" if days <= 60 else "61+"
        bal = Decimal(i.total) - Decimal(i.paid_amount or 0)
        buckets[k] += bal
        counts[k] += 1
        rows.append({"id": i.id, "reference": i.reference, "supplier": i.supplier.legal_name, "balance": bal, "days": days, "bucket": k,
                     "has_verified_details": bool(i.supplier.payment_details)})
    return {"buckets": [{"bucket": k, "amount": v, "count": counts[k]} for k, v in buckets.items()], "invoices": sorted(rows, key=lambda r: -r["days"]),
            "target_days": settings.payment_target_days}


@router.get("/integrations/log")
def integration_log(p: Principal = Depends(require("fin:view")), db: Session = Depends(get_db)):
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    if orgs and db.scalar(select(Supplier.id).where(Supplier.organization_id.in_(orgs))):
        raise AppError(403, "FORBIDDEN", "The integration log is for finance staff.")
    allowed = scope_for(db, p, "fin:view")
    rows = db.scalars(select(IntegrationTransaction).order_by(IntegrationTransaction.created_at.desc()).limit(200)).all()
    return [{"id": t.id, "reference": t.reference, "direction": t.direction, "system": t.system, "kind": t.kind, "status": t.status,
             "records": t.record_count, "total": t.total_amount, "has_file": bool(t.file_key), "summary": t.summary, "note": t.note,
             "created_at": t.created_at} for t in rows if allowed is None or t.county_id is None or t.county_id in allowed]
