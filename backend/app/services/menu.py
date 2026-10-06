"""Portal features (menu pages) per role and per user.

Every role gets a default set of pages (ROLE_DEFAULTS). The Super Administrator can change a role's defaults and can add
or remove pages for an individual user. A page appears in a user's menu only when it is in that user's set AND the user
holds a permission the page needs: giving someone a page never gives them new rights. When a page needs a permission the
user does not have, the Super Administrator must assign a role that includes it (Users & roles).

Stored in system_settings: "menu.roles" = {role_key: [page, ...]} (only roles that were changed) and
"menu.users" = {user_id: {"add": [...], "remove": [...]}}."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Supplier, SystemSetting, User

# page -> (label, group, permissions (any of), audience) ; audience: "staff", "supplier" or "all"
FEATURES: dict[str, tuple[str, str, tuple[str, ...], str]] = {
    "/app/approvals": ("My approvals", "Overview", (), "all"),
    "/app/my-supplier": ("My supplier profile", "Supplier", (), "supplier"),
    "/app/demand": ("School demand", "Plan", ("dem:view",), "all"),
    "/app/locations": ("School locations", "Plan", ("md:edit", "inv:create", "agg:create", "log:approve"), "staff"),
    "/app/menus": ("Menus & terms", "Plan", ("dem:view", "md:view"), "staff"),
    "/app/plans": ("Procurement plans", "Plan", ("src:view", "bud:view", "dem:approve"), "staff"),
    "/app/budgets": ("Budgets", "Plan", ("bud:view",), "all"),
    "/app/opportunities": ("Opportunities", "Supplier", (), "supplier"),
    "/app/orders": ("My contracts & orders", "Supplier", (), "supplier"),
    "/app/suppliers": ("Supplier registry", "Source", ("sup:view",), "staff"),
    "/app/sourcing": ("Sourcing events", "Source", ("src:view",), "staff"),
    "/app/evaluations": ("My evaluations", "Source", ("eva:evaluate",), "all"),
    "/app/contracts": ("Contracts & POs", "Source", ("con:view",), "staff"),
    "/app/aggregation": ("Aggregation & intake", "Fulfil", ("agg:create", "agg:submit"), "all"),
    "/app/quality": ("Quality inspection", "Fulfil", ("agg:verify",), "all"),
    "/app/inventory": ("Inventory", "Fulfil", ("inv:view",), "all"),
    "/app/dispatch": ("Dispatch", "Fulfil", ("log:create",), "all"),
    "/app/deliveries": ("Deliveries", "Fulfil", ("log:view",), "all"),
    "/app/trace": ("Traceability", "Fulfil", ("agg:view", "log:view", "meal:view"), "all"),
    "/app/invoices": ("Invoices & payments", "Performance & finance", ("fin:view",), "all"),
    "/app/complaints": ("Complaints", "Performance & finance", ("cmp:view", "cmp:create"), "all"),
    "/app/performance": ("Supplier performance", "Performance & finance", ("sup:view", "cmp:view", "meal:view"), "all"),
    "/app/integrations": ("Payment integrations", "Performance & finance", ("fin:verify", "fin:pay", "fin:export"), "staff"),
    "/app/insights": ("Forecasts & prices", "Performance & finance", ("inv:view", "meal:view"), "staff"),
    "/app/map": ("Programme map", "Performance & finance", ("meal:view", "log:view", "rsk:view"), "staff"),
    "/app/meal": ("MEAL dashboard", "Performance & finance", ("meal:view",), "staff"),
    "/app/admin": ("Admin console", "Administration", ("iam:edit", "cms:approve"), "all"),
    "/app/readiness": ("Pilot readiness", "Administration", ("iam:edit", "md:edit"), "all"),
    "/app/users": ("Users & roles", "Administration", ("iam:view",), "all"),
    "/app/features": ("Features & menus", "Administration", ("iam:edit",), "super"),
    "/app/master-data": ("Master data", "Administration", ("md:edit",), "all"),
    "/app/system": ("System & onboarding", "Administration", ("iam:edit", "md:edit"), "all"),
    "/app/website": ("Website content", "Administration", ("cms:view",), "all"),
    "/app/exceptions": ("Exceptions", "Oversight", ("rsk:view",), "all"),
    "/app/risk": ("Risk dashboard", "Oversight", ("rsk:view",), "staff"),
    "/app/audit": ("Audit trail", "Oversight", ("aud:view",), "all"),
}
ALWAYS = ["/app", "/app/notifications", "/app/profile"]

_ADMIN = ["/app/admin", "/app/readiness", "/app/users", "/app/master-data", "/app/system", "/app/website", "/app/menus", "/app/locations",
          "/app/audit"]
_SUPPLIER = ["/app/approvals", "/app/my-supplier", "/app/opportunities", "/app/orders", "/app/invoices", "/app/complaints", "/app/performance"]
_PROCUREMENT = ["/app/approvals", "/app/menus", "/app/demand", "/app/plans", "/app/suppliers", "/app/sourcing", "/app/contracts",
                "/app/complaints", "/app/exceptions", "/app/performance", "/app/insights", "/app/trace"]

# The pages each role works with (see docs/LisheBora_Process_Guide.docx for who does what).
ROLE_DEFAULTS: dict[str, list[str]] = {
    "super_admin": _ADMIN + ["/app/features"],
    "system_admin": _ADMIN,
    "content_editor": ["/app/website"],
    "helpdesk_officer": ["/app/users", "/app/suppliers", "/app/complaints"],
    "county_admin": ["/app/approvals", "/app/demand", "/app/plans", "/app/budgets", "/app/suppliers", "/app/sourcing", "/app/contracts",
                     "/app/complaints", "/app/exceptions", "/app/performance", "/app/meal", "/app/map", "/app/risk"],
    "county_procurement_officer": _PROCUREMENT,
    "procurement_officer": _PROCUREMENT,
    "county_finance_officer": ["/app/approvals", "/app/budgets", "/app/plans", "/app/contracts", "/app/invoices"],
    "finance_officer": ["/app/approvals", "/app/invoices", "/app/integrations"],
    "nutrition_officer": ["/app/approvals", "/app/menus", "/app/demand"],
    "approving_officer": ["/app/approvals", "/app/sourcing", "/app/contracts"],
    "evaluation_committee_member": ["/app/evaluations"],
    "school_admin": ["/app/approvals", "/app/demand", "/app/locations", "/app/deliveries", "/app/inventory", "/app/complaints", "/app/trace"],
    "school_meals_officer": ["/app/approvals", "/app/demand", "/app/locations", "/app/inventory", "/app/deliveries", "/app/insights",
                             "/app/complaints"],
    "quality_inspector": ["/app/quality", "/app/aggregation", "/app/trace"],
    "warehouse_officer": ["/app/approvals", "/app/inventory", "/app/trace"],
    "logistics_officer": ["/app/dispatch", "/app/deliveries", "/app/map", "/app/locations"],
    "driver": ["/app/deliveries"],
    "supplier": _SUPPLIER,
    "farmer_group": _SUPPLIER,
    "aggregator": _SUPPLIER + ["/app/aggregation", "/app/inventory", "/app/trace"],
    "programme_meal_officer": ["/app/meal", "/app/map", "/app/performance", "/app/insights", "/app/complaints"],
    "risk_compliance_officer": ["/app/risk", "/app/exceptions", "/app/complaints", "/app/performance", "/app/audit"],
    "auditor": ["/app/audit", "/app/plans", "/app/budgets", "/app/sourcing", "/app/contracts", "/app/invoices", "/app/exceptions"],
}


def _setting(db: Session, key: str) -> dict:
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return dict(s.value or {}) if s else {}


def save_setting(db: Session, key: str, value: dict, description: str):
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if s is None:
        s = SystemSetting(key=key, value=value, description=description)
        db.add(s)
    else:
        s.value = value


def role_pages(db: Session, role_key: str) -> list[str]:
    over = _setting(db, "menu.roles")
    return list(over[role_key]) if role_key in over else list(ROLE_DEFAULTS.get(role_key, []))


def user_overrides(db: Session, user_id) -> dict:
    return _setting(db, "menu.users").get(str(user_id), {"add": [], "remove": []})


def user_permissions(user: User) -> set[str]:
    return {rp.permission.code for ur in user.roles if ur.is_active for rp in ur.role.permissions}


def is_supplier_account(db: Session, user: User) -> bool:
    ids = [ur.org_id for ur in user.roles if ur.is_active and ur.org_id]
    return bool(ids) and db.scalar(select(Supplier.id).where(Supplier.organization_id.in_(ids))) is not None


def allowed(page: str, perms: set[str], supplier: bool, super_admin: bool) -> bool:
    """Whether the account's permissions let it use this page at all."""
    _label, _group, need, aud = FEATURES[page]
    if aud == "supplier" and not supplier:
        return False
    if aud == "staff" and supplier:
        return False
    if aud == "super" and not super_admin:
        return False
    return not need or bool(perms & set(need))


def menu_for(db: Session, user: User) -> list[str]:
    keys = [ur.role.key for ur in user.roles if ur.is_active]
    perms, supplier = user_permissions(user), is_supplier_account(db, user)
    defaults = {p for k in keys for p in role_pages(db, k)}
    ov = user_overrides(db, user.id)
    pages = (defaults | set(ov.get("add", []))) - set(ov.get("remove", []))
    sup = "super_admin" in keys
    return ALWAYS + [p for p in FEATURES if p in pages and allowed(p, perms, supplier, sup)]


def who_has(db: Session, codes: tuple[str, ...]) -> list[str]:
    """Role names that hold any of these permissions (to tell the Super Administrator which role to assign)."""
    from app.models import Role
    out = []
    for r in db.scalars(select(Role).order_by(Role.name)).all():
        if r.key in ("super_admin", "system_admin"):     # administrator roles cannot be combined with other roles
            continue
        if {rp.permission.code for rp in r.permissions} & set(codes):
            out.append(r.name)
    return out
