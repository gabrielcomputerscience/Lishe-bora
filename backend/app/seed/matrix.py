"""Role × Domain permission matrix — SRS Consolidated Draft v0.3, Section 6.4
(+ 'cms' domain for the admin-managed public website, new in this build).

Letters: V view · C create · E edit · S submit · Vf verify · Ev evaluate · A approve · R reject · P pay · X export · Au audit
"""
ACTIONS = {"V": "view", "C": "create", "E": "edit", "S": "submit", "Vf": "verify", "Ev": "evaluate",
           "A": "approve", "R": "reject", "P": "pay", "X": "export", "Au": "audit"}

DOMAINS = {
    "iam": "Identity & Access", "md": "Master Data", "dem": "Demand & Nutrition", "bud": "Budget",
    "sup": "Supplier", "src": "Sourcing & bids", "eva": "Evaluation & award", "con": "Contracts & POs",
    "agg": "Aggregation & quality", "inv": "Inventory", "log": "Logistics & delivery", "fin": "Finance",
    "cmp": "Complaints & performance", "rsk": "Risk & exceptions", "meal": "Dashboards & reports",
    "aud": "Audit log", "cms": "Public website content",
}
ORDER = ["iam", "md", "dem", "bud", "sup", "src", "eva", "con", "agg", "inv", "log", "fin", "cmp", "rsk", "meal", "aud"]

# key: (name, tier, default_scope, requires_mfa, [16 cells in ORDER], cms cell)
ROLES = {
 # Administrator accounts sign in separately and hold no other role (app/services/admin_access.py).
 # Super Administrator: everything an Administrator does, plus creating and managing administrator accounts.
 "super_admin": ("Super Administrator", "core", "national", True,
   ["V C E S A R", "V C E S A R", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V X", "V Au X"], "V C E S A R"),
 # Administrator (SRS "System Administrator"): manages all content — the public website (write and publish), master
 # data (counties, schools, commodities, food categories, menus/terms), users other than administrators, onboarding
 # imports and background jobs. Read-only on operational records; it cannot approve, award or pay.
 "system_admin": ("Administrator", "core", "national", True,
   ["V C E S", "V C E S A R", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V X", "V"], "V C E S A R"),
 "county_admin": ("County Administrator", "core", "county", True,
   ["V", "V", "V A R", "V A R", "V A R", "V", "V", "V", "V", "V", "V", "V", "V A", "V A", "V X", "—"], "—"),
 "county_procurement_officer": ("County Procurement Officer", "core", "county", True,
   ["—", "V", "V Vf", "V", "V Vf", "C E S", "V", "C E S", "V", "V", "V", "V", "V C", "V C", "V X", "—"], "—"),
 "county_finance_officer": ("County Finance Officer", "core", "county", True,
   ["—", "V", "V", "C E S Vf", "V", "V", "V", "V", "—", "—", "V", "V Vf A R", "V C", "V C", "V X", "—"], "—"),
 "school_admin": ("School Administrator", "core", "school", False,
   ["—", "V", "V Vf A R", "V", "—", "V", "V", "V", "—", "C E", "V Vf A R", "V", "C S V", "—", "V", "—"], "—"),
 "school_meals_officer": ("School Meals Officer", "core", "school", False,
   ["—", "V", "C E S", "V", "—", "—", "—", "—", "—", "C E", "V", "—", "C S V", "—", "V", "—"], "—"),
 "procurement_officer": ("Procurement Officer", "core", "entity", True,
   ["—", "V", "V", "V", "V Vf", "C E S", "V", "C E S", "V", "V", "V", "V", "V C", "V C", "V X", "—"], "—"),
 "evaluation_committee_member": ("Evaluation Committee Member", "core", "event", False,
   ["—", "—", "—", "—", "V", "V", "V Ev S", "—", "—", "—", "—", "—", "—", "—", "—", "—"], "—"),
 "quality_inspector": ("Quality Inspector", "core", "area", False,
   ["—", "V", "—", "—", "V Vf", "—", "—", "—", "C E Vf A R", "V", "V", "—", "V C", "C", "V", "—"], "—"),
 "aggregator": ("Aggregator", "core", "own_org", False,
   ["—", "V", "—", "—", "C S", "V C S", "V", "V", "C E S", "C E", "C E S", "C S V", "C S V", "—", "V", "—"], "—"),
 "supplier": ("Supplier", "core", "own_org", False,
   ["—", "V", "—", "—", "C E S", "V C S", "V", "V", "V", "—", "V E", "C S V", "C S V", "—", "V", "—"], "—"),
 "warehouse_officer": ("Warehouse Officer", "core", "warehouse", False,
   ["—", "V", "—", "—", "—", "—", "—", "V", "V", "C E S Vf", "V C", "—", "C S", "C", "V", "—"], "—"),
 "logistics_officer": ("Logistics Officer", "core", "area", False,
   ["—", "V", "—", "—", "—", "—", "—", "V", "V", "V", "C E S", "—", "V C", "C", "V X", "—"], "—"),
 "finance_officer": ("Finance Officer", "core", "entity", True,
   ["—", "V", "—", "V", "V", "—", "—", "V", "—", "—", "V", "V C Vf P X", "V", "V C", "V X", "—"], "—"),
 "programme_meal_officer": ("Programme/MEAL Officer", "core", "programme", False,
   ["—", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V C X", "—"], "V"),
 "auditor": ("Auditor", "core", "national", False,
   ["V Au"] * 14 + ["V X", "V Au X"], "V"),
 "nutrition_officer": ("Nutrition Officer", "optional", "county", False,
   ["—", "C E S", "V Vf A R", "—", "—", "—", "—", "—", "—", "—", "—", "—", "V", "—", "V X", "—"], "—"),
 "approving_officer": ("Approving Officer", "optional", "threshold", True,
   ["—", "V", "V", "V A R", "V", "V A R", "V A R", "V A R", "—", "—", "—", "—", "V", "V", "V", "—"], "—"),
 "farmer_group": ("Farmer Group / Cooperative", "optional", "own_org", False,
   ["—", "V", "—", "—", "C E S", "V C S", "V", "V", "V", "—", "—", "V", "C S V", "—", "V", "—"], "—"),
 "driver": ("Driver", "optional", "trip", False,
   ["—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "V E", "—", "C S", "—", "—", "—"], "—"),
 "risk_compliance_officer": ("Risk/Compliance Officer", "optional", "programme", False,
   ["—", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "V", "C E A R", "V X", "V"], "—"),
 "helpdesk_officer": ("Helpdesk Officer", "optional", "programme", False,
   ["V E", "V", "—", "—", "C", "—", "—", "—", "—", "—", "—", "—", "C S", "—", "—", "—"], "—"),
 "content_editor": ("Content Editor (website)", "optional", "national", False,
   ["—"] * 16, "V C E S"),
}

# Segregation-of-duties: role pairs that must never be held by the same user (SRS §6.5)
CONFLICTING_ROLE_PAIRS = [
    ("finance_officer", "county_finance_officer"),   # SoD-07/08: match + approve + pay
    ("supplier", "evaluation_committee_member"),     # SoD-04
    ("supplier", "quality_inspector"),
    ("supplier", "approving_officer"),
    ("aggregator", "quality_inspector"),             # SoD-09
    ("warehouse_officer", "approving_officer"),      # SoD-10 (simplified)
]


def parse_cell(cell: str) -> list[str]:
    if not cell or cell.strip() in ("—", "-"):
        return []
    return [ACTIONS[t] for t in cell.split()]


def role_permission_codes(key: str) -> set[str]:
    """Any permission on a domain implies 'view' on it (you cannot edit what you cannot see).
    Records remain limited to the role's data scope, so e.g. a supplier's sup:view only covers its own record."""
    name, tier, scope, mfa, cells, cms = ROLES[key]
    codes = {f"{d}:{a}" for d, cell in zip(ORDER, cells) for a in parse_cell(cell)}
    codes |= {f"cms:{a}" for a in parse_cell(cms)}
    codes |= {f"{c.split(':')[0]}:view" for c in codes}
    return codes


def all_permission_codes() -> set[str]:
    out: set[str] = set()
    for k in ROLES:
        out |= role_permission_codes(k)
    return out
