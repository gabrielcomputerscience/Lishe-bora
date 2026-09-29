"""Operational exception cases (FR-LOG-05, FR-AGG-04, FR-RSK-03): raised automatically, routed to an owner role with a due date."""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import ExceptionCase
from app.services import notifications as note
from app.services.refs import next_ref

SLA_DAYS = {"high": 2, "medium": 5, "low": 10}
OWNER = {"quality_rejection": "county_procurement_officer", "short_delivery": "county_procurement_officer",
         "rejected_goods": "county_procurement_officer", "late_delivery": "logistics_officer",
         "damaged": "county_procurement_officer", "stock_variance": "warehouse_officer", "waste": "warehouse_officer",
         "late_payment": "county_finance_officer", "batch_recall": "county_procurement_officer",
         "risk_flag": "risk_compliance_officer"}


def raise_case(db: Session, *, category: str, severity: str, entity: str, entity_id, entity_ref: str, org_id,
               title: str, detail: str = "", supplier_id=None, user_id=None) -> ExceptionCase:
    c = ExceptionCase(reference=next_ref(db, ExceptionCase, "EXC"), category=category, severity=severity, entity=entity,
                      entity_id=entity_id, entity_ref=entity_ref, org_id=org_id, supplier_id=supplier_id, title=title,
                      detail=detail, owner_role=OWNER.get(category, "county_procurement_officer"),
                      due_at=utcnow() + timedelta(days=SLA_DAYS.get(severity, 5)), created_by=user_id)
    db.add(c)
    db.flush()
    owners = note.users_with_role(db, c.owner_role, org_id) if org_id else []
    note.to_users(db, owners, f"Exception {c.reference}: {title}", detail[:200], "/app/exceptions?id=" + str(c.id), "exception")
    return c
