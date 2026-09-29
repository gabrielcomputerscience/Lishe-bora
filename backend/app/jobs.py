"""Background jobs (SRS §9: task queue for notifications, scheduled alerts and SLA monitoring).

Usage:
    python -m app.jobs all              # run every task once
    python -m app.jobs send             # just deliver queued SMS / email
    python -m app.jobs all --loop 60    # keep running; every 60 s sends messages, other tasks at their own interval

Run one worker per deployment (the docker compose `worker` service, or a Windows scheduled task every few minutes).
Every task is idempotent: re-running never sends the same reminder twice."""
import argparse
import logging
import time
import traceback
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.timeutil import as_utc, utcnow

log = logging.getLogger("lishebora.jobs")
INTERVALS = {"send": 60, "sla": 900, "late_payments": 3600, "risk": 6 * 3600, "documents": 12 * 3600, "contracts": 12 * 3600, "stock": 12 * 3600}


def _already(db: Session, user_ids, event: str, link: str, days: int) -> set:
    """Users who already got this reminder recently (reminders are keyed by event + link)."""
    from app.models import Notification
    since = utcnow() - timedelta(days=days)
    return set(db.scalars(select(Notification.user_id).where(Notification.event == event, Notification.link == link,
                                                              Notification.created_at >= since, Notification.user_id.in_(list(user_ids) or [None]))))


def _remind(db, users, title, body, link, event, days=30, sms=False) -> int:
    from app.services import notifications as note
    users = set(users) - _already(db, users, event, link, days)
    if users:
        note.to_users(db, users, title, body, link, event, sms=sms)
    return len(users)


def task_send(db: Session) -> dict:
    from app.services import notify
    return notify.send_queued(db)


def task_late_payments(db: Session) -> dict:
    from app.api.v1.finance import sweep_late_payments
    return {"raised": sweep_late_payments(db)}


def task_risk(db: Session) -> dict:
    from app.services import analytics as an
    flags = an.risk_flags(db, None)
    n = an.raise_new_cases(db, flags, None)
    db.commit()
    return {"flags": len(flags), "new_cases": n}


def task_sla(db: Session) -> dict:
    """Overdue approvals: remind whoever can act; after twice the SLA, escalate to the county administrator (FR-PLT-01)."""
    from app.api.v1.workflow import LINKS
    from app.models import InstanceStatus, WorkflowInstance
    from app.services import notifications as note, workflow as wf
    from app.services.stock import county_of
    now, reminded, escalated = utcnow(), 0, 0
    for inst in db.scalars(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions))
                           .where(WorkflowInstance.status == InstanceStatus.active)).all():
        due = as_utc(inst.stage_due_at)
        if not due or due > now:
            continue
        st = wf.current_stage(inst)
        link = LINKS.get(inst.entity, "/app/approvals").format(id=inst.entity_id)
        actors = set(note.users_with_permission(db, st.permission, inst.scope_org_id)) - {inst.initiator_id}
        reminded += _remind(db, actors, f"Overdue approval: {inst.title}", f"{st.label} was due {due:%d %b %H:%M}.", link, "sla_overdue", days=1)
        sla = timedelta(days=st.sla_days)
        if now - due >= sla:
            county = county_of(db, inst.scope_org_id) if inst.scope_org_id else None
            admins = note.users_with_role(db, "county_admin", county) if county else []
            escalated += _remind(db, admins, f"Escalated: {inst.title}", f"{st.label} is overdue by more than {st.sla_days} day(s).", link,
                                 "sla_escalated", days=3, sms=True)
    db.commit()
    return {"reminded": reminded, "escalated": escalated}


def task_documents(db: Session) -> dict:
    from app.models import Supplier, SupplierStatus
    from app.services import notifications as note
    soon, n = date.today() + timedelta(days=30), 0
    for s in db.scalars(select(Supplier).options(selectinload(Supplier.documents)).where(
            Supplier.status.in_([SupplierStatus.approved, SupplierStatus.prequalified, SupplierStatus.active]))).all():
        for d in s.documents:
            if d.expires_on and d.expires_on <= soon:
                what = "has expired" if d.expires_on < date.today() else f"expires on {d.expires_on:%d %b %Y}"
                n += _remind(db, note.users_of_org(db, s.organization_id), f"Document {what}: {d.doc_type.replace('_', ' ')}",
                             "Upload a current copy to stay eligible for opportunities.", f"/app/my-supplier?doc={d.id}", "doc_expiry", days=14, sms=True)
    db.commit()
    return {"reminders": n}


def task_contracts(db: Session) -> dict:
    from app.models import Contract, ContractStatus
    from app.services import notifications as note
    soon, n = date.today() + timedelta(days=14), 0
    for c in db.scalars(select(Contract).where(Contract.status == ContractStatus.active, Contract.ends_on <= soon)).all():
        users = note.users_with_role(db, "county_procurement_officer", c.county_id) if c.county_id else []
        n += _remind(db, users, f"Contract {c.reference} ends {c.ends_on:%d %b %Y}", "Plan a new sourcing event or an extension in time.",
                     "/app/contracts", "contract_expiry:" + c.reference, days=7)
        if c.ends_on < date.today():
            c.status = ContractStatus.expired
    db.commit()
    return {"reminders": n}


def task_stock(db: Session) -> dict:
    from app.services import analytics as an, notifications as note, stock
    n = 0
    for r in stock.balances(db, None):
        if r["expiry_date"] and float(r["on_hand"]) > 0 and (r["expiry_date"] - date.today()).days <= 14:
            n += _remind(db, note.users_of_org(db, r["location_id"]), f"{r['commodity_code']} batch {r['batch_code']} expires {r['expiry_date']:%d %b}",
                         f"{r['on_hand']} {r['unit']} on hand. Use it first.", f"/app/inventory?batch={r['batch_id']}", "stock_expiry", days=7)
    for o in an.stock_outlook(db, None):
        if o["risk"] == "high":
            n += _remind(db, note.users_of_org(db, o["school_id"]), f"{o['commodity']} runs out in about {o['days_left']} days",
                         "Tell the county procurement office if a delivery is not on the way.", "/app/insights", "stockout:" + o["commodity_code"], days=5)
    db.commit()
    return {"reminders": n}


TASKS = {"send": task_send, "sla": task_sla, "late_payments": task_late_payments, "risk": task_risk, "documents": task_documents,
         "contracts": task_contracts, "stock": task_stock}


def _record(db: Session, name: str, result: dict | None, error: str = ""):
    from app.models import SystemSetting
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == "jobs.last_run"))
    if s is None:
        s = SystemSetting(key="jobs.last_run", value={}, description="Background job status (written by the worker)")
        db.add(s)
    s.value = {**(s.value or {}), name: {"at": utcnow().isoformat(), "result": result, "error": error[:300]}}
    db.commit()


def run(names: list[str]) -> dict:
    out = {}
    for name in names:
        db = SessionLocal()
        try:
            out[name] = TASKS[name](db)
            _record(db, name, out[name])
        except Exception as e:     # a failing task must not stop the others
            db.rollback()
            log.error("Job %s failed: %s", name, traceback.format_exc())
            out[name] = {"error": str(e)}
            _record(db, name, None, str(e))
        finally:
            db.close()
    return out


def main():
    ap = argparse.ArgumentParser(description="LisheBora background jobs")
    ap.add_argument("task", nargs="?", default="all", choices=["all", *TASKS])
    ap.add_argument("--loop", type=int, default=0, help="keep running; seconds between cycles")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    names = list(TASKS) if a.task == "all" else [a.task]
    if not a.loop:
        print(run(names))
        return
    last: dict[str, float] = {}
    log.info("Worker started: %s every %ss", ", ".join(names), a.loop)
    while True:
        due = [n for n in names if time.time() - last.get(n, 0) >= INTERVALS.get(n, a.loop)]
        if due:
            res = run(due)
            last.update({n: time.time() for n in due})
            log.info("Jobs: %s", res)
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
