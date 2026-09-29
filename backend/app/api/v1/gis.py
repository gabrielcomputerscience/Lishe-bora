"""GIS (Phase 6): location coordinates, the programme map and suggested delivery routes."""
import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, descendants, ensure_in_scope, require, require_any, scope_any
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (Complaint, ComplaintStatus, Dispatch, DispatchLine, DispatchStatus, Organization, OrgType,
                        ProofOfDelivery)
from app.services import audit, geo, stock

router = APIRouter(tags=["GIS"])
MAPPED = (OrgType.school, OrgType.aggregation_centre, OrgType.warehouse)


GPS_CODES = ("md:edit", "inv:create", "agg:create", "log:approve")
# Kenya's bounding box (with a small margin): catches swapped lat/lng, a missing minus sign or a typing slip.
KENYA = {"lat": (-4.9, 5.1), "lng": (33.8, 42.0)}


class GpsIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    source: str = Field(default="device", pattern="^(device|manual|map)$")   # phone GPS, typed in, or picked on the map
    note: str = Field(default="", max_length=200)


def _gps_scope(db: Session, p: Principal) -> set[uuid.UUID] | None:
    return scope_any(db, p, *GPS_CODES)


def _can_set(db: Session, p: Principal, o: Organization) -> bool:
    sc = _gps_scope(db, p)
    return sc is None or o.id in sc


@router.get("/fulfilment/gps-locations")
def list_locations(q: str = "", type: str = "school", missing: bool = False,
                   p: Principal = Depends(require_any(*GPS_CODES)), db: Session = Depends(get_db)):
    """Schools (or hubs/stores) the user may locate, with their current coordinates and who captured them."""
    types = [t for t in MAPPED if type in ("", "all") or t.value == type]
    sc = _gps_scope(db, p)
    orgs = db.scalars(select(Organization).where(Organization.type.in_(types), Organization.is_active).order_by(Organization.name)).all()
    parents = {o.id: o for o in db.scalars(select(Organization).where(Organization.type.in_((OrgType.county, OrgType.sub_county)))).all()}
    out = []
    for o in orgs:
        if sc is not None and o.id not in sc:
            continue
        if q and q.lower() not in (o.name + " " + o.code).lower():
            continue
        g = (o.meta or {}).get("gps")
        if missing and g:
            continue
        sub = parents.get(o.parent_id)
        county = sub if sub and sub.type == OrgType.county else parents.get(sub.parent_id) if sub else None
        out.append({"id": o.id, "name": o.name, "code": o.code, "type": o.type.value,
                    "sub_county": sub.name if sub and sub.type == OrgType.sub_county else None,
                    "county": county.name if county else None, "gps": g})
    return {"items": out, "total": len(out), "mapped": sum(1 for x in out if x["gps"])}


@router.put("/fulfilment/locations/{oid}/gps")
def set_gps(oid: uuid.UUID, body: GpsIn, request: Request, p: Principal = Depends(require_any(*GPS_CODES)),
            db: Session = Depends(get_db)):
    """Record a location's coordinates: captured on site with the phone's GPS, typed in, or picked on the map.
    School staff can set their own school; administrators can set any location. Every change is audited."""
    o = db.get(Organization, oid)
    if o is None or o.type not in MAPPED:
        raise AppError(404, "NOT_FOUND", "Location not found.")
    if not _can_set(db, p, o):
        raise AppError(403, "OUT_OF_SCOPE", "This location is outside your assigned area.")
    if not (KENYA["lat"][0] <= body.lat <= KENYA["lat"][1] and KENYA["lng"][0] <= body.lng <= KENYA["lng"][1]):
        raise AppError(422, "OUTSIDE_KENYA", "These coordinates are outside Kenya. Check that latitude and longitude are not swapped "
                                             "and that the minus sign is there for places south of the equator (e.g. Makueni is about -1.8, 37.6).")
    before = (o.meta or {}).get("gps")
    o.meta = {**(o.meta or {}), "gps": {"lat": round(body.lat, 6), "lng": round(body.lng, 6),
                                        "accuracy_m": round(body.accuracy_m, 1) if body.accuracy_m is not None else None,
                                        "source": body.source, "note": body.note.strip(), "by": p.user.full_name,
                                        "at": utcnow().isoformat()}}
    audit.record(db, action="SET_GPS", entity="organization", entity_id=o.id, user=p.user, before={"gps": before}, after={"gps": o.meta["gps"]},
                 request=request)
    db.commit()
    return {"id": o.id, "name": o.name, "gps": o.meta["gps"]}


@router.delete("/fulfilment/locations/{oid}/gps")
def clear_gps(oid: uuid.UUID, request: Request, p: Principal = Depends(require("md:edit")), db: Session = Depends(get_db)):
    """Administrators can remove wrong coordinates so the location is captured again."""
    o = db.get(Organization, oid)
    if o is None or o.type not in MAPPED:
        raise AppError(404, "NOT_FOUND", "Location not found.")
    before = (o.meta or {}).get("gps")
    o.meta = {k: v for k, v in (o.meta or {}).items() if k != "gps"}
    audit.record(db, action="CLEAR_GPS", entity="organization", entity_id=o.id, user=p.user, before={"gps": before}, request=request)
    db.commit()
    return {"id": o.id, "name": o.name, "gps": None}


@router.get("/gis/map")
def programme_map(county_id: uuid.UUID | None = None, p: Principal = Depends(require_any("meal:view", "log:view", "rsk:view")),
                  db: Session = Depends(get_db)):
    allowed = scope_any(db, p, "meal:view", "log:view", "rsk:view")
    if county_id:
        if allowed is not None and county_id not in allowed:
            raise AppError(403, "OUT_OF_SCOPE", "This county is outside your assigned area.")
        allowed = descendants(db, [county_id])
    orgs = [o for o in db.scalars(select(Organization).where(Organization.type.in_(MAPPED), Organization.is_active)).all()
            if allowed is None or o.id in allowed]
    ids = {o.id for o in orgs}
    last_pod: dict = {}
    pods_n: dict = defaultdict(int)
    for x in db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.school_id.in_(ids or {uuid.uuid4()}))).all():
        pods_n[x.school_id] += 1
        if x.school_id not in last_pod or as_utc(x.received_at) > as_utc(last_pod[x.school_id]):
            last_pod[x.school_id] = x.received_at
    complaints: dict = defaultdict(int)
    for c in db.scalars(select(Complaint).where(Complaint.school_id.in_(ids or {uuid.uuid4()}),
                                                Complaint.status.in_([ComplaintStatus.submitted, ComplaintStatus.investigating]))).all():
        complaints[c.school_id] += 1
    bal = stock.balances(db, ids)
    on_hand: dict = defaultdict(Decimal)
    alerts: dict = defaultdict(int)
    for r in bal:
        on_hand[r["location_id"]] += Decimal(r["on_hand"])
        alerts[r["location_id"]] += len(r["alerts"])
    points, missing = [], []
    for o in orgs:
        g = geo.gps(o)
        item = {"id": o.id, "name": o.name, "type": o.type.value, "code": o.code, "on_hand_kg": on_hand.get(o.id, Decimal(0)),
                "stock_alerts": alerts.get(o.id, 0)}
        if o.type == OrgType.school:
            item.update(deliveries=pods_n.get(o.id, 0), last_delivery=last_pod.get(o.id), open_complaints=complaints.get(o.id, 0))
        if g:
            points.append({**item, "lat": g[0], "lng": g[1]})
        else:
            missing.append(item)
    trips = []
    for d in db.scalars(select(Dispatch).options(selectinload(Dispatch.lines).selectinload(DispatchLine.school), selectinload(Dispatch.source))
                        .where(Dispatch.status.in_([DispatchStatus.dispatched, DispatchStatus.in_transit, DispatchStatus.delivered]))).all():
        if allowed is not None and d.source_location_id not in allowed and d.county_id not in allowed:
            continue
        fix = next((m for m in reversed(d.milestones or []) if m.get("lat") is not None), None)
        src = geo.gps(d.source)
        trips.append({"id": d.id, "reference": d.reference, "status": d.status.value, "vehicle": d.vehicle, "driver": d.driver_name,
                      "last_fix": {"lat": fix["lat"], "lng": fix["lng"], "at": fix["at"], "status": fix["status"]} if fix else None,
                      "source": {"lat": src[0], "lng": src[1]} if src else None,
                      "stops": [{"school": ln.school.name, **({"lat": geo.gps(ln.school)[0], "lng": geo.gps(ln.school)[1]} if geo.gps(ln.school) else {})}
                                for ln in {ln.school_id: ln for ln in d.lines}.values()]})
    return {"points": points, "without_coordinates": missing, "trips": trips,
            "counts": {"schools": sum(1 for o in orgs if o.type == OrgType.school),
                       "schools_served": sum(1 for o in orgs if o.type == OrgType.school and pods_n.get(o.id)),
                       "mapped": len(points), "unmapped": len(missing), "trips_on_road": len(trips)}}


def _route_for(db, d: Dispatch) -> dict:
    src = geo.gps(d.source)
    if not src:
        raise AppError(409, "NO_COORDINATES", f"Add GPS coordinates for {d.source.name} first.")
    schools = {ln.school_id: ln.school for ln in d.lines}
    r = geo.route(src, [(str(sid), geo.gps(s)) for sid, s in schools.items()])
    names = {str(k): v.name for k, v in schools.items()}
    r["stops"] = [{"school_id": k, "school": names[k], "km": next((x["km"] for x in r["legs"] if x["key"] == k), None),
                   **({"lat": geo.gps(schools[uuid.UUID(k)])[0], "lng": geo.gps(schools[uuid.UUID(k)])[1]} if geo.gps(schools[uuid.UUID(k)]) else {})}
                  for k in r["order"]]
    r["source"] = {"name": d.source.name, "lat": src[0], "lng": src[1]}
    return r


@router.get("/dispatches/{did}/route")
def suggest_route(did: uuid.UUID, p: Principal = Depends(require("log:view")), db: Session = Depends(get_db)):
    from app.api.v1.logistics import _load
    d = _load(db, did)
    ensure_in_scope(db, p, "log:view", d.source_location_id, d.county_id, *[ln.school_id for ln in d.lines])
    return {"suggested": _route_for(db, d), "saved": d.route}


@router.post("/dispatches/{did}/route")
def save_route(did: uuid.UUID, request: Request, p: Principal = Depends(require("log:create")), db: Session = Depends(get_db)):
    from app.api.v1.logistics import _load
    d = _load(db, did)
    ensure_in_scope(db, p, "log:create", d.source_location_id, d.county_id)
    if d.status not in (DispatchStatus.planned, DispatchStatus.dispatched):
        raise AppError(409, "INVALID_STATE", "The route can only be set before the trip is under way.")
    d.route = _route_for(db, d)
    audit.record(db, action="ROUTE", entity="dispatch", entity_id=d.id, user=p.user, after={"order": d.route["order"], "km": d.route["total_km"]},
                 request=request)
    db.commit()
    return {"saved": d.route}
