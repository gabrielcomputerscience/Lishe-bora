"""Budget status and commitment control (FR-BUD-02…06, BR-001, BR-008).

  approved − held commitments − invoiced − paid = available
Financial terminology (commitment vs obligation vs expenditure) to be confirmed with Finance (SRS §14 Q22)."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import BudgetLine, Commitment, CommitmentStatus

Z = Decimal("0.00")


def status(db: Session, line: BudgetLine) -> dict:
    rows = dict(db.execute(select(Commitment.status, func.coalesce(func.sum(Commitment.amount), 0))
                           .where(Commitment.budget_line_id == line.id).group_by(Commitment.status)).all())
    held = Decimal(rows.get(CommitmentStatus.held, 0) or 0)
    invoiced = Decimal(rows.get(CommitmentStatus.invoiced, 0) or 0)
    paid = Decimal(rows.get(CommitmentStatus.paid, 0) or 0)
    approved = Decimal(line.approved_amount)
    available = approved - held - invoiced - paid
    used_pct = float((approved - available) / approved * 100) if approved else 0.0
    alerts = []
    if available < 0:
        alerts.append({"code": "OVER_COMMITTED", "severity": "high", "message": "Commitments exceed the approved budget."})
    elif used_pct >= line.alert_threshold_pct:
        alerts.append({"code": "THRESHOLD", "severity": "medium",
                       "message": f"{used_pct:.0f}% of the budget is committed or spent."})
    return {"approved": approved, "committed": held, "invoiced": invoiced, "paid": paid,
            "available": available, "utilisation_pct": round(used_pct, 1), "alerts": alerts}


def check(db: Session, line: BudgetLine, amount: Decimal) -> dict:
    st = status(db, line)
    shortfall = max(Z, Decimal(amount) - st["available"])
    return {**st, "requested": Decimal(amount), "sufficient": shortfall == 0, "shortfall": shortfall}


def commit(db: Session, line: BudgetLine, *, amount: Decimal, source_entity: str, source_id, source_ref: str,
           exception_id=None, actor_id=None) -> Commitment:
    """Hold funds. Blocks when insufficient unless an approved exception covers the shortfall (BR-001)."""
    c = check(db, line, amount)
    if not c["sufficient"] and exception_id is None:
        raise AppError(409, "BUDGET_EXCEEDED", "The available budget is insufficient for this transaction.",
                       [{"available": str(c["available"]), "requested": str(amount), "shortfall": str(c["shortfall"])}])
    cm = Commitment(budget_line_id=line.id, amount=Decimal(amount), source_entity=source_entity, source_id=source_id,
                    source_ref=source_ref, exception_id=exception_id, created_by=actor_id)
    db.add(cm)
    db.flush()
    return cm


def release(db: Session, source_entity: str, source_id):
    for cm in db.scalars(select(Commitment).where(Commitment.source_entity == source_entity,
                                                  Commitment.source_id == source_id,
                                                  Commitment.status == CommitmentStatus.held)):
        cm.status = CommitmentStatus.released


def convert(db: Session, *, from_entity: str, from_id, from_status: CommitmentStatus, to_status: CommitmentStatus,
            amount: Decimal, new_entity: str, new_id, new_ref: str, actor_id=None) -> Commitment | None:
    """Move `amount` from one commitment state to the next (held → invoiced → paid), splitting rows as needed.
    Returns None when the source has no commitment (e.g. a contract without a budget line)."""
    rows = list(db.scalars(select(Commitment).where(Commitment.source_entity == from_entity, Commitment.source_id == from_id,
                                                    Commitment.status == from_status).order_by(Commitment.created_at)))
    if not rows:
        return None
    left = Decimal(amount)
    line_id = rows[0].budget_line_id
    for cm in rows:
        if left <= 0:
            break
        take = min(left, Decimal(cm.amount))
        cm.amount = Decimal(cm.amount) - take
        if cm.amount == 0:
            cm.status = CommitmentStatus.released    # fully converted; the new row carries the amount
        left -= take
    # anything beyond the commitment (should not happen after the match) still lands on the same line
    new = Commitment(budget_line_id=line_id, amount=Decimal(amount), source_entity=new_entity, source_id=new_id,
                     source_ref=new_ref, status=to_status, created_by=actor_id)
    db.add(new)
    db.flush()
    return new
