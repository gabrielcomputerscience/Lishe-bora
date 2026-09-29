"""Seed roles, permissions, the first super-admin, pilot geography, commodities and starter website content.
Safe to run repeatedly (idempotent).   Usage:  python -m app.seed.run  [--demo]"""
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.timeutil import utcnow
from datetime import date
from decimal import Decimal

from app.models import (AcademicTerm, BudgetLine, FundingSource, Menu, MenuDay, MenuStatus, SystemSetting, Commodity, ContentStatus, EventStatus, FaqItem, NewsPost, Organization, OrgType, Page,
                        Permission, ProcurementEvent, ProcurementMethod, Resource, Role, RolePermission, SiteBlock,
                        User, UserRole, UserStatus)
from app.seed.matrix import ACTIONS, DOMAINS, ROLES, all_permission_codes, role_permission_codes

from app.seed.reference import COUNTIES, FOOD_CATEGORIES, LEGACY_DEMO_COMMODITIES, SAMPLED_SCHOOLS

# (code, name, category key, unit, nutrition group) for every food item of the survey food categories
COMMODITIES = [(code, name, key, unit, group) for key, _label, group, items in FOOD_CATEGORIES for code, name, unit in items]


def upsert_permissions_and_roles(db: Session):
    perms = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code in sorted(all_permission_codes()):
        if code not in perms:
            d, a = code.split(":")
            perms[code] = Permission(code=code, domain=d, action=a, description=f"{a} — {DOMAINS[d]}")
            db.add(perms[code])
    db.flush()
    for key, (name, tier, scope, mfa, _cells, _cms) in ROLES.items():
        role = db.scalar(select(Role).where(Role.key == key))
        if role is None:
            role = Role(key=key, name=name, tier=tier, default_scope=scope, requires_mfa=mfa)
            db.add(role)
            db.flush()
        role.name, role.tier, role.default_scope, role.requires_mfa = name, tier, scope, mfa
        want = role_permission_codes(key)
        have = {rp.permission.code: rp for rp in role.permissions}
        for code in want - have.keys():
            role.permissions.append(RolePermission(permission=perms[code]))
        for code in have.keys() - want:
            role.permissions.remove(have[code])
    db.flush()


def org(db, type_, code, name, parent=None, **meta):
    o = db.scalar(select(Organization).where(Organization.code == code))
    if o is None:
        o = Organization(type=type_, code=code, name=name, parent_id=parent.id if parent else None, meta=meta)
        db.add(o)
        db.flush()
    return o


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^A-Z0-9]+", "-", s.upper()).strip("-")[:20]


def seed_geography(db, demo: bool = True):
    """Kenya > pilot counties > sub-counties > the sampled schools (real reference data, seeded in every mode).
    Codes follow the school importer ({county}-{SUB-COUNTY}), so a later CSV import updates rather than duplicates."""
    ke = org(db, OrgType.country, "KE", "Kenya")
    org(db, OrgType.programme, "STEP", "STEP School Feeding Project", ke)
    counties = {code: org(db, OrgType.county, code, name, ke) for code, name in COUNTIES}
    for county_code, sub_county, school_code, school_name in SAMPLED_SCHOOLS:
        c = counties[county_code]
        sc = org(db, OrgType.sub_county, f"{c.code}-{_slug(sub_county)}", sub_county, c)
        org(db, OrgType.school, school_code, school_name, sc, source="Schools-Sampled.xlsx")
    return counties


def seed_admin(db):
    u = db.scalar(select(User).where(User.email == settings.seed_admin_email.lower()))
    if u is None:
        u = User(full_name="Super Administrator", email=settings.seed_admin_email.lower(),
                 password_hash=hash_password(settings.seed_admin_password), status=UserStatus.active)
        db.add(u)
        db.flush()
        role = db.scalar(select(Role).where(Role.key == "super_admin"))
        db.add(UserRole(user_id=u.id, role_id=role.id, org_id=None))
        print(f"Created super admin: {settings.seed_admin_email}  (password from SEED_ADMIN_PASSWORD — change it!)")
    return u


def seed_commodities(db):
    """One commodity per survey food item. Existing codes get their category and group refreshed; commodity codes
    from earlier development builds are deactivated (kept, so records that reference them stay valid)."""
    for code, name, cat, unit, group in COMMODITIES:
        c = db.scalar(select(Commodity).where(Commodity.code == code))
        if c is None:
            db.add(Commodity(code=code, name=name, category=cat, unit=unit, food_group=group, quality_spec={}))
        else:
            c.category, c.food_group, c.is_active = cat, group, True
    for c in db.scalars(select(Commodity).where(Commodity.code.in_(LEGACY_DEMO_COMMODITIES), Commodity.is_active)).all():
        c.is_active = False
    db.flush()


FOR_SUPPLIERS = """LisheBora opens school food procurement to local producers. If you grow, aggregate, process or trade food that
schools buy, you can register once and receive alerts for every opportunity that matches what you supply.

## Who can register
- Individual farmers
- Farmer groups and cooperatives
- Aggregators and traders
- Processors and small food businesses (MSMEs)

## What you need
- A mobile phone number (a smartphone is not required; alerts also come by SMS)
- Your business or group registration certificate, if you have one
- Bank or M-Pesa payment details in the name of the business or group
- The foods you supply, chosen from the programme's food categories (grains, legumes, vegetables, fruits, roots and tubers, animal-source foods, oils and more)

## How it works for you
1. **Register** on the website or with help from a county officer, an aggregator or the helpdesk.
2. **Get prequalified.** The county checks your documents and approves the food categories you can supply.
3. **Receive alerts** by SMS and email when a matching opportunity opens.
4. **Submit a sealed bid** before the deadline. Nobody can see bids until they are opened together.
5. **Deliver.** Goods are inspected for quality and the school confirms what it received.
6. **Invoice and track payment** in your portal until it is paid.

## Fair for everyone
Every notice publishes its evaluation criteria in advance. Women-, youth- and PWD-led enterprises can declare their status
(voluntary, with consent) so that inclusion can be monitored. You can raise a complaint or grievance at any time on the Contact page.

*[Programme-specific eligibility rules and contacts to be confirmed by the programme team.]*"""

FOR_SCHOOLS = """LisheBora helps schools plan meals, order the right quantities and confirm deliveries, without paperwork piling up.

## What schools do on LisheBora
- **Plan each term:** enter enrolment, feeding days and food already in store. The platform calculates the food needed from the approved menu.
- **Check nutrition:** menus are checked for food-group variety before they are used.
- **Receive deliveries:** confirm what arrived on a phone, even without network. The record uploads when the phone is back online.
- **Raise issues:** report short deliveries, poor quality or late deliveries and follow them to resolution.
- **See the history:** every batch can be traced from the farmer group to the school kitchen.

## Who uses it at the school
- **School administrator (head teacher or deputy):** approves the term plan and confirms deliveries.
- **School meals officer:** prepares the plan and records stock and meals served.

Accounts for schools are created by the county or programme team. If your school is in a pilot area and does not have an
account yet, use the Contact page.

*[School onboarding schedule to be confirmed by the programme team.]*"""

FOR_COUNTIES = """LisheBora gives county teams one place to plan, buy, deliver and pay for school food, with controls built in.

## For county teams
- **Procurement officers:** combine school demand into procurement plans, publish notices, open sealed bids and manage contracts and purchase orders.
- **Finance officers:** keep spending within approved budget lines, match invoices to deliveries and track payments.
- **Nutrition officers:** set and approve menus and check food-group variety.
- **County administrators:** oversee approvals, exceptions and performance across the county.

## Controls you can rely on
- Approval workflows with deadlines and reminders
- Segregation of duties: the same person cannot, for example, verify and pay the same invoice
- Sealed bids, conflict-of-interest declarations and a complete audit trail
- Quality inspection and electronic proof of delivery
- Dashboards and exports for monitoring, evaluation and reporting

## For programme partners
Partners with a monitoring role can see programme dashboards and reports according to the access agreed with the programme.

*[Partnership and data-sharing arrangements to be confirmed by the programme team.]*"""


def seed_cms(db, admin):
    now = utcnow()
    blocks = {
        "hero": {"eyebrow": "STEP School Feeding Project",
                 "title": "Nutritious school meals, sourced from local farmers",
                 "subtitle": "LisheBora connects schools with qualified local producers, cooperatives and aggregators. "
                             "Procurement is open, fair and traceable, and suppliers are paid faster.",
                 "cta_label": "Register as a supplier"},
        # Figures must come from signed-off MEAL data — placeholders until then.
        "stats": {"show": False, "items": [{"value": "[x]", "label": "schools in the pilot"},
                                           {"value": "[x]", "label": "registered suppliers"},
                                           {"value": "[x]%", "label": "of food sourced locally"},
                                           {"value": "[x]%", "label": "of contract value to women-, youth- and PWD-led suppliers"}]},
        "backgrounds": {},
        # helpdesk contact details shown in the website footer and on the sign-in pages (filled in by the programme team)
        "site": {"phone": "", "sms_code": "", "whatsapp": "", "email": "", "address": "", "hours": "", "languages": "English · Kiswahili"},     # section/page background images, managed under Website content → Images & backgrounds
    }
    for key, data in blocks.items():
        if db.scalar(select(SiteBlock).where(SiteBlock.key == key)) is None:
            db.add(SiteBlock(key=key, data=data, published_data=data, status=ContentStatus.published,
                             published_at=now, published_by=admin.id))
    pages = {
        "about": ("About LisheBora", "LisheBora is being developed under the STEP School Feeding Project to strengthen "
                  "links between schools, local producers, aggregators and other suppliers.\n\n"
                  "## About AATF\nThe African Agricultural Technology Foundation (AATF) is an African-led, not-for-profit organisation, "
                  "founded in 2003, that works across Sub-Saharan Africa on agricultural technology transfer: product development, "
                  "seed systems and enabling-environment and policy programmes. Learn more at "
                  "[aatf-africa.org](https://www.aatf-africa.org).\n\n"
                  "*[Programme description to be supplied and approved by the programme team.]*"),
        "how-it-works": ("How it works", "## For suppliers\nRegister → get prequalified → receive alerts → submit sealed bids → "
                         "deliver → invoice and track payment.\n\n## For schools\nEnter enrolment, feeding days and menus → "
                         "confirm deliveries on your phone.\n\n## For counties\nApprove plans and budgets → run sourcing → "
                         "monitor delivery, payments and inclusion."),
        "for-suppliers": ("For farmers, cooperatives and suppliers", FOR_SUPPLIERS),
        "for-schools": ("For schools", FOR_SCHOOLS),
        "for-counties": ("For counties and partners", FOR_COUNTIES),
        "privacy": ("Privacy notice", "*[Privacy notice aligned with the Data Protection Act, 2019 — to be supplied by legal.]*"),
        "terms": ("Terms of use", "*[Terms of use — to be supplied by legal.]*"),
    }
    for slug, (title, body) in pages.items():
        if db.scalar(select(Page).where(Page.slug == slug)) is None:
            db.add(Page(slug=slug, title=title, body=body, status=ContentStatus.published, published_at=now,
                        published_by=admin.id))
    if db.scalar(select(NewsPost.id).limit(1)) is None:
        db.add(NewsPost(slug="supplier-registration-opens", title="Supplier registration opens for pilot counties",
                        category="Announcement",
                        summary="Farmers, cooperatives, aggregators and traders in the pilot counties can now register "
                                "and apply for prequalification.",
                        body="*[Full article to be written by the content editor.]*",
                        status=ContentStatus.published, published_at=now, published_by=admin.id))
    if db.scalar(select(FaqItem.id).limit(1)) is None:
        for i, (q, a) in enumerate([
            ("Who can register as a supplier?", "Individual farmers, farmer groups and cooperatives, aggregators, traders, "
                                                "processors and MSMEs operating in the pilot counties."),
            ("I don't have a smartphone. Can I still take part?", "Yes. Assisted registration is available through county "
                                                                  "officers, aggregators and the helpdesk. Alerts are also sent by SMS."),
            ("How are winning bids chosen?", "Against the criteria published in each notice, such as price, quality, "
                                             "capacity, local sourcing and inclusion."),
            ("How long do payments take?", "Payment starts once goods are accepted and a valid invoice is submitted. "
                                           "You can track status in your portal."),
        ]):
            db.add(FaqItem(question=q, answer=a, sort_order=i))
    if db.scalar(select(Resource.id).limit(1)) is None:
        db.add(Resource(title="Supplier registration checklist", description="Documents you need to register",
                        is_published=True))


def seed_demo(db, counties):
    """Optional demo notices so the public site isn't empty during development."""
    now = utcnow()
    for ref, title, days, cats in [("RFQ-2026-A-0042", "Maize flour: Kibwezi West schools (demo)", 5, ["refined_grains"]),
                                   ("RFQ-2026-A-0043", "Legumes: Makueni schools, Term 3 (demo)", 12, ["legumes"])]:
        if db.scalar(select(ProcurementEvent).where(ProcurementEvent.reference == ref)) is None:
            db.add(ProcurementEvent(reference=ref, title=title, method=ProcurementMethod.rfq, county_id=counties["MAKUENI"].id,
                                    eligibility="Prequalified: " + ", ".join(cats), categories=cats,
                                    closes_at=now + timedelta(days=days), status=EventStatus.open))


def seed_terms_and_rules(db):
    # Kenyan school calendar dates are placeholders — confirm with the programme (SRS §14).
    for y, n, s_, e_, days in [(2026, 1, date(2026, 1, 5), date(2026, 4, 2), 58), (2026, 2, date(2026, 4, 27), date(2026, 7, 31), 62),
                               (2026, 3, date(2026, 8, 24), date(2026, 10, 30), 45)]:
        if db.scalar(select(AcademicTerm).where(AcademicTerm.year == y, AcademicTerm.term_no == n)) is None:
            db.add(AcademicTerm(year=y, term_no=n, name=f"Term {n} {y}", starts_on=s_, ends_on=e_, feeding_days=days))
    if db.scalar(select(SystemSetting).where(SystemSetting.key == "nutrition.rules")) is None:
        from app.services.demand import DEFAULT_RULES
        db.add(SystemSetting(key="nutrition.rules", value=DEFAULT_RULES,
                             description="Menu diversity and demand validation rules — to be validated by nutrition authorities"))


DEMO_USERS = [
    ("meals.officer@demo.lishebora", "School Meals Officer (demo)", "school_meals_officer", "MAKUENI-SCH001"),
    ("school.admin@demo.lishebora", "School Administrator (demo)", "school_admin", "MAKUENI-SCH001"),
    # a meals coordinator assigned at county level can plan for every school in Makueni
    ("county.meals@demo.lishebora", "Makueni Meals Coordinator (demo)", "school_meals_officer", "MAKUENI"),
    ("nutrition@demo.lishebora", "Nutrition Officer (demo)", "nutrition_officer", "MAKUENI"),
    ("procurement@demo.lishebora", "County Procurement Officer (demo)", "county_procurement_officer", "MAKUENI"),
    ("finance@demo.lishebora", "County Finance Officer (demo)", "county_finance_officer", "MAKUENI"),
    ("county.admin@demo.lishebora", "County Administrator (demo)", "county_admin", "MAKUENI"),
    ("approver@demo.lishebora", "Approving Officer (demo)", "approving_officer", "MAKUENI"),
    ("evaluator1@demo.lishebora", "Evaluator One (demo)", "evaluation_committee_member", "MAKUENI"),
    ("evaluator2@demo.lishebora", "Evaluator Two (demo)", "evaluation_committee_member", "MAKUENI"),
    ("administrator@demo.lishebora", "Administrator (demo)", "system_admin", None),   # signs in at /admin/sign-in
    ("editor@demo.lishebora", "Content Editor (demo)", "content_editor", None),
    ("auditor@demo.lishebora", "Auditor (demo)", "auditor", None),
]


def seed_demo_planning(db, counties):
    """Illustrative data for development ONLY — prices and budgets are not programme figures."""
    # KES per unit. Illustrative placeholders, NOT market or programme prices: replace from county market surveys.
    prices = {"MAIZE-FLOUR": 55, "RICE-WHITE": 160, "GITHERI": 100, "BEANS": 130, "GREEN-GRAMS": 150, "SUKUMA-WIKI": 60,
              "AMARANTH": 60, "CABBAGE": 40, "BANANAS": 70, "COOKING-OIL": 300, "SALT": 30}
    # Demo quality thresholds so inspection can be tried; the real specification comes from KEBS standards / the programme.
    specs = {"MAIZE-FLOUR": {"max_moisture_pct": 13.5}, "BEANS": {"max_moisture_pct": 14}, "GREEN-GRAMS": {"max_moisture_pct": 14}}
    for code, pr in prices.items():
        c = db.scalar(select(Commodity).where(Commodity.code == code))
        if c and c.reference_price is None:
            c.reference_price = pr
        if c and code in specs and not c.quality_spec:
            c.quality_spec = specs[code]
            c.notes = "Demo quality threshold (placeholder)."
    if db.scalar(select(Menu).where(Menu.name == "Standard 5-day menu (demo)")) is None:
        m = Menu(name="Standard 5-day menu (demo)", description="Illustrative only — portions to be set by nutrition officers.",
                 status=MenuStatus.approved, approved_at=utcnow())
        for i, (lbl, dish, comps) in enumerate([
            ("Mon", "Ugali, beans and sukuma wiki", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("SUKUMA-WIKI", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
            ("Tue", "Rice and green grams with cabbage", [("RICE-WHITE", 120), ("GREEN-GRAMS", 40), ("CABBAGE", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
            ("Wed", "Ugali, beans and amaranth", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("AMARANTH", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
            ("Thu", "Githeri with cabbage", [("GITHERI", 190), ("CABBAGE", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
            ("Fri", "Ugali, beans, sukuma wiki and banana", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("SUKUMA-WIKI", 60), ("BANANAS", 80),
                                                          ("COOKING-OIL", 10), ("SALT", 2)])], 1):
            m.days.append(MenuDay(day_index=i, label=lbl, dish=dish, components=[{"commodity": c, "portion_g": g} for c, g in comps]))
        db.add(m)
    fs = db.scalar(select(FundingSource).where(FundingSource.code == "DEMO-GRANT"))
    if fs is None:
        fs = FundingSource(code="DEMO-GRANT", name="Programme grant (demo)", kind="grant")
        db.add(fs)
        db.flush()
    t3 = db.scalar(select(AcademicTerm).where(AcademicTerm.year == 2026, AcademicTerm.term_no == 3))
    if db.scalar(select(BudgetLine).where(BudgetLine.code == "DEMO-A-T3")) is None:
        db.add(BudgetLine(code="DEMO-A-T3", name="Makueni County · school feeding · Term 3 2026 (demo)", funding_source_id=fs.id,
                          org_id=counties["MAKUENI"].id, term_id=t3.id, period_start=t3.starts_on, period_end=t3.ends_on,
                          approved_amount=Decimal("2500000")))
    created = []
    for email, name, role_key, org_code in DEMO_USERS:
        if db.scalar(select(User).where(User.email == email)) is None:
            u = User(full_name=name, email=email, password_hash=hash_password(settings.seed_demo_password), status=UserStatus.active)
            db.add(u)
            db.flush()
            oid = db.scalar(select(Organization.id).where(Organization.code == org_code)) if org_code else None
            db.add(UserRole(user_id=u.id, role_id=db.scalar(select(Role.id).where(Role.key == role_key)), org_id=oid))
            created.append(email)
    created += seed_demo_suppliers(db, counties)
    created += seed_demo_fulfilment(db, counties)
    if created:
        print("Demo users (password from SEED_DEMO_PASSWORD):\n  " + "\n  ".join(created))


def seed_demo_suppliers(db, counties):
    """Two prequalified demo suppliers with verified placeholder documents, so bidding can be tried end to end."""
    import hashlib
    from pathlib import Path
    from app.models import DocumentStatus, Supplier, SupplierDocument, SupplierStatus, SupplierType
    pdf = b"%PDF-1.4\n% LisheBora demo placeholder document\n"
    out = []
    for email, phone, name, stype, lead, comms, cats in [
        ("supplier1@demo.lishebora", "+254700000101", "Umoja Farmers Cooperative (demo)", SupplierType.cooperative, "women",
         ["MAIZE-FLOUR", "SORGHUM", "BEANS", "GREEN-GRAMS", "COWPEAS", "SUKUMA-WIKI", "CABBAGE", "BANANAS", "MANGOES"],
         ["whole_grains", "refined_grains", "legumes", "green_leafy_vegetables", "other_vegetables", "fruits"]),
        ("supplier2@demo.lishebora", "+254700000102", "Tumaini Grain Traders (demo)", SupplierType.trader, "none",
         ["MAIZE-FLOUR", "RICE-WHITE", "GITHERI", "BEANS", "GREEN-GRAMS", "COOKING-OIL", "SALT"],
         ["refined_grains", "blended_grain_foods", "legumes", "cooking_oil", "salt"]),
    ]:
        if db.scalar(select(User).where(User.email == email)):
            continue
        o = Organization(type=OrgType.supplier, name=name, code=f"SUP-DEMO-{phone[-3:]}", parent_id=counties["MAKUENI"].id)
        db.add(o)
        db.flush()
        u = User(full_name=name.replace(" (demo)", " contact"), email=email, phone=phone,
                 password_hash=hash_password(settings.seed_demo_password), status=UserStatus.active)
        db.add(u)
        db.flush()
        role = "farmer_group" if stype == SupplierType.cooperative else "supplier"
        db.add(UserRole(user_id=u.id, role_id=db.scalar(select(Role.id).where(Role.key == role)), org_id=o.id))
        sup = Supplier(organization_id=o.id, county_id=counties["MAKUENI"].id, supplier_type=stype, legal_name=name, phone=phone,
                       email=email, commodities=comms, approved_categories=cats,
                       inclusion_claim={"leadership": lead}, inclusion_consent=True, inclusion_verified=lead != "none",
                       status=SupplierStatus.prequalified, created_by=u.id)
        db.add(sup)
        db.flush()
        for t in ("registration", "bank"):
            key = f"suppliers/{sup.id}/demo-{t}.pdf"
            path = Path(settings.storage_dir) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pdf)
            db.add(SupplierDocument(supplier_id=sup.id, doc_type=t, file_key=key, file_name=f"demo-{t}.pdf",
                                    content_type="application/pdf", size_bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest(),
                                    status=DocumentStatus.verified))
        out.append(email)
    return out


DEMO_P4_USERS = [
    ("aggregator@demo.lishebora", "+254700000201", "Hub Aggregator (demo)", "aggregator", "SUP-DEMO-101"),
    ("inspector@demo.lishebora", "+254700000202", "Quality Inspector (demo)", "quality_inspector", "MAKUENI"),
    ("warehouse@demo.lishebora", "+254700000203", "Warehouse Officer (demo)", "warehouse_officer", "WH-DEMO-A1"),
    ("warehouse.supervisor@demo.lishebora", "+254700000204", "Warehouse Supervisor (demo)", "warehouse_officer", "MAKUENI"),
    ("logistics@demo.lishebora", "+254700000205", "Logistics Officer (demo)", "logistics_officer", "MAKUENI"),
    ("driver@demo.lishebora", "+254700000206", "Peter Driver (demo)", "driver", "MAKUENI"),
    ("school2.admin@demo.lishebora", "+254700000207", "Muatini School Administrator (demo)", "school_admin", "MAKUENI-SCH002"),
    ("risk@demo.lishebora", "+254700000208", "Risk & Compliance Officer (demo)", "risk_compliance_officer", "MAKUENI"),
    ("accounts@demo.lishebora", "+254700000301", "Accounts Officer (demo)", "finance_officer", "MAKUENI"),
    ("payments@demo.lishebora", "+254700000302", "Payments Officer (demo)", "finance_officer", "MAKUENI"),
    ("meal@demo.lishebora", "+254700000303", "Programme MEAL Officer (demo)", "programme_meal_officer", None),
]


def seed_demo_fulfilment(db, counties):
    """Phase 4 demo: an aggregation hub under the demo cooperative, a county store, field users,
    and one acknowledged purchase order (maize flour + beans for Kalulini and Muatini schools) ready to be fulfilled. Illustrative only."""
    from app.models import (Contract, ContractKind, ContractLine, EventStatus, POLine, POStatus, ProcurementLot,
                            PurchaseOrder, Supplier)
    sup_org = db.scalar(select(Organization).where(Organization.code == "SUP-DEMO-101"))
    if sup_org is None:
        return []
    org(db, OrgType.aggregation_centre, "HUB-DEMO-101", "Umoja Aggregation Hub (demo)", sup_org)
    org(db, OrgType.warehouse, "WH-DEMO-A1", "Makueni County Food Store (demo)", counties["MAKUENI"])
    out = []
    for email, phone, name, role_key, org_code in DEMO_P4_USERS:
        if db.scalar(select(User).where(User.email == email)):
            continue
        u = User(full_name=name, email=email, phone=phone, password_hash=hash_password(settings.seed_demo_password),
                 status=UserStatus.active)
        db.add(u)
        db.flush()
        db.add(UserRole(user_id=u.id, role_id=db.scalar(select(Role.id).where(Role.key == role_key)),
                        org_id=db.scalar(select(Organization.id).where(Organization.code == org_code)) if org_code else None))
        out.append(email)
    if db.scalar(select(PurchaseOrder).where(PurchaseOrder.reference == "PO-DEMO-0001")) is None:
        sup = db.scalar(select(Supplier).where(Supplier.organization_id == sup_org.id))
        s1 = db.scalar(select(Organization).where(Organization.code == "MAKUENI-SCH001"))
        s2 = db.scalar(select(Organization).where(Organization.code == "MAKUENI-SCH002"))
        now = utcnow()
        ev = ProcurementEvent(reference="RFQ-DEMO-P4", title="Demo award for fulfilment testing", method=ProcurementMethod.rfq,
                              county_id=counties["MAKUENI"].id, closes_at=now - timedelta(days=10), status=EventStatus.awarded,
                              is_public=False, awarded_to=sup.legal_name, awarded_at=now - timedelta(days=5))
        spec = [("MAIZE-FLOUR", "Maize flour", "refined_grains", 700, 500, Decimal("55")), ("BEANS", "Beans", "legumes", 180, 120, Decimal("130"))]
        for i, (code, nm, cat, q1, q2, _pr) in enumerate(spec, 1):
            ev.lots.append(ProcurementLot(lot_no=i, name=nm, commodity_code=code, category=cat, quantity=Decimal(q1 + q2),
                                          schools=[{"school_id": str(s1.id), "name": s1.name, "qty": str(q1)},
                                                   {"school_id": str(s2.id), "name": s2.name, "qty": str(q2)}]))
        db.add(ev)
        db.flush()
        total = sum(((Decimal(q1 + q2) * pr) for _, _, _, q1, q2, pr in spec), Decimal(0))
        con = Contract(reference="CON-DEMO-0001", event_id=ev.id, supplier_id=sup.id, county_id=counties["MAKUENI"].id,
                       kind=ContractKind.purchase, value=total, starts_on=date.today() - timedelta(days=5),
                       ends_on=date.today() + timedelta(days=90), terms="Demo contract (illustrative).")
        po = PurchaseOrder(reference="PO-DEMO-0001", supplier_id=sup.id, county_id=counties["MAKUENI"].id, status=POStatus.acknowledged,
                           total=total, delivery_window="Within 2 weeks (demo)", issued_at=now - timedelta(days=4),
                           acknowledged_at=now - timedelta(days=3))
        for lot, (code, _, _, q1, q2, pr) in zip(ev.lots, spec):
            cl = ContractLine(lot_id=lot.id, commodity_code=code, quantity=lot.quantity, unit_price=pr, quantity_ordered=lot.quantity)
            con.lines.append(cl)
        db.add(con)
        db.flush()
        po.contract_id = con.id
        for lot, cl, (code, _, _, q1, q2, pr) in zip(ev.lots, con.lines, spec):
            po.lines.append(POLine(contract_line_id=cl.id, commodity_code=code, quantity=lot.quantity, unit_price=pr, schools=lot.schools))
        db.add(po)
        db.flush()
    # Phase 6: GPS for the two fictional demo sites only (approximate: near Kibwezi and Wote town). The real schools get
    # no invented coordinates: school admins capture them on site, or they come in through the school CSV import.
    # Verified M-Pesa details for the demo cooperative.
    for code, lat, lng in (("HUB-DEMO-101", -2.4170, 37.9650), ("WH-DEMO-A1", -1.7830, 37.6290)):
        o = db.scalar(select(Organization).where(Organization.code == code))
        if o is not None and not (o.meta or {}).get("gps"):
            o.meta = {**(o.meta or {}), "gps": {"lat": lat, "lng": lng, "demo": True}}
    sup1 = db.scalar(select(Supplier).where(Supplier.organization_id == sup_org.id))
    if sup1 is not None and not sup1.payment_details:
        sup1.payment_details = {"method": "mpesa", "account_name": "Umoja Farmers Cooperative", "mpesa_phone": "0700000101",
                                "verified_by": "seed (demo)", "verified_at": utcnow().isoformat(), "verification_note": "Demo data"}
    # Phase 5: fund the demo contract from the demo budget line so invoices and payments move the budget
    from app.models import Commitment
    con = db.scalar(select(Contract).where(Contract.reference == "CON-DEMO-0001"))
    bl = db.scalar(select(BudgetLine).where(BudgetLine.code == "DEMO-A-T3"))
    if con and bl and con.budget_line_id is None:
        con.budget_line_id = bl.id
        if db.scalar(select(Commitment.id).where(Commitment.source_entity == "contract", Commitment.source_id == con.id)) is None:
            db.add(Commitment(budget_line_id=bl.id, amount=con.value, source_entity="contract", source_id=con.id, source_ref=con.reference))
        db.flush()
    return out


def main(demo: bool = False):
    db = SessionLocal()
    try:
        upsert_permissions_and_roles(db)
        counties = seed_geography(db, demo)
        admin = seed_admin(db)
        seed_commodities(db)
        seed_cms(db, admin)
        seed_terms_and_rules(db)
        db.flush()
        if demo:
            seed_demo_planning(db, counties)
        db.commit()
        print(f"Seed complete: {len(ROLES)} roles, {len(all_permission_codes())} permissions.")
    finally:
        db.close()


if __name__ == "__main__":
    main(demo="--demo" in sys.argv)
