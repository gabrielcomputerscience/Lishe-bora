"""Phase 6 analytics & risk: stock-out outlook, requirement projection, price intelligence, automated risk flags,
and county/school performance (FR-MEAL-04, FR-RSK-01…02, FR-CMP-03)."""
import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, require_any, scope_any
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (Complaint, Dispatch, InstanceStatus, Invoice, InvoiceStatus, Organization, OrgType, ProofOfDelivery, Supplier,
                        SystemSetting, WorkflowInstance)
from app.services import analytics as an, audit
from app.services.stock import county_of

router = APIRouter(tags=["analytics & risk"])


def _no_suppliers(db, p: Principal):
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    if orgs and db.scalar(select(Supplier.id).where(Supplier.organization_id.in_(orgs))):
        raise AppError(403, "FORBIDDEN", "This view is for programme staff.")


def _counties(db, p: Principal, *codes) -> set | None:
    allowed = scope_any(db, p, *codes)
    if allowed is None:
        return None
    return {c for c in (county_of(db, o) for o in allowed) if c}


@router.get("/analytics/stock-outlook")
def stock_outlook(p: Principal = Depends(require_any("inv:view", "meal:view")), db: Session = Depends(get_db)):
    return an.stock_outlook(db, scope_any(db, p, "inv:view", "meal:view"))


@router.get("/analytics/requirements")
def requirements(p: Principal = Depends(require_any("dem:view", "meal:view")), db: Session = Depends(get_db)):
    _no_suppliers(db, p)
    return an.requirement_projection(db, _counties(db, p, "dem:view", "meal:view"))


@router.get("/analytics/prices")
def prices(p: Principal = Depends(require_any("src:view", "con:view", "meal:view")), db: Session = Depends(get_db)):
    _no_suppliers(db, p)
    return an.price_intelligence(db, _counties(db, p, "src:view", "con:view", "meal:view"))


@router.get("/risk/dashboard")
def risk_dashboard(p: Principal = Depends(require_any("rsk:view")), db: Session = Depends(get_db)):
    _no_suppliers(db, p)
    counties = _counties(db, p, "rsk:view")
    flags = an.risk_flags(db, counties)
    by_rule: dict = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    for f in flags:
        by_rule[f["rule"]][f["severity"]] += 1
    return {"flags": flags, "by_rule": by_rule, "suppliers": an.supplier_risk(flags), "rules": an.rules(db),
            "counts": {s: sum(1 for f in flags if f["severity"] == s) for s in ("high", "medium", "low")}}


@router.post("/risk/scan")
def risk_scan(request: Request, p: Principal = Depends(require_any("rsk:create", "rsk:edit")), db: Session = Depends(get_db)):
    """Run the rules now and open an exception case for each new medium or high flag."""
    _no_suppliers(db, p)
    flags = an.risk_flags(db, _counties(db, p, "rsk:create", "rsk:edit"))
    n = an.raise_new_cases(db, flags, p.id)
    audit.record(db, action="RISK_SCAN", entity="risk", entity_id="scan", user=p.user, after={"flags": len(flags), "new_cases": n}, request=request)
    db.commit()
    return {"flags": len(flags), "new_cases": n}


@router.put("/risk/rules")
def set_rules(body: dict, request: Request, p: Principal = Depends(require_any("rsk:edit")), db: Session = Depends(get_db)):
    _no_suppliers(db, p)     # thresholds are programme-wide; every change is audited
    cur = an.rules(db)
    for k, v in body.items():
        if k not in an.DEFAULT_RULES or not isinstance(v, dict):
            raise AppError(422, "VALIDATION_ERROR", f"Unknown rule {k}.")
        for kk, vv in v.items():
            if kk not in an.DEFAULT_RULES[k]:
                raise AppError(422, "VALIDATION_ERROR", f"Unknown setting {k}.{kk}.")
            cur[k][kk] = vv
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == "risk.rules"))
    before = dict(s.value) if s else {}
    if s is None:
        s = SystemSetting(key="risk.rules", value=cur, description="Automated risk flag thresholds")
        db.add(s)
    else:
        s.value = cur
    audit.record(db, action="RISK_RULES", entity="system_setting", entity_id="risk.rules", user=p.user, before=before, after=cur, request=request)
    db.commit()
    return cur


@router.get("/performance/counties")
def county_performance(p: Principal = Depends(require_any("meal:view", "cmp:view")), db: Session = Depends(get_db)):
    """Buyer-side performance (FR-CMP-03): how quickly counties approve and pay, and how schools confirm deliveries."""
    _no_suppliers(db, p)
    counties = _counties(db, p, "meal:view", "cmp:view")
    rows = []
    target = settings.payment_target_days
    wf_rows = db.scalars(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions))).all()
    for c in db.scalars(select(Organization).where(Organization.type == OrgType.county)).all():
        if counties is not None and c.id not in counties:
            continue
        invs = db.scalars(select(Invoice).where(Invoice.county_id == c.id)).all()
        paid = [i for i in invs if i.paid_at]
        days = [(as_utc(i.paid_at) - as_utc(i.submitted_at)).days for i in paid]
        wfs = [w for w in wf_rows if w.scope_org_id and county_of(db, w.scope_org_id) == c.id]
        done = [w for w in wfs if w.finished_at]
        hours = [(as_utc(w.finished_at) - as_utc(w.started_at)).total_seconds() / 3600 for w in done]
        overdue = [w for w in wfs if w.status == InstanceStatus.active and w.stage_due_at and as_utc(w.stage_due_at) < utcnow()]
        disp = {d.id: d for d in db.scalars(select(Dispatch).where(Dispatch.county_id == c.id)).all()}
        pods = db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.dispatch_id.in_(list(disp) or [uuid.uuid4()]))).all()
        confirm = []
        for x in pods:
            ms = next((m for m in disp[x.dispatch_id].milestones or [] if m.get("status") == "dispatched"), None)
            if ms:
                confirm.append((as_utc(x.created_at) - datetime.fromisoformat(ms["at"])).total_seconds() / 3600)
        comp = db.scalars(select(Complaint).where(Complaint.org_id == c.id)).all()
        res = [x for x in comp if x.resolved_at]
        in_sla = [x for x in res if x.due_at and as_utc(x.resolved_at) <= as_utc(x.due_at)]
        rows.append({"county_id": c.id, "county": c.name, "invoices": len(invs), "paid": len(paid),
                     "avg_days_to_pay": round(sum(days) / len(days), 1) if days else None,
                     "paid_within_target_pct": round(sum(1 for d in days if d <= target) / len(days) * 100, 1) if days else None,
                     "approvals_completed": len(done), "avg_approval_hours": round(sum(hours) / len(hours), 1) if hours else None,
                     "approvals_overdue": len(overdue), "deliveries_confirmed": len(pods),
                     "avg_hours_to_confirm_delivery": round(sum(confirm) / len(confirm), 1) if confirm else None,
                     "complaints": len(comp), "complaints_resolved_in_sla_pct": round(len(in_sla) / len(res) * 100, 1) if res else None,
                     "unpaid_approved": sum(1 for i in invs if i.status in (InvoiceStatus.approved, InvoiceStatus.partially_paid)),
                     "payment_target_days": target})
    return rows
