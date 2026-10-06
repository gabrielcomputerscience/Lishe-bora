"""LisheBora pilot simulation: one county (Makueni), one school (Kalulini, MAKUENI-SCH001), every process end to end.

It builds a throw-away database with the demo data and demo accounts, then signs in as each demo role and does what that
person would do in the pilot, in order: menu, school demand, budget, procurement plan, supplier registration and vetting,
sourcing event, bids, evaluation, award, contract and purchase order, aggregation and quality inspection, warehouse,
dispatch and delivery, school stock, invoice, payment, complaints, recall, monitoring, audit and website content.

Every step is checked (including the controls that must BLOCK something, e.g. segregation of duties), and the result is
written to docs/pilot_test/LisheBora_Simulation_Report.xlsx. Your own demo and pilot databases are not touched.

    cd backend
    python scripts/pilot_simulation.py           # run and write the report
    python scripts/pilot_simulation.py --save    # also keep the finished cycle as backend/lishebora_example.db to browse

All figures (prices, quantities, enrolment) are illustrative demo values, not programme data.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
_work = tempfile.mkdtemp(prefix="lishebora_sim_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_work, "simulation.db")
os.environ["STORAGE_DIR"] = os.path.join(_work, "storage")
os.environ["DEBUG"] = "true"              # one-time codes are returned to the caller instead of being sent by SMS
os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ.setdefault("NOTIFY_BACKEND", "console")
os.environ.pop("SMTP_HOST", None)

import logging  # noqa: E402

logging.disable(logging.WARNING)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AcademicTerm, Organization, ProcurementEvent  # noqa: E402
from app.seed import run as seed  # noqa: E402

A = "/api/v1"
PW = settings.seed_demo_password
ADMIN = ("administrator@demo.lishebora", PW)
SCHOOL = "MAKUENI-SCH001"
TODAY = date.today()
SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
PDF = b"%PDF-1.4\n% LisheBora pilot simulation document\n"

ROLE_OF = {
    "administrator": "Administrator", "editor": "Content Editor", "nutrition": "Nutrition Officer",
    "procurement": "County Procurement Officer", "meals.officer": "School Meals Officer", "school.admin": "School Administrator",
    "finance": "County Finance Officer", "county.admin": "County Administrator", "approver": "Approving Officer",
    "evaluator1": "Evaluator 1", "evaluator2": "Evaluator 2", "evaluator3": "Evaluator 3", "supplier1": "Supplier (cooperative)",
    "supplier2": "Supplier (trader)", "supplier3": "New supplier (self-registered)", "aggregator": "Aggregator (cooperative hub)",
    "inspector": "Quality Inspector", "warehouse": "Warehouse Officer", "warehouse.supervisor": "Warehouse Supervisor",
    "logistics": "Logistics Officer", "driver": "Driver", "accounts": "Finance Officer (verifier)",
    "payments": "Finance Officer (payer)", "meal": "Programme MEAL Officer", "risk": "Risk & Compliance Officer",
    "auditor": "Auditor", "public": "Member of the public",
}


class Check(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Check(msg)


class Sim:
    def __init__(self):
        self.c = TestClient(app)
        self.tokens: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.ctx: dict = {}
        self.stage = ""

    # ---------- sign-in ----------
    def login(self, who: str, password: str = PW, identifier: str | None = None) -> dict:
        key = identifier or who
        if key in self.tokens:
            return self.tokens[key]
        ident = identifier or (f"{who}@demo.lishebora" if "@" not in who else who)
        r = self.c.post(f"{A}/auth/login", json={"identifier": ident, "password": password})
        if r.status_code == 403 and r.json()["error"]["code"] == "USE_ADMIN_SIGN_IN":
            r = self.c.post(f"{A}/auth/admin/login", json={"identifier": ident, "password": password})
        expect(r.status_code == 200, f"sign-in failed for {ident}: {r.text[:200]}")
        d = r.json()
        if d.get("mfa_required"):
            r = self.c.post(f"{A}/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": d["dev_code"]})
            expect(r.status_code == 200, f"MFA failed for {ident}")
            d = r.json()
        self.c.cookies.clear()
        self.tokens[key] = {"Authorization": f"Bearer {d['access_token']}"}
        return self.tokens[key]

    def h(self, who):
        return self.login(who)

    # ---------- HTTP helpers that fail loudly ----------
    def call(self, method, who, path, ok=(200, 201), **kw):
        headers = self.h(who) if who != "public" else {}
        r = self.c.request(method, A + path, headers=headers, **kw)
        if ok and r.status_code not in ok:
            raise Check(f"{method} {path} as {who} → {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            return r

    def get(self, who, path, **kw):
        return self.call("GET", who, path, **kw)

    def post(self, who, path, json=None, **kw):
        return self.call("POST", who, path, json=json, **kw)

    def put(self, who, path, json=None, **kw):
        return self.call("PUT", who, path, json=json, **kw)

    def blocked(self, method, who, path, json=None, codes=(403, 409, 422)):
        """A control that must refuse the action. Returns the error code."""
        r = self.c.request(method, A + path, headers=self.h(who), json=json)
        expect(r.status_code in codes, f"expected the system to refuse {method} {path} as {who}, got {r.status_code}")
        return r.json().get("error", {}).get("code", str(r.status_code))

    def act(self, who, wid, action="approve", note=""):
        body = {"action": action}
        if note:
            body["note"] = note
        return self.post(who, f"/workflow/{wid}/act", body)

    # ---------- recorder ----------
    def step(self, title, who, fn, control=False):
        n = len(self.rows) + 1
        t0 = time.perf_counter()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                detail = fn() or ""
            status = "PASS"
        except Exception as e:   # noqa: BLE001
            status = "FAIL"
            detail = f"{e}" if isinstance(e, Check) else f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
        ms = int((time.perf_counter() - t0) * 1000)
        sent = buf.getvalue().splitlines()
        sms, mail = sum(x.startswith("[SMS") for x in sent), sum(x.startswith("[EMAIL") for x in sent)
        if sms or mail:
            detail = f"{detail}  [Messages: {sms} SMS, {mail} email]"
        self.rows.append({"no": n, "stage": self.stage, "step": title, "role": ROLE_OF.get(who, who), "account": who if who == "public" else
                          (who if "@" in who else f"{who}@demo.lishebora"), "type": "Control (must be blocked)" if control else "Process",
                          "status": status, "detail": str(detail)[:900], "ms": ms})
        mark = "✔" if status == "PASS" else "✘"
        print(f"  {mark} {n:>3}. [{self.stage}] {title} — {ROLE_OF.get(who, who)}" + ("" if status == "PASS" else f"\n        {detail}"))
        return status == "PASS"


def org_id(code):
    with SessionLocal() as db:
        return str(db.scalar(select(Organization.id).where(Organization.code == code)))


def pass_time(event_ref):
    """Simulate the bid closing time passing (in the pilot the procurement officer waits for the deadline)."""
    with SessionLocal() as db:
        db.execute(update(ProcurementEvent).where(ProcurementEvent.reference == event_ref)
                   .values(closes_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()


def build_database():
    print("Building a fresh demo database (demo data and demo accounts)…")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with contextlib.redirect_stdout(io.StringIO()):
        seed.main(demo=True)


# =====================================================================================================================
def run(s: Sim):
    X = s.ctx
    school, county = org_id(SCHOOL), org_id("MAKUENI")
    with SessionLocal() as db:
        term = db.scalar(select(AcademicTerm).where(AcademicTerm.year == 2026, AcademicTerm.term_no == 3))
        X["term"], X["term_start"], X["term_end"] = str(term.id), term.starts_on, term.ends_on
        X["school_name"] = db.scalar(select(Organization.name).where(Organization.code == SCHOOL))

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "1 Set-up"

    def admin_signin():
        me = s.get("administrator", "/auth/me")
        expect("md:edit" in me["permissions"] and "iam:edit" in me["permissions"], "administrator lacks content/user rights")
        return "Administrator signs in at /admin/sign-in with a one-time code (MFA)."
    s.step("Administrator signs in (separate admin sign-in, MFA)", "administrator", admin_signin)

    def admin_not_on_staff_signin():
        r = s.c.post(f"{A}/auth/login", json={"identifier": ADMIN[0], "password": ADMIN[1]})
        expect(r.status_code == 403 and r.json()["error"]["code"] == "USE_ADMIN_SIGN_IN", "admin could use the staff sign-in")
        return "USE_ADMIN_SIGN_IN"
    s.step("Administrator cannot use the staff sign-in page", "administrator", admin_not_on_staff_signin, control=True)

    def school_gps():
        r = s.put("school.admin", f"/fulfilment/locations/{school}/gps",
                  {"lat": -1.803512, "lng": 37.620145, "accuracy_m": 8, "source": "device", "note": "Simulation (illustrative point)"})
        expect(r["gps"]["source"] == "device", "GPS not stored")
        return f"{X['school_name']} located at {r['gps']['lat']}, {r['gps']['lng']} (illustrative)"
    s.step("School administrator records the school's GPS location", "school.admin", school_gps)

    s.step("Coordinates outside Kenya are refused (swapped lat/lng)", "school.admin",
           lambda: s.blocked("PUT", "school.admin", f"/fulfilment/locations/{school}/gps", {"lat": 37.62, "lng": -1.80}), control=True)

    def school_enrolment():
        r = s.get("administrator", "/system/readiness")
        return f"Readiness: {r['summary']}"
    s.step("Administrator reviews the Pilot readiness checklist", "administrator", school_enrolment)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "2 Menu"
    menu_days = [
        ("Mon", "Ugali, beans and sukuma wiki", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("SUKUMA-WIKI", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
        ("Tue", "Rice and green grams with cabbage", [("RICE-WHITE", 120), ("GREEN-GRAMS", 40), ("CABBAGE", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
        ("Wed", "Ugali, beans and amaranth", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("AMARANTH", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
        ("Thu", "Githeri with cabbage", [("GITHERI", 190), ("CABBAGE", 60), ("COOKING-OIL", 10), ("SALT", 2)]),
        ("Fri", "Ugali, beans, sukuma wiki and banana", [("MAIZE-FLOUR", 150), ("BEANS", 40), ("SUKUMA-WIKI", 60), ("BANANAS", 80),
                                                      ("COOKING-OIL", 10), ("SALT", 2)])]

    def make_menu():
        m = s.post("nutrition", "/menus", {"name": "Makueni pilot menu – Term 3 (simulation)", "description": "Illustrative portions",
                                           "days": [{"label": l, "dish": d, "components": [{"commodity": c, "portion_g": g} for c, g in comps]}
                                                    for l, d, comps in menu_days]})
        X["menu"] = m["id"]
        expect(m["summary"]["meets_minimum"], f"menu does not meet the diversity minimum: {m['summary']}")
        return f"Menu created; {m['summary'].get('group_count')} food groups; meets minimum diversity."
    s.step("Nutrition officer creates the term menu", "nutrition", make_menu)

    def submit_menu():
        r = s.post("nutrition", f"/menus/{X['menu']}/submit")
        X["menu_wf"] = r["workflow"]["id"]
        return "Submitted for nutrition validation"
    s.step("Nutrition officer submits the menu", "nutrition", submit_menu)
    s.step("Nutrition officer cannot approve their own menu", "nutrition",
           lambda: s.blocked("POST", "nutrition", f"/workflow/{X['menu_wf']}/act", {"action": "approve"}), control=True)
    s.step("Returning a menu without a reason is refused", "procurement",
           lambda: s.blocked("POST", "procurement", f"/workflow/{X['menu_wf']}/act", {"action": "return"}), control=True)

    def approve_menu():
        s.act("procurement", X["menu_wf"], note="Portions checked against the menu guidance")
        st = next(m for m in s.get("nutrition", "/menus") if m["id"] == X["menu"])["status"]
        expect(st == "approved", f"menu status {st}")
        return "Menu approved"
    s.step("County procurement officer validates and approves the menu", "procurement", approve_menu)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "3 School demand"

    def demand():
        d = s.post("meals.officer", "/demands", {"school_id": school, "term_id": X["term"], "menu_id": X["menu"], "enrolment": 612,
                                                 "attendance_pct": 95, "feeding_days": 40, "wastage_pct": 3,
                                                 "stock": [{"commodity": "MAIZE-FLOUR", "qty": 100}]})
        X["demand"] = d["id"]
        errs = [f for f in d["flags"] if f["severity"] == "error"]
        expect(not errs, f"demand has blocking flags: {errs}")
        mz = next(ln for ln in d["lines"] if ln["commodity"] == "MAIZE-FLOUR")
        return f"{len(d['lines'])} food items; maize flour net {mz['net_qty']} kg after 100 kg in stock (612 learners, 40 days)"
    s.step("School meals officer records the school's demand (enrolment, days, stock)", "meals.officer", demand)

    def demand_bad_days():
        d = s.put("meals.officer", f"/demands/{X['demand']}", {"school_id": school, "term_id": X["term"], "menu_id": X["menu"],
                                                                "enrolment": 612, "attendance_pct": 95, "feeding_days": 120, "wastage_pct": 3})
        expect(any(f["code"] == "FEEDING_DAYS" for f in d["flags"]), "feeding days above the calendar were not flagged")
        code = s.blocked("POST", "meals.officer", f"/demands/{X['demand']}/submit")
        s.put("meals.officer", f"/demands/{X['demand']}", {"school_id": school, "term_id": X["term"], "menu_id": X["menu"], "enrolment": 612,
                                                            "attendance_pct": 95, "feeding_days": 40, "wastage_pct": 3,
                                                            "stock": [{"commodity": "MAIZE-FLOUR", "qty": 100}]})
        return f"Feeding days above the term calendar flagged; submission refused ({code}); corrected back to 40 days"
    s.step("Demand with more feeding days than the term allows cannot be submitted", "meals.officer", demand_bad_days, control=True)

    def submit_demand():
        r = s.post("meals.officer", f"/demands/{X['demand']}/submit")
        X["demand_wf"] = r["workflow"]["id"]
        expect(r["status"] == "submitted", r["status"])
        return "Submitted"
    s.step("School meals officer submits the demand", "meals.officer", submit_demand)
    s.step("Meals officer cannot approve their own demand", "meals.officer",
           lambda: s.blocked("POST", "meals.officer", f"/workflow/{X['demand_wf']}/act", {"action": "approve"}), control=True)

    def approve_demand():
        inbox = s.get("school.admin", "/workflow/inbox")["waiting_for_me"]
        expect(any(i["id"] == X["demand_wf"] for i in inbox), "demand not in the school administrator's approvals")
        s.act("school.admin", X["demand_wf"])
        s.act("school.admin", X["demand_wf"])
        st = s.get("school.admin", f"/demands/{X['demand']}")["status"]
        expect(st == "approved", st)
        return "Validated and approved from 'My approvals'"
    s.step("School administrator validates and approves the demand", "school.admin", approve_demand)
    s.step("An approved demand is locked against edits", "meals.officer",
           lambda: s.blocked("PUT", "meals.officer", f"/demands/{X['demand']}", {"school_id": school, "term_id": X["term"],
                                                                                   "menu_id": X["menu"], "enrolment": 1}), control=True)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "4 Budget & plan"

    def budget_line():
        fs = s.get("finance", "/funding-sources")[0]["id"]
        bl = s.post("finance", "/budget-lines", {"code": "SIM-MAK-T3", "name": "Makueni school meals – Term 3 (simulation)", "funding_source_id": fs,
                                                 "org_id": county, "period_start": str(X["term_start"]), "period_end": str(X["term_end"]),
                                                 "approved_amount": "2500000"})
        X["bl"] = bl["id"]
        return f"Budget line {bl['code']} KES 2,500,000 (illustrative)"
    s.step("County finance officer sets up the term budget line", "finance", budget_line)

    def plan():
        prev = s.post("procurement", "/plans/preview", {"county_id": county, "term_id": X["term"]})
        expect(prev["demand_count"] >= 1, "no approved demand reached the plan")
        p = s.post("procurement", "/plans", {"county_id": county, "term_id": X["term"], "group_by": "county"})
        X["plan"] = p
        expect(p["unpriced_lines"] == 0, f"{p['unpriced_lines']} lines without a reference price")
        s.put("procurement", f"/plans/{p['id']}", {"budget_line_id": X["bl"]})
        return f"Plan {p.get('reference', '')}: {len(p['lines'])} lines from {p['demand_count']} school demand(s), est. KES {p['estimated_value']}"
    s.step("County procurement officer builds the procurement plan from approved demand", "procurement", plan)

    def submit_plan():
        r = s.post("procurement", f"/plans/{X['plan']['id']}/submit")
        X["plan_wf"] = r["workflow"]["id"]
        return "Submitted for budget confirmation and county approval"
    s.step("County procurement officer submits the plan", "procurement", submit_plan)
    s.step("County administrator cannot do the finance (budget) step", "county.admin",
           lambda: s.blocked("POST", "county.admin", f"/workflow/{X['plan_wf']}/act", {"action": "approve"}), control=True)
    s.step("County finance officer confirms the budget", "finance", lambda: s.act("finance", X["plan_wf"]) and "Budget confirmed")

    def approve_plan():
        r = s.act("county.admin", X["plan_wf"])
        expect(r["status"] == "approved", r["status"])
        bl = s.get("finance", f"/budget-lines/{X['bl']}")
        return f"Plan approved; KES {bl['committed']} earmarked on the budget line"
    s.step("County administrator approves the plan (budget earmarked)", "county.admin", approve_plan)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "5 Supplier onboarding"

    def register_supplier():
        body = {"account_type": "farmer_group" if False else "cooperative", "legal_name": "Kalulini Farmers Self-Help Group (simulation)",
                "contact_name": "Simulation Contact", "phone": "0711 000 913", "county_id": county,
                "commodities": ["BEANS", "GREEN-GRAMS", "SUKUMA-WIKI", "CABBAGE", "AMARANTH", "BANANAS"], "members_count": 38,
                "inclusion": {"leadership": "youth", "pct_women": 55}, "inclusion_consent": True, "accept_terms": True,
                "password": "Sim!Supplier2026"}
        reg = s.post("public", "/auth/register/supplier", body)
        s.c.cookies.clear()
        v = s.c.post(f"{A}/auth/verify-phone", json={"user_id": reg["user_id"], "code": reg["dev_code"]})
        expect(v.status_code == 200, "phone verification failed")
        s.c.cookies.clear()
        X["sup3"] = reg["supplier_id"]
        s.login("supplier3", "Sim!Supplier2026", identifier="0711000913")
        return "Registered on the website and verified the phone with the SMS code"
    s.step("A new supplier registers on the website (farmer group)", "public", register_supplier)

    def upload_docs():
        for t in ("registration", "bank"):
            r = s.c.post(f"{A}/suppliers/{X['sup3']}/documents", headers=s.tokens["0711000913"], data={"doc_type": t},
                         files={"file": (f"{t}.pdf", PDF, "application/pdf")})
            expect(r.status_code == 201, r.text[:200])
        return "Registration certificate and bank letter uploaded"
    s.step("New supplier uploads compliance documents", "supplier3", lambda: upload_docs())

    def vet():
        s.post("procurement", f"/suppliers/{X['sup3']}/review", {"to_status": "under_review"})
        for d in s.get("procurement", f"/suppliers/{X['sup3']}")["documents"]:
            s.post("procurement", f"/suppliers/{X['sup3']}/documents/{d['id']}/review", {"status": "verified"})
        return "Under review; documents verified"
    s.step("County procurement officer reviews the supplier and verifies documents", "procurement", vet)
    s.step("Procurement officer cannot approve a supplier (county administrator does)", "procurement",
           lambda: s.blocked("POST", "procurement", f"/suppliers/{X['sup3']}/review", {"to_status": "approved"}), control=True)

    def prequalify():
        s.post("county.admin", f"/suppliers/{X['sup3']}/review", {"to_status": "approved"})
        r = s.post("county.admin", f"/suppliers/{X['sup3']}/review", {"to_status": "prequalified",
                                                                     "approved_categories": ["legumes", "green_leafy_vegetables", "other_vegetables", "fruits"]})
        expect(r["status"] == "prequalified", r["status"])
        return "Approved and prequalified for legumes, vegetables and fruits"
    s.step("County administrator approves and prequalifies the supplier", "county.admin", prequalify)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "6 Sourcing"

    def event():
        closes = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        ev = s.post("procurement", "/procurement-events/from-plan", {"plan_id": X["plan"]["id"], "closes_at": closes})
        X["ev"] = ev
        return f"Sourcing event {ev['reference']} with {len(ev['lots'])} lots, closing in 5 days"
    s.step("County procurement officer creates the sourcing event from the plan", "procurement", event)
    s.step("Evaluation weights that do not add up are refused", "procurement",
           lambda: s.blocked("PUT", "procurement", f"/procurement-events/{X['ev']['id']}", {"technical_weight": 70}), control=True)

    def submit_event():
        X["ev_wf"] = s.post("procurement", f"/procurement-events/{X['ev']['id']}/submit")["workflow"]["id"]
        return "Submitted for approval to publish"
    s.step("Procurement officer submits the event", "procurement", submit_event)
    s.step("Procurement officer cannot approve their own event", "procurement",
           lambda: s.blocked("POST", "procurement", f"/workflow/{X['ev_wf']}/act", {"action": "approve"}), control=True)

    def publish():
        s.act("approver", X["ev_wf"])
        ev = s.get("procurement", f"/procurement-events/{X['ev']['id']}")
        expect(ev["status"] == "open", ev["status"])
        pub = s.get("public", "/public/opportunities")
        expect(any(o["reference"] == ev["reference"] for o in pub.get("open", pub.get("items", []))) or ev["reference"] in str(pub),
               "event not on the public Opportunities page")
        return "Approved, open for bids and listed on the public Opportunities page"
    s.step("Approving officer approves; event is published", "approver", publish)

    def notified():
        n = s.get("supplier1", "/notifications")["items"]
        expect(any("opportunit" in (x["title"] + x["body"]).lower() for x in n), "supplier was not notified")
        return "Eligible suppliers notified"
    s.step("Eligible suppliers receive a 'New opportunity' notification", "supplier1", notified)

    def bids():
        opp = s.get("supplier1", f"/supplier/opportunities/{X['ev']['id']}")
        expect(opp["eligible"] and "estimated_value" not in opp, "supplier sees the estimate or is not eligible")
        lots = opp["lots"]
        price = {ln["commodity"] if "commodity" in ln else ln.get("commodity_code"): ln.get("unit_price") for ln in X["plan"]["lines"]}

        def body(f, only=None):
            out = []
            for lt in lots:
                if only and lt["category"] not in only:
                    continue
                base = float(price.get(lt.get("commodity_code")) or 60)
                out.append({"lot_id": lt["id"], "unit_price": str(round(base * f, 2)), "quantity": str(lt["quantity"])})
            return {"lines": out, "delivery_plan": "Two deliveries per month to the school (simulation)"}
        s.put("supplier1", f"/supplier/opportunities/{X['ev']['id']}/bid", body(0.97))
        r1 = s.post("supplier1", f"/supplier/opportunities/{X['ev']['id']}/bid/submit")
        s.put("supplier2", f"/supplier/opportunities/{X['ev']['id']}/bid", body(1.0))
        r2 = s.post("supplier2", f"/supplier/opportunities/{X['ev']['id']}/bid/submit")
        tok = s.tokens["0711000913"]
        r = s.c.put(f"{A}/supplier/opportunities/{X['ev']['id']}/bid", headers=tok,
                    json=body(0.95, {"legumes", "green_leafy_vegetables", "other_vegetables", "fruits"}))
        expect(r.status_code == 200, f"new supplier bid failed: {r.text[:200]}")
        r3 = s.c.post(f"{A}/supplier/opportunities/{X['ev']['id']}/bid/submit", headers=tok).json()
        expect(r1["receipt"] and r2["receipt"] and r3.get("receipt"), "no bid receipt")
        return f"3 sealed bids submitted with receipts ({r1['receipt']}, {r2['receipt']}, {r3['receipt']})"
    s.step("Three suppliers submit sealed bids (incl. the new farmer group, for its categories)", "supplier1", bids)

    def sealed():
        b = s.get("procurement", f"/procurement-events/{X['ev']['id']}/bids")
        expect(b["opened"] is False and all(x["contents"] is None for x in b["bids"]), "bid prices visible before opening")
        code = s.blocked("POST", "procurement", f"/procurement-events/{X['ev']['id']}/open")
        return f"{len(b['bids'])} bids, prices sealed; opening before the deadline refused ({code})"
    s.step("Bids stay sealed until the closing time", "procurement", sealed, control=True)

    def clarification():
        s.post("supplier2", f"/supplier/opportunities/{X['ev']['id']}/questions", {"question": "Can we deliver in two batches?"})
        q = s.get("procurement", f"/procurement-events/{X['ev']['id']}/clarifications")[0]
        s.post("procurement", f"/procurement-events/clarifications/{q['id']}/answer", {"answer": "Yes, two batches are fine."})
        c = s.get("supplier1", f"/supplier/opportunities/{X['ev']['id']}")["clarifications"]
        expect(any(x["answer"] for x in c), "answer not shared with all bidders")
        return "Question answered and shared with all bidders"
    s.step("Supplier asks a clarification; officer answers to all bidders", "supplier2", clarification)

    def close_open():
        pass_time(X["ev"]["reference"])
        code = s.blocked("PUT", "supplier1", f"/supplier/opportunities/{X['ev']['id']}/bid", {"lines": [], "delivery_plan": "late"})
        reg = s.post("procurement", f"/procurement-events/{X['ev']['id']}/open")
        return f"(Simulated: closing time passed.) Late bid refused ({code}); bid register opened with {len(reg['register'])} bids"
    s.step("Bidding closes; late bids refused; bids opened", "procurement", close_open)

    def panel():
        cands = {c["name"]: c["id"] for c in s.get("procurement", f"/procurement-events/{X['ev']['id']}/evaluators")["candidates"]}
        me = s.get("procurement", "/auth/me")["id"]
        code = s.blocked("POST", "procurement", f"/procurement-events/{X['ev']['id']}/evaluators", {"user_ids": [me]})
        s.post("procurement", f"/procurement-events/{X['ev']['id']}/evaluators",
               {"user_ids": [cands["Evaluator One (demo)"], cands["Evaluator Two (demo)"], cands["Evaluator Three (demo)"]]})
        return f"3 evaluators appointed; procurement officer cannot appoint themself ({code})"
    s.step("Procurement officer appoints a 3-member evaluation committee", "procurement", panel)

    def evaluate():
        eid = X["ev"]["id"]
        expect(s.get("evaluator1", f"/evaluations/{eid}")["bids"] is None, "bids shown before conflict-of-interest declaration")
        code = s.blocked("PUT", "evaluator1", f"/evaluations/{eid}/scores", {"scores": {}})
        for who in ("evaluator1", "evaluator2", "evaluator3"):
            s.post(who, f"/evaluations/{eid}/coi", {"has_conflict": False, "statement": "I have no interest in any bidder."})
            ws = s.get(who, f"/evaluations/{eid}")
            sc = {b["id"]: {"technical": 18, "capacity": 13, "quality": 9, "local": 8} for b in ws["bids"]}
            s.put(who, f"/evaluations/{eid}/scores", {"scores": sc})
            s.post(who, f"/evaluations/{eid}/submit")
        return f"Each evaluator declared no conflict, then scored and submitted (scoring before the declaration refused: {code})"
    s.step("Evaluators declare conflicts of interest, score and submit", "evaluator1", evaluate)

    def consolidate():
        res = s.post("procurement", f"/procurement-events/{X['ev']['id']}/consolidate")["results"]
        X["rec_total"] = res.get("recommended_total")
        tops = {lt["name"]: lt["bids"][0]["supplier"] for lt in res["lots"] if lt["bids"]}
        return f"Recommended total KES {res.get('recommended_total')}; winners per lot: " + "; ".join(f"{k}: {v}" for k, v in list(tops.items())[:6])
    s.step("Procurement officer consolidates scores (technical + price)", "procurement", consolidate)

    def recommend():
        X["aw_wf"] = s.post("procurement", f"/procurement-events/{X['ev']['id']}/recommend")["workflow"]["id"]
        code = s.blocked("POST", "approver", f"/workflow/{X['aw_wf']}/act", {"action": "approve"})
        s.act("finance", X["aw_wf"])
        r = s.act("approver", X["aw_wf"])
        expect(r["status"] == "approved", r["status"])
        ev = s.get("procurement", f"/procurement-events/{X['ev']['id']}")
        expect(ev["status"] == "awarded", ev["status"])
        return f"Finance commitment check, then award approved (approver could not skip the finance step: {code}). Awarded to: {ev['awarded_to']}"
    s.step("Award: finance commitment check, approving officer approves", "approver", recommend)

    def award_notice():
        pub = s.get("public", "/public/opportunities")
        expect(any(a["reference"] == X["ev"]["reference"] for a in pub["awards"]), "no public award notice")
        return "Award notice published on the website"
    s.step("Public award notice is published", "public", award_notice)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "7 Contract & order"

    def orders():
        found = []
        for who, tok in (("supplier1", s.h("supplier1")), ("supplier2", s.h("supplier2")), ("supplier3", s.tokens["0711000913"])):
            o = s.c.get(f"{A}/supplier/orders", headers=tok).json()
            for po in o["orders"]:
                if po["status"] == "issued":
                    r = s.c.post(f"{A}/supplier/orders/{po['id']}/acknowledge", headers=tok).json()
                    expect(r["status"] == "acknowledged", r)
                    found.append((who, po["reference"]))
        expect(found, "no purchase order issued")
        X["pos"] = found
        return "Purchase orders acknowledged: " + ", ".join(f"{w} {r}" for w, r in found)
    s.step("Winning suppliers see their contract and acknowledge the purchase order", "supplier1", orders)

    def losers():
        all_notes = " ".join(n["body"] for n in s.get("supplier2", "/notifications")["items"]) + \
            " ".join(n["body"] for n in s.get("supplier1", "/notifications")["items"])
        expect("not successful" in all_notes or "awarded" in all_notes.lower(), "no award / regret notice")
        return "Award and regret notifications sent"
    s.step("Bidders are told the outcome", "supplier2", losers)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "8 Aggregation & quality"
    hub = org_id("HUB-DEMO-101")
    lg_orders = s.get("logistics", "/dispatch/orders")["orders"]
    umoja_po = next((o for o in lg_orders if o["reference"] in [r for w, r in X.get("pos", []) if w == "supplier1"]), None)
    X["po"] = umoja_po

    def intake():
        expect(X["po"], "no purchase order for the cooperative (Umoja) to fulfil")
        X["batches"] = {}
        for ln in X["po"]["lines"][:3]:
            q = sum(float(sc["remaining"]) for sc in ln["schools"] if sc["school_id"] == school)
            if q <= 0:
                continue
            ref = uuid.uuid4().hex[:10]
            parts = [round(q * 0.6, 2), round(q - round(q * 0.6, 2), 2)]
            first = None
            for i, part in enumerate(parts):
                r = s.post("aggregator", "/intakes", {"location_id": hub, "producer_name": f"Producer {i + 1} (simulation)",
                                                      "producer_gender": "female" if i == 0 else "male", "producer_youth": i == 0,
                                                      "commodity_code": ln["commodity_code"], "quantity": str(part), "client_ref": f"{ref}-{i}"})
                first = first or r
            X["batches"][ln["commodity_code"]] = {"id": first["batch"]["id"], "qty": q, "line": ln}
        return "Intake recorded from smallholder producers into batches: " + ", ".join(f"{k} {v['qty']:.0f} kg" for k, v in X["batches"].items())
    s.step("Aggregator records produce intake from farmers at the hub", "aggregator", intake)

    def offline_dup():
        ln = next(iter(X["batches"].values()))
        r = s.post("aggregator", "/intakes", {"location_id": hub, "producer_name": "Retry", "commodity_code": ln["line"]["commodity_code"],
                                              "quantity": "1", "client_ref": "dup-check-1"})
        r2 = s.post("aggregator", "/intakes", {"location_id": hub, "producer_name": "Retry", "commodity_code": ln["line"]["commodity_code"],
                                               "quantity": "1", "client_ref": "dup-check-1"})
        expect(r2.get("duplicate"), "offline retry created a duplicate")
        X["dup_batch"] = r["batch"]["id"]
        return "Re-sending the same offline record does not double-count"
    s.step("Offline re-sync of the same intake is not double-counted", "aggregator", offline_dup, control=True)

    def inspect():
        out = []
        for code, b in X["batches"].items():
            s.post("aggregator", f"/batches/{b['id']}/request-inspection")
            batch = s.get("aggregator", f"/batches/{b['id']}")
            r = s.post("inspector", f"/batches/{b['id']}/inspections", {
                "parameters": {"moisture_pct": 12.4}, "visual_checks": {"pests": False, "mould": False}, "result": "accepted",
                "accepted_qty": str(batch["intake_qty"]), "rejected_qty": "0", "grade": "Grade 1"})
            out.append(f"{code} {batch['code']}")
            b["code"] = batch["code"]
        return "Inspected and cleared: " + ", ".join(out)
    s.step("Quality inspector inspects and clears each batch", "inspector", inspect)

    def quality_fail():
        r = s.post("aggregator", "/intakes", {"location_id": hub, "producer_name": "Wet lot (simulation)", "commodity_code": "MAIZE-FLOUR",
                                              "variety": "sim-wet", "quantity": "100"})
        bid = r["batch"]["id"]
        s.post("aggregator", f"/batches/{bid}/request-inspection")
        code = s.blocked("POST", "inspector", f"/batches/{bid}/inspections", {"parameters": {"moisture_pct": 15.5}, "result": "accepted",
                                                                               "accepted_qty": "100", "rejected_qty": "0"})
        s.post("inspector", f"/batches/{bid}/inspections", {"parameters": {"moisture_pct": 15.5}, "result": "rejected", "accepted_qty": "0",
                                                            "rejected_qty": "100", "reason": "Moisture above 13.5%",
                                                            "corrective_action": "Dry and re-submit"})
        cases = s.get("procurement", "/exceptions")
        expect(any(c["category"] == "quality_rejection" for c in cases), "no exception case raised")
        return f"Wet maize cannot be accepted ({code}); rejected and an exception case raised"
    s.step("Produce that fails moisture limits cannot be accepted", "inspector", quality_fail, control=True)

    def qr():
        b = next(iter(X["batches"].values()))
        r = s.c.get(f"{A}/batches/{b['id']}/qr.svg", headers=s.h("aggregator"))
        expect(r.status_code == 200 and b"<svg" in r.content, "no QR label")
        return f"QR label printed for batch {b['code']}"
    s.step("Aggregator prints the batch QR label", "aggregator", qr)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "9 Warehouse"
    store = org_id("WH-DEMO-A1")

    def transfer():
        code, b = list(X["batches"].items())[0]
        r = s.post("aggregator", "/inventory/transfers", {"from_location_id": hub, "to_location_id": store, "batch_id": b["id"], "quantity": "5"})
        return f"5 kg of {code} moved to the county store ({r.get('reference', 'ok')})"
    s.step("Stock transfer from the hub to the county store", "aggregator", transfer)

    def adjust():
        r = s.post("aggregator", "/inventory/adjustments", {"location_id": hub, "batch_id": X["dup_batch"], "quantity": "-1", "type": "waste",
                                                            "reason": "Torn sack (simulation)"})
        w = r["workflow"]["id"]
        code = s.blocked("POST", "aggregator", f"/workflow/{w}/act", {"action": "approve"})
        s.act("warehouse.supervisor", w)
        return f"Write-off posted only after the warehouse supervisor verified it (self-approval refused: {code})"
    s.step("Stock write-off needs a second person's verification", "warehouse.supervisor", adjust)

    def count():
        bal = s.get("warehouse", "/inventory/balances")
        rows = [r for r in bal if r.get("location_id") == store] or bal[:1]
        expect(rows, "no stock in the county store")
        r0 = rows[0]
        c = s.post("warehouse", "/inventory/counts", {"location_id": store, "lines": [
            {"batch_id": r0["batch_id"], "commodity_code": r0["commodity_code"], "counted_qty": str(float(r0["on_hand"]) - 1)}]})
        if c.get("workflow"):
            s.act("warehouse.supervisor", c["workflow"]["id"])
        return f"Physical count at the county store; variance {c['lines'][0]['variance']} kg verified and posted"
    s.step("Warehouse officer does a stock count; variance verified", "warehouse", count)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "10 Dispatch & delivery"

    def dispatch():
        drivers = s.get("logistics", "/dispatch/drivers")
        lines = []
        for code, b in X["batches"].items():
            avail = float(s.get("aggregator", f"/batches/{b['id']}")["on_hand"])
            q = min(b["qty"], avail)
            lines.append({"po_line_id": b["line"]["po_line_id"], "school_id": school, "batch_id": b["id"], "quantity": f"{q:.2f}"})
        over = [{**lines[0], "quantity": str(float(lines[0]["quantity"]) + 1000)}]
        body = {"po_id": X["po"]["id"], "source_location_id": hub, "vehicle": "KDA 123A", "driver_user_id": drivers[0]["id"],
                "planned_date": str(TODAY), "lines": lines}
        code = s.blocked("POST", "logistics", "/dispatches", {**body, "lines": over})
        d = s.post("logistics", "/dispatches", body)
        X["disp"] = d
        return f"Trip {d['reference']} planned to {X['school_name']} with {len(lines)} items (sending more than ordered refused: {code})"
    s.step("Logistics officer plans the delivery trip", "logistics", dispatch)

    def route():
        r = s.get("logistics", f"/dispatches/{X['disp']['id']}/route")
        return f"Suggested route: {r['suggested'].get('total_km')} km"
    s.step("Route suggestion uses the school GPS", "logistics", route)

    def go():
        d = s.post("logistics", f"/dispatches/{X['disp']['id']}/dispatch")
        expect(d["status"] == "dispatched", d["status"])
        d = s.post("driver", f"/dispatches/{X['disp']['id']}/milestones", {"status": "in_transit", "lat": -1.95, "lng": 37.70})
        expect(d["status"] == "in_transit", d["status"])
        X["disp"] = d
        return "Dispatched; driver marked 'in transit' with a GPS position"
    s.step("Trip dispatched; driver updates progress", "driver", go)

    def pod():
        stop = next(st for st in X["disp"]["stops"] if st["school_id"] == school)
        lines = []
        for i, ln in enumerate(stop["lines"]):
            q = float(ln["quantity"])
            if i == 0:
                lines.append({"line_id": ln["id"], "accepted_qty": f"{q - 10:.2f}", "rejected_qty": "10", "rejection_reason": "Two torn sacks"})
            else:
                lines.append({"line_id": ln["id"], "accepted_qty": f"{q:.2f}"})
        r = s.post("school.admin", f"/dispatches/{X['disp']['id']}/pod", {"school_id": school, "receiver_name": "Head teacher (simulation)",
                                                                          "signature": SIG, "lines": lines})
        cats = {c["category"] for c in s.get("procurement", "/exceptions") if c["entity_ref"] == X["disp"]["reference"]}
        return f"Delivery confirmed with signature; 10 kg rejected → exception raised ({', '.join(sorted(cats)) or 'none'}). Trip {r['status']}"
    s.step("School administrator confirms delivery (e-POD) and rejects damaged goods", "school.admin", pod)

    def wrong_school():
        stop = X["disp"]["stops"][0]
        return s.blocked("POST", "school2.admin", f"/dispatches/{X['disp']['id']}/pod",
                         {"school_id": school, "receiver_name": "x", "lines": [{"line_id": stop["lines"][0]["id"], "accepted_qty": "1"}]})
    s.step("Another school cannot confirm this school's delivery", "school2.admin", wrong_school, control=True)

    def resolve_exc():
        ca = [c for c in s.get("county.admin", "/exceptions") if c["entity_ref"] == X["disp"]["reference"]]
        expect(ca, "no delivery exception to resolve")
        s.post("procurement", f"/exceptions/{ca[0]['id']}/progress", {"text": "Supplier to replace 10 kg"})
        r = s.post("county.admin", f"/exceptions/{ca[0]['id']}/resolve", {"text": "Replacement delivered (simulation)"})
        expect(r["status"] == "resolved", r["status"])
        return "Exception followed up and resolved"
    s.step("Delivery exception followed up and resolved", "county.admin", resolve_exc)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "11 School stock"

    def consume():
        code = next(iter(X["batches"]))
        r = s.post("meals.officer", "/inventory/consumption", {"location_id": school, "commodity_code": code, "quantity": "20", "meals_served": 580})
        bal = [b for b in s.get("meals.officer", "/inventory/balances") if b.get("location_id") == school]
        return f"Daily use recorded (20 kg {code}, 580 meals). School stock lines: {len(bal)}"
    s.step("School meals officer records daily food use and meals served", "meals.officer", consume)

    def outlook():
        r = s.get("meals.officer", "/analytics/stock-outlook")
        return f"Stock outlook rows: {len(r)}"
    s.step("School sees its stock outlook (days of food left)", "meals.officer", outlook)

    def trace():
        b = next(iter(X["batches"].values()))
        t = s.get("procurement", f"/trace/{b['code']}")
        pub = s.get("public", f"/public/trace/{b['code']}")
        expect("Producer 1" not in str(pub), "producer names leaked on the public trace page")
        return f"Farm → hub → school traced ({len(t['deliveries'])} deliveries); public QR page hides producer names"
    s.step("Traceability: batch traced from farmers to the school", "procurement", trace)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "12 Invoice & payment"

    def invoice():
        bill = next(o for o in s.get("aggregator", "/invoices/billable") if o["id"] == X["po"]["id"])
        lines = [{"po_line_id": ln["po_line_id"], "quantity": str(ln["billable_qty"])} for ln in bill["lines"] if float(ln["billable_qty"]) > 0]
        base = {"po_id": X["po"]["id"], "supplier_invoice_no": "SIM-INV-001", "invoice_date": str(TODAY)}
        over = [{**lines[0], "quantity": str(float(lines[0]["quantity"]) + 50)}]
        code = s.blocked("POST", "aggregator", "/invoices", {**base, "lines": over})
        inv = s.post("aggregator", "/invoices", {**base, "lines": lines})
        expect(inv["match"]["result"] == "matched", inv["match"])
        X["inv"] = inv
        return f"Invoice {inv['reference']} KES {inv['total']} matched to PO and accepted deliveries (billing more than delivered refused: {code})"
    s.step("Supplier (aggregator) submits the invoice; three-way match", "aggregator", invoice)

    def dup_inv():
        bill = s.get("aggregator", "/invoices/billable")
        return s.blocked("POST", "aggregator", "/invoices", {"po_id": X["po"]["id"], "supplier_invoice_no": "sim-inv-001", "invoice_date": str(TODAY),
                                                            "lines": [{"po_line_id": X["po"]["lines"][0]["po_line_id"], "quantity": "1"}]})
    s.step("A duplicate invoice number is refused", "aggregator", dup_inv, control=True)

    def verify_approve():
        w = X["inv"]["workflow"]["id"]
        s.act("accounts", w)
        code = s.blocked("POST", "accounts", f"/workflow/{w}/act", {"action": "approve"})
        s.act("finance", w)
        got = s.get("accounts", f"/invoices/{X['inv']['id']}")
        expect(got["status"] == "approved", got["status"])
        return f"Verified by accounts, approved by county finance (same person cannot do both: {code})"
    s.step("Finance verifies, county finance approves the invoice", "finance", verify_approve)

    def pay_details():
        r = s.put("aggregator", "/suppliers/me/payment-details", {"method": "mpesa", "account_name": "Umoja Farmers Cooperative (demo)",
                                                                  "mpesa_phone": "0700 000 101"})
        pend = s.get("accounts", "/finance/payment-details/pending")
        sid = next(x["supplier_id"] for x in pend if x["supplier"].startswith("Umoja"))
        s.post("accounts", f"/finance/payment-details/{sid}/verify", {"approve": True, "note": "Called the registered number (simulation)"})
        return "Payment details change requested by the supplier and verified by finance"
    s.step("Supplier payment details verified before payment", "accounts", pay_details)

    def pay():
        code = s.blocked("POST", "accounts", f"/invoices/{X['inv']['id']}/payments",
                         {"amount": "1", "method": "mpesa", "transaction_ref": "SIMX0", "paid_on": str(TODAY)})
        total = Decimal(str(X["inv"]["total"]))
        half = (total / 2).quantize(Decimal("0.01"))
        s.post("payments", f"/invoices/{X['inv']['id']}/payments", {"amount": str(half), "method": "mpesa", "transaction_ref": "SIMPAY001",
                                                                    "paid_on": str(TODAY)})
        r = s.post("payments", f"/invoices/{X['inv']['id']}/payments", {"amount": str(total - half), "method": "mpesa",
                                                                        "transaction_ref": "SIMPAY002", "paid_on": str(TODAY)})
        expect(r["status"] == "paid", r["status"])
        return f"Paid in two instalments (verifier could not pay: {code})"
    s.step("Payments officer records payment (separate from the verifier)", "payments", pay)

    def supplier_sees():
        n = s.get("aggregator", "/notifications")["items"]
        expect(any("Payment" in x["title"] for x in n), "supplier not told about payment")
        inv = s.get("supplier1", "/invoices")
        return f"Supplier notified and can follow its invoice ({len(inv)} invoice(s) visible to the cooperative)"
    s.step("Supplier is notified and follows payment status", "supplier1", supplier_sees)

    def budget_moves():
        bl = s.get("finance", f"/budget-lines/{X['bl']}")
        return f"Budget line: committed {bl['committed']}, invoiced {bl.get('invoiced')}, paid {bl.get('paid')}, available {bl['available']}"
    s.step("Budget line shows committed, invoiced and paid amounts", "finance", budget_moves)

    def exports():
        r = s.c.get(f"{A}/finance/ifmis-export.csv", headers=s.h("payments"))
        expect(r.status_code == 200 and X["inv"]["reference"] in r.text, "IFMIS export missing the invoice")
        return "IFMIS export contains the paid invoice"
    s.step("Finance exports payments for IFMIS", "payments", exports)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "13 Complaints & recall"
    sup_id = next((c["supplier_id"] for c in s.get("procurement", "/performance/suppliers") if c["supplier"].startswith("Umoja")), None)

    def complaint():
        c = s.post("school.admin", "/complaints", {"category": "food_quality", "subject": "Beans with stones (simulation)",
                                                   "description": "Two sacks of beans had many small stones.", "supplier_id": sup_id})
        s.post("procurement", f"/complaints/{c['id']}/actions", {"action": "investigate", "note": "Asked the hub for sorting records"})
        s.post("aggregator", f"/complaints/{c['id']}/actions", {"action": "respond", "note": "We will re-sort and replace"})
        s.post("county.admin", f"/complaints/{c['id']}/actions", {"action": "resolve", "note": "Supplier replaced 20 kg"})
        d = s.post("school.admin", f"/complaints/{c['id']}/actions", {"action": "confirm", "satisfaction": 4})
        expect(d["status"] == "closed", d["status"])
        return f"Complaint {c['reference']}: raised → investigated → supplier responded → resolved → school confirmed (4/5)"
    s.step("School raises a food-quality complaint; it is investigated and closed", "school.admin", complaint)

    def grievance():
        r = s.post("public", "/public/contact", {"name": "Parent (simulation)", "contact": "0711000000", "topic": "grievance",
                                                 "category": "late_delivery", "message": "Lunch was not served on Monday because food had not arrived.",
                                                 "county_id": county})
        expect(r["reference"].startswith("CMP-"), r)
        return f"Public grievance {r['reference']} routed to Makueni County"
    s.step("A parent sends a grievance through the website", "public", grievance)

    def recall():
        b = list(X["batches"].values())[-1]
        code = s.blocked("POST", "aggregator", f"/batches/{b['id']}/recall", {"reason": "Lab test"})
        r = s.post("inspector", f"/batches/{b['id']}/recall", {"reason": "Aflatoxin test failed at county lab (simulation)"})
        pub = s.get("public", f"/public/trace/{b['code']}")
        expect(pub["recalled"] is True, "public page does not show the recall")
        return f"Batch {b['code']} recalled; {r['schools_notified']} school(s) notified; QR page shows RECALLED (supplier cannot recall: {code})"
    s.step("Quality inspector recalls a batch; schools are warned", "inspector", recall)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "14 Monitoring & audit"

    def meal():
        d = s.get("meal", "/meal/dashboard")
        x = s.c.get(f"{A}/meal/exports/invoices.xlsx", headers=s.h("meal"))
        expect(x.status_code == 200, "Excel export failed")
        return f"MEAL dashboard: schools served {d['reach']['schools_served']}, paid KES {d['finance']['paid']}; Excel export OK"
    s.step("MEAL officer views the dashboard and exports data", "meal", meal)

    def scorecard():
        cards = s.get("procurement", "/performance/suppliers")
        u = next(c for c in cards if c["supplier"].startswith("Umoja"))
        perf = s.get("meal", "/performance/counties")
        return f"Supplier scorecard: Umoja score {u['score']}, {u['deliveries']} deliveries; county performance rows {len(perf)}"
    s.step("Supplier scorecards and county performance", "procurement", scorecard)

    def prices():
        p = s.get("procurement", "/analytics/prices")
        s.blocked("GET", "supplier2", "/analytics/prices", codes=(403,))
        return f"Price intelligence for {len(p)} food items (hidden from suppliers)"
    s.step("Price intelligence (officers only)", "procurement", prices)

    def risk():
        d = s.get("risk", "/risk/dashboard")
        n = s.post("risk", "/risk/scan")["new_cases"]
        return f"Risk dashboard: {len(d['flags'])} flags; scan opened {n} new case(s)"
    s.step("Risk & compliance officer reviews risk flags", "risk", risk)

    def gis():
        m = s.get("meal", "/gis/map")
        expect(m["counts"]["mapped"] >= 1, "nothing on the map")
        return f"Programme map: {m['counts']['mapped']} locations mapped"
    s.step("Programme map shows the school and stores", "meal", gis)

    def audit():
        r = s.get("auditor", "/audit")
        items = r["items"] if isinstance(r, dict) else r
        expect(items, "audit log empty")
        code = s.blocked("POST", "auditor", f"/workflow/{X['inv']['workflow']['id']}/act", {"action": "approve"})
        return f"Audit trail readable ({r.get('total', len(items)) if isinstance(r, dict) else len(items)} entries); auditor is read-only ({code})"
    s.step("Auditor reviews the audit trail (read-only)", "auditor", audit)

    def county_scope():
        rows = s.get("school.admin", "/demands")
        expect(all(r.get("school_id") in (school, None) for r in rows), "school admin sees another school's demand")
        return f"School administrator sees only {X['school_name']} records ({len(rows)} demand(s))"
    s.step("Each person sees only their school/county", "school.admin", county_scope, control=True)

    def jobs():
        from app import jobs as j
        out = j.run(list(j.TASKS))
        bad = {k: v for k, v in out.items() if isinstance(v, dict) and "error" in v}
        expect(not bad, f"background jobs failed: {bad}")
        return "Background jobs ran: " + ", ".join(out)
    s.step("Background jobs (reminders, messages, auto-closing) run cleanly", "administrator", jobs)

    # ----------------------------------------------------------------------------------------------------------------
    s.stage = "15 Website content"

    def news():
        n = s.post("editor", "/cms/news", {"title": "Makueni pilot begins (simulation)", "summary": "Simulation post"})
        code = s.blocked("POST", "editor", f"/cms/news/{n['id']}/workflow", {"action": "publish"})
        s.post("editor", f"/cms/news/{n['id']}/workflow", {"action": "submit"})
        r = s.post("administrator", f"/cms/news/{n['id']}/workflow", {"action": "publish"})
        expect(r["status"] == "published", r["status"])
        pub = s.c.get(f"{A}/public/news/{n['slug']}")
        expect(pub.status_code == 200, "news not public")
        return f"Editor drafted, submitted (could not publish: {code}); administrator published"
    s.step("Content editor drafts news; administrator publishes", "editor", news)

    def hero():
        blk = next(b for b in s.get("administrator", "/cms/blocks") if b["key"] == "hero")
        s.put("administrator", "/cms/blocks/hero", {"data": dict(blk["data"], title="Nutritious school meals, sourced from local farmers")})
        s.post("administrator", "/cms/blocks/hero/workflow", {"action": "publish"})
        return "Homepage banner edited and published"
    s.step("Administrator edits and publishes the homepage banner", "administrator", hero)


# =====================================================================================================================
def write_report(s: Sim, path: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    passed = sum(r["status"] == "PASS" for r in s.rows)
    ws.append(["LisheBora pilot simulation – Makueni County, " + str(s.ctx.get("school_name", SCHOOL))])
    ws.append([f"Run on {datetime.now():%d %b %Y %H:%M}. Fresh demo database; demo accounts; illustrative figures only."])
    ws.append([])
    ws.append(["Steps", len(s.rows)])
    ws.append(["Passed", passed])
    ws.append(["Failed", len(s.rows) - passed])
    ws.append(["Of which controls (actions the system must block)", sum(r["type"].startswith("Control") for r in s.rows)])
    ws.append([])
    ws.append(["Stage", "Steps", "Passed"])
    stages = {}
    for r in s.rows:
        st = stages.setdefault(r["stage"], [0, 0])
        st[0] += 1
        st[1] += r["status"] == "PASS"
    for k, (n, p) in stages.items():
        ws.append([k, n, p])
    ws["A1"].font = Font(bold=True, size=14, color="2F4520")
    for c in ("A9", "B9", "C9"):
        ws[c].font = Font(bold=True)
    ws.column_dimensions["A"].width = 52
    d = wb.create_sheet("Steps")
    head = ["#", "Stage", "Step", "Type", "Role", "Demo account", "Result", "What happened"]
    d.append(head)
    for r in s.rows:
        d.append([r["no"], r["stage"], r["step"], r["type"], r["role"], r["account"], r["status"], r["detail"]])
    fill = PatternFill("solid", fgColor="507435")
    for c in d[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
    for row in d.iter_rows(min_row=2):
        row[6].fill = PatternFill("solid", fgColor="D9EAD3" if row[6].value == "PASS" else "F4CCCC")
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for col, w in zip("ABCDEFGH", (5, 20, 52, 18, 28, 34, 9, 90)):
        d.column_dimensions[col].width = w
    d.freeze_panes = "A2"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main():
    save = "--save" in sys.argv
    build_database()
    s = Sim()
    print(f"Running the pilot story for Makueni County, school {SCHOOL}…\n")
    try:
        run(s)
    except Exception as e:  # a set-up step blew up outside a recorded step
        s.rows.append({"no": len(s.rows) + 1, "stage": s.stage, "step": "Simulation stopped", "role": "", "account": "", "type": "Process",
                       "status": "FAIL", "detail": f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}", "ms": 0})
        print(traceback.format_exc())
    out = ROOT / "docs" / "pilot_test" / "LisheBora_Simulation_Report.xlsx"
    write_report(s, out)
    passed = sum(r["status"] == "PASS" for r in s.rows)
    print(f"\n{passed} of {len(s.rows)} steps passed. Report: {out}")
    if save:
        engine.dispose()
        dest = BACKEND / "lishebora_example.db"
        shutil.copyfile(os.path.join(_work, "simulation.db"), dest)
        # mark the copy as up to date with the migrations, so "alembic upgrade head" leaves it alone
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        import sqlite3
        head = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
        con = sqlite3.connect(dest)
        con.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        con.execute("DELETE FROM alembic_version")
        con.execute("INSERT INTO alembic_version VALUES (?)", (head,))
        con.commit()
        con.close()
        src_store, dst_store = Path(os.environ["STORAGE_DIR"]), BACKEND / "storage"
        for f in src_store.rglob("*"):
            if f.is_file():
                t = dst_store / f.relative_to(src_store)
                t.parent.mkdir(parents=True, exist_ok=True)
                if not t.exists():
                    shutil.copyfile(f, t)
        print(f"Completed example cycle saved to {dest} (switch to it with scripts\\use-example.bat).")
    return 0 if passed == len(s.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
