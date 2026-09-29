"""Demand calculation, validation and nutrition checks (FR-DEM-02, -03, -05, -06).

Per commodity c on a menu cycle of n days:
  grams per learner per cycle   G_c = Σ portion_g(c) over the n menu days
  cycles in the term            k   = feeding_days / n
  gross (kg)  = enrolment × attendance% × k × G_c / 1000 × (1 + wastage%)
  net (kg)    = max(0, gross − stock on hand)
Units other than kg (litre, tray) use the same formula with the portion expressed in that unit ×1000."""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Commodity, DemandLine, Menu, SchoolDemand, SystemSetting

Q = Decimal("0.01")
DEFAULT_RULES = {"min_food_groups_per_cycle": 4,
                 "recommended_groups": ["Cereal", "Legume", "Vegetable", "Fruit", "Animal-source", "Oil"],
                 "max_enrolment_change_pct": 30, "max_kg_per_learner_per_day": 0.6}


def rules(db: Session) -> dict:
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == "nutrition.rules"))
    return {**DEFAULT_RULES, **(s.value if s else {})}


def menu_summary(db: Session, menu: Menu) -> dict:
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    groups: dict[str, int] = {}
    per_commodity: dict[str, Decimal] = {}
    unknown = set()
    for d in menu.days:
        day_groups = set()
        for comp in d.components:
            code, g = comp.get("commodity"), Decimal(str(comp.get("portion_g", 0) or 0))
            c = comms.get(code)
            if c is None:
                unknown.add(code)
                continue
            per_commodity[code] = per_commodity.get(code, Decimal(0)) + g
            if c.food_group:
                day_groups.add(c.food_group)
        for fg in day_groups:
            groups[fg] = groups.get(fg, 0) + 1
    r = rules(db)
    missing = [g for g in r["recommended_groups"] if g not in groups]
    return {"cycle_days": len(menu.days), "food_groups": groups, "group_count": len(groups),
            "meets_minimum": len(groups) >= r["min_food_groups_per_cycle"], "minimum": r["min_food_groups_per_cycle"],
            "missing_groups": missing, "grams_per_learner_cycle": {k: str(v) for k, v in per_commodity.items()},
            "unknown_commodities": sorted(x for x in unknown if x)}


def calculate(db: Session, d: SchoolDemand, stock: dict[str, Decimal] | None = None) -> None:
    """(Re)build lines from the menu. Preserves stock entries and overrides already on the demand."""
    old = {ln.commodity_code: ln for ln in d.lines}
    stock = stock or {}
    menu = db.get(Menu, d.menu_id) if d.menu_id else None
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    d.nutrition = menu_summary(db, menu) if menu else {}
    new_lines = []
    if menu and menu.days:
        n = len(menu.days)
        k = Decimal(d.feeding_days) / Decimal(n)
        learners = Decimal(d.enrolment) * Decimal(d.attendance_pct) / Decimal(100)
        waste = Decimal(1) + Decimal(d.wastage_pct) / Decimal(100)
        for code, g in d.nutrition["grams_per_learner_cycle"].items():
            g = Decimal(g)
            gross = (learners * k * g / Decimal(1000) * waste).quantize(Q, ROUND_HALF_UP)
            prev = old.get(code)
            st = Decimal(stock.get(code, prev.stock_qty if prev else 0))
            ln = DemandLine(commodity_code=code, unit=comms[code].unit if code in comms else "kg",
                            grams_per_learner_cycle=g, gross_qty=gross, stock_qty=st,
                            net_qty=max(Decimal(0), gross - st).quantize(Q),
                            override_qty=prev.override_qty if prev else None,
                            override_reason=prev.override_reason if prev else "")
            new_lines.append(ln)
    d.lines.clear()
    db.flush()
    d.lines.extend(new_lines)


def validate(db: Session, d: SchoolDemand, previous: SchoolDemand | None) -> list[dict]:
    """FR-DEM-03 validation findings. severity: error blocks submission; warning needs attention."""
    f = []
    r = rules(db)
    add = lambda code, sev, msg: f.append({"code": code, "severity": sev, "message": msg})  # noqa: E731
    if d.enrolment <= 0:
        add("NO_ENROLMENT", "error", "Enter the number of learners.")
    if not d.menu_id:
        add("NO_MENU", "error", "Choose an approved menu.")
    if not (0 < float(d.attendance_pct) <= 100):
        add("ATTENDANCE", "error", "Expected attendance must be between 1 and 100%.")
    if d.term and d.feeding_days > d.term.feeding_days:
        add("FEEDING_DAYS", "error", f"Feeding days exceed the term calendar ({d.term.feeding_days}).")
    if d.feeding_days <= 0:
        add("FEEDING_DAYS", "error", "Enter the number of feeding days.")
    for ln in d.lines:
        if ln.stock_qty < 0:
            add("NEGATIVE_STOCK", "error", f"Stock for {ln.commodity_code} cannot be negative.")
        if ln.override_qty is not None and not ln.override_reason.strip():
            add("OVERRIDE_REASON", "error", f"Give a reason for changing the quantity of {ln.commodity_code}.")
    if previous and previous.enrolment:
        ch = abs(d.enrolment - previous.enrolment) / previous.enrolment * 100
        if ch > r["max_enrolment_change_pct"]:
            add("ENROLMENT_CHANGE", "warning",
                f"Enrolment changed {ch:.0f}% from last term ({previous.enrolment}). Please confirm.")
    if d.lines and d.enrolment and d.feeding_days:
        total = sum(float(ln.final_qty) for ln in d.lines if ln.unit == "kg")
        per_day = total / (d.enrolment * d.feeding_days)
        if per_day > r["max_kg_per_learner_per_day"]:
            add("EXCESSIVE_QTY", "warning", f"About {per_day:.2f} kg per learner per day is unusually high.")
    if d.storage_capacity_kg and d.lines:
        biggest = max(float(ln.final_qty) for ln in d.lines)
        if biggest > float(d.storage_capacity_kg):
            add("STORAGE", "warning", "One delivery may exceed storage capacity. Consider split deliveries.")
    if d.nutrition and not d.nutrition.get("meets_minimum", True):
        add("DIVERSITY", "warning", f"The menu covers {d.nutrition['group_count']} food groups; the minimum is {d.nutrition['minimum']}.")
    return f
