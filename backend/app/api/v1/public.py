"""Unauthenticated endpoints for the public website. Only published content is returned."""
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, optional_principal
from app.core.errors import AppError
from app.models import (Commodity, ContactMessage, ContentStatus, EventStatus, FaqItem, NewsPost, Organization,
                        OrgType, Page, ProcurementEvent, Resource, SiteBlock)

router = APIRouter(prefix="/public", tags=["public website"])
OPEN = (EventStatus.published, EventStatus.open)


def _news(n: NewsPost, body=False):
    d = {"slug": n.slug, "title": n.title, "category": n.category, "summary": n.summary,
         "cover_image": n.cover_image, "cover_alt": n.cover_alt, "published_at": n.published_at}
    if body:
        d["body"] = n.body
    return d


def _notice(e: ProcurementEvent):
    return {"reference": e.reference, "title": e.title, "method": e.method.value,
            "county": e.county.name if e.county else None, "eligibility": e.eligibility,
            "closes_at": e.closes_at, "status": e.status.value}


def _blocks(db: Session) -> dict:
    return {b.key: b.published_data for b in db.scalars(select(SiteBlock)).all() if b.published_data}


@router.get("/home")
def home(db: Session = Depends(get_db)):
    blocks = _blocks(db)
    stats = blocks.get("stats", {})
    news = db.scalars(select(NewsPost).where(NewsPost.status == ContentStatus.published)
                      .order_by(NewsPost.published_at.desc()).limit(3)).all()
    notices = db.scalars(select(ProcurementEvent).where(ProcurementEvent.is_public, ProcurementEvent.status.in_(OPEN))
                         .order_by(ProcurementEvent.closes_at).limit(3)).all()
    return {"hero": blocks.get("hero", {}), "stats": stats if stats.get("show") else None,
            "live": _live_figures(db) if stats.get("show_live", True) else None,
            "news": [_news(n) for n in news], "notices": [_notice(e) for e in notices]}


def _live_figures(db: Session) -> list[dict]:
    """Counted from the platform's own records at request time (not programme impact figures, which come from
    signed-off MEAL data through the admin-managed "stats" block)."""
    from sqlalchemy import func
    from app.models import Supplier, SupplierStatus
    from app.seed.reference import FOOD_CATEGORIES

    def orgs(t):
        return db.scalar(select(func.count()).select_from(Organization).where(Organization.type == t, Organization.is_active)) or 0
    suppliers = db.scalar(select(func.count()).select_from(Supplier).where(
        Supplier.status.in_([SupplierStatus.approved, SupplierStatus.prequalified, SupplierStatus.active]))) or 0
    commodities = db.scalar(select(func.count()).select_from(Commodity).where(Commodity.is_active)) or 0
    opps = db.scalar(select(func.count()).select_from(ProcurementEvent).where(ProcurementEvent.is_public,
                                                                            ProcurementEvent.status.in_(OPEN))) or 0
    return [{"key": "schools", "value": orgs(OrgType.school), "label": "schools on the platform"},
            {"key": "counties", "value": orgs(OrgType.county), "label": "pilot counties"},
            {"key": "suppliers", "value": suppliers, "label": "approved local suppliers"},
            {"key": "foods", "value": commodities, "label": f"foods across {len(FOOD_CATEGORIES)} food categories"},
            {"key": "opportunities", "value": opps, "label": "open opportunities"}]


@router.get("/news")
def news(db: Session = Depends(get_db)):
    rows = db.scalars(select(NewsPost).where(NewsPost.status == ContentStatus.published)
                      .order_by(NewsPost.published_at.desc())).all()
    return [_news(n) for n in rows]


@router.get("/news/{slug}")
def news_item(slug: str, db: Session = Depends(get_db)):
    n = db.scalar(select(NewsPost).where(NewsPost.slug == slug, NewsPost.status == ContentStatus.published))
    if n is None:
        raise AppError(404, "NOT_FOUND", "Article not found.")
    return _news(n, body=True)


@router.get("/pages/{slug}")
def page(slug: str, db: Session = Depends(get_db)):
    pg = db.scalar(select(Page).where(Page.slug == slug, Page.status == ContentStatus.published))
    if pg is None:
        raise AppError(404, "NOT_FOUND", "Page not found.")
    return {"slug": pg.slug, "title": pg.title, "body": pg.body, "updated_at": pg.updated_at}


@router.get("/faq")
def faq(db: Session = Depends(get_db)):
    rows = db.scalars(select(FaqItem).where(FaqItem.is_published).order_by(FaqItem.sort_order)).all()
    return [{"question": f.question, "answer": f.answer} for f in rows]


@router.get("/resources")
def resources(p: Principal | None = Depends(optional_principal), db: Session = Depends(get_db)):
    stmt = select(Resource).where(Resource.is_published)
    if p is None:
        stmt = stmt.where(Resource.visibility == "public")
    rows = db.scalars(stmt.order_by(Resource.sort_order, Resource.title)).all()
    return [{"id": r.id, "title": r.title, "description": r.description, "file_name": r.file_name,
             "size_bytes": r.size_bytes, "has_file": bool(r.file_key), "visibility": r.visibility} for r in rows]


@router.get("/resources/{rid}/file")
def resource_file(rid: str, p: Principal | None = Depends(optional_principal), db: Session = Depends(get_db)):
    import uuid as _u
    r = db.get(Resource, _u.UUID(rid))
    if r is None or not r.is_published or not r.file_key or (r.visibility != "public" and p is None):
        raise AppError(404, "NOT_FOUND", "File not found.")
    from app.services.storage import open_path
    return FileResponse(open_path(r.file_key), media_type=r.content_type, filename=r.file_name)


@router.get("/opportunities")
def opportunities(db: Session = Depends(get_db)):
    open_ = db.scalars(select(ProcurementEvent).where(ProcurementEvent.is_public, ProcurementEvent.status.in_(OPEN))
                       .order_by(ProcurementEvent.closes_at)).all()
    awards = db.scalars(select(ProcurementEvent).where(ProcurementEvent.is_public,
                                                       ProcurementEvent.status == EventStatus.awarded)
                        .order_by(ProcurementEvent.awarded_at.desc()).limit(20)).all()
    return {"open": [_notice(e) for e in open_],
            "awards": [{"reference": e.reference, "title": e.title, "awarded_to": e.awarded_to,
                        "value": e.awarded_value, "awarded_at": e.awarded_at} for e in awards]}


@router.get("/counties")
def counties(db: Session = Depends(get_db)):
    rows = db.scalars(select(Organization).where(Organization.type == OrgType.county, Organization.is_active)
                      .order_by(Organization.name)).all()
    return [{"id": o.id, "name": o.name} for o in rows]


@router.get("/commodities")
def commodities(db: Session = Depends(get_db)):
    rows = db.scalars(select(Commodity).where(Commodity.is_active).order_by(Commodity.category, Commodity.name)).all()
    from app.seed.reference import CATEGORY_LABELS
    return [{"code": c.code, "name": c.name, "category": c.category, "category_label": CATEGORY_LABELS.get(c.category, c.category)}
            for c in rows]


@router.get("/food-categories")
def food_categories(db: Session = Depends(get_db)):
    """The programme's food categories (school survey) with the active commodities in each."""
    from app.seed.reference import FOOD_CATEGORIES
    rows = db.scalars(select(Commodity).where(Commodity.is_active).order_by(Commodity.name)).all()
    by_cat: dict[str, list] = {}
    for c in rows:
        by_cat.setdefault(c.category, []).append({"code": c.code, "name": c.name, "unit": c.unit})
    out = [{"key": k, "label": label, "group": group, "commodities": by_cat.pop(k, [])} for k, label, group, _ in FOOD_CATEGORIES]
    out += [{"key": k, "label": k.replace("_", " ").capitalize(), "group": "", "commodities": v} for k, v in sorted(by_cat.items())]
    return out


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=120)
    topic: str = Field(default="general", max_length=40)
    message: str = Field(min_length=5, max_length=4000)
    website: str = ""   # honeypot: must stay empty
    county_id: uuid.UUID | None = None      # grievances: routes the case to the county
    category: str = "other"                 # grievances: complaint category
    anonymous: bool = False


@router.post("/contact", status_code=201)
def contact(body: ContactIn, request: Request, db: Session = Depends(get_db)):
    if body.website:
        return {"message": "Thank you."}   # silently drop bots
    db.add(ContactMessage(name=body.name, contact=body.contact, topic=body.topic, message=body.message))
    if body.topic == "grievance":
        from app.api.v1.complaints import CATEGORIES, create_complaint
        county = db.get(Organization, body.county_id) if body.county_id else None
        c = create_complaint(db, category=body.category if body.category in CATEGORIES else "other",
                             subject=body.message[:80] + ("…" if len(body.message) > 80 else ""), description=body.message, channel="public",
                             org_id=county.id if county and county.type == OrgType.county else None, contact_name=body.name,
                             contact=body.contact, anonymous=body.anonymous)
        db.commit()
        return {"message": f"Thank you. Your case number is {c.reference}. Keep it to follow up with the programme team.",
                "reference": c.reference}
    db.commit()
    return {"message": "Thank you. We have received your message."}


@router.get("/trace/{code}")
def public_trace(code: str, db: Session = Depends(get_db)):
    """Public batch verification from a QR label: origin, inspection outcome and recall status. No personal data."""
    from app.models import Batch, BatchStatus, DispatchLine, QualityInspection, Supplier
    from app.services.stock import county_of
    b = db.scalar(select(Batch).where(Batch.code == code.strip().upper()))
    if b is None or b.status == BatchStatus.open:
        raise AppError(404, "NOT_FOUND", "We could not find a batch with this code. Check the label and try again.")
    comm = db.scalar(select(Commodity).where(Commodity.code == b.commodity_code))
    county = db.get(Organization, county_of(db, b.location_id)) if county_of(db, b.location_id) else None
    sup = db.get(Supplier, b.supplier_id) if b.supplier_id else None
    insp = db.scalar(select(QualityInspection).where(QualityInspection.batch_id == b.id).order_by(QualityInspection.inspected_at.desc()))
    intakes = b.intakes
    schools = {ln.school_id for ln in db.scalars(select(DispatchLine).where(DispatchLine.batch_id == b.id, DispatchLine.accepted_qty > 0))}
    return {"code": b.code, "commodity": comm.name if comm else b.commodity_code, "variety": b.variety, "grade": b.grade,
            "status": b.status.value, "recalled": b.status == BatchStatus.recalled, "recall_reason": b.recall_reason if b.status == BatchStatus.recalled else "",
            "recalled_at": b.recalled_at, "county": county.name if county else None, "aggregated_by": sup.legal_name if sup else None,
            "formed_on": b.created_at.date() if b.created_at else None, "expiry_date": b.expiry_date,
            "inspection": {"result": insp.result.value, "date": insp.inspected_at.date()} if insp else None,
            "producers": len({(i.producer_name.strip().lower(), i.producer_phone) for i in intakes}),
            "women_producers": len({(i.producer_name.strip().lower(), i.producer_phone) for i in intakes if i.producer_gender == "female"}),
            "schools_supplied": len(schools)}


@router.get("/site")
def site(db: Session = Depends(get_db)):
    """Published helpdesk contact details (footer, sign-in pages)."""
    return _blocks(db).get("site", {})


@router.get("/backgrounds")
def backgrounds(db: Session = Depends(get_db)):
    """Published section and page background images: {slot: {url, overlay, position}}."""
    return _blocks(db).get("backgrounds", {})


@router.get("/media/{mid}")
def media(mid: uuid.UUID, db: Session = Depends(get_db)):
    from app.models import MediaAsset
    from app.services.storage import open_path
    m = db.get(MediaAsset, mid)
    if m is None:
        raise AppError(404, "NOT_FOUND", "Image not found.")
    return FileResponse(open_path(m.file_key), media_type=m.content_type, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/pilot-areas")
def pilot_areas(db: Session = Depends(get_db)):
    """Counties with their sub-counties and schools, for the public "Where we work" page (names only)."""
    rows = db.scalars(select(Organization).where(Organization.is_active, Organization.type.in_(
        [OrgType.county, OrgType.sub_county, OrgType.school_cluster, OrgType.school]))).all()
    kids: dict = {}
    for o in rows:
        kids.setdefault(o.parent_id, []).append(o)

    def schools_under(o) -> list[str]:
        out = []
        for k in kids.get(o.id, []):
            out += [k.name] if k.type == OrgType.school else schools_under(k)
        return out
    counties = []
    for c in sorted((o for o in rows if o.type == OrgType.county), key=lambda o: o.name):
        subs = [{"name": sc.name, "schools": sorted(schools_under(sc))}
                for sc in sorted(kids.get(c.id, []), key=lambda o: o.name) if sc.type == OrgType.sub_county]
        counties.append({"name": c.name, "code": c.code, "sub_counties": subs,
                         "schools": sum(len(x["schools"]) for x in subs)})
    return counties


@router.get("/reach")
def reach(db: Session = Depends(get_db)):
    """Programme reach per county for the homepage map, counted live from platform records.
    pupils = enrolment on each school's most recent submitted/approved term plan (schools without a plan add 0)."""
    from sqlalchemy import func
    from app.models import DemandStatus, SchoolDemand, Supplier, SupplierStatus
    counties = db.scalars(select(Organization).where(Organization.type == OrgType.county, Organization.is_active)).all()
    orgs = db.scalars(select(Organization).where(Organization.is_active, Organization.type.in_(
        [OrgType.sub_county, OrgType.school_cluster, OrgType.school]))).all()
    parent = {o.id: o.parent_id for o in orgs}
    ids = {c.id for c in counties}

    def county_of(oid):
        for _ in range(6):
            if oid in ids or oid is None:
                return oid
            oid = parent.get(oid)
        return None
    schools = [o for o in orgs if o.type == OrgType.school]
    counted = [DemandStatus.submitted, DemandStatus.validated, DemandStatus.approved, DemandStatus.converted, DemandStatus.closed]
    latest: dict = {}
    for d in db.scalars(select(SchoolDemand).where(SchoolDemand.status.in_(counted)).order_by(SchoolDemand.created_at)).all():
        latest[d.school_id] = d.enrolment
    registered = [SupplierStatus.submitted, SupplierStatus.under_review, SupplierStatus.approved, SupplierStatus.prequalified, SupplierStatus.active]
    sups = db.scalars(select(Supplier).where(Supplier.status.in_(registered))).all()
    active_codes = set(db.scalars(select(Commodity.code).where(Commodity.is_active)))
    out, tot_foods = [], set()
    for c in sorted(counties, key=lambda o: o.name):
        sch = [s for s in schools if county_of(s.parent_id) == c.id]
        cs = [s for s in sups if s.county_id == c.id]
        foods = {x for s in cs for x in (s.commodities or []) if x in active_codes}
        tot_foods |= foods
        # pupils: the latest submitted term plan, else the enrolment recorded on the school
        out.append({"code": c.code, "name": c.name, "schools": len(sch),
                    "pupils": sum(latest.get(s.id) or int((s.meta or {}).get("enrolment") or 0) for s in sch),
                    "suppliers": len(cs), "food_varieties": len(foods),
                    "sub_counties": sorted({o.name for o in orgs if o.type == OrgType.sub_county and o.parent_id == c.id})})
    return {"counties": out, "totals": {
        "counties": len(out), "schools": sum(x["schools"] for x in out), "pupils": sum(x["pupils"] for x in out),
        "suppliers": sum(x["suppliers"] for x in out), "food_varieties": len(tot_foods),
        "food_categories": len({db.scalar(select(Commodity.category).where(Commodity.code == f)) for f in tot_foods} - {None}),
    }}
