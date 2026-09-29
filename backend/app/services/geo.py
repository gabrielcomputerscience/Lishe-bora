"""Small GIS helpers (SRS Phase 6: GIS, route optimisation). Coordinates live in Organization.meta["gps"] = {lat, lng}.
PostGIS can replace these once the database is PostgreSQL; the API contract stays the same."""
import math


def gps(org) -> tuple[float, float] | None:
    g = (org.meta or {}).get("gps") if org is not None else None
    try:
        return (float(g["lat"]), float(g["lng"])) if g else None
    except (KeyError, TypeError, ValueError):
        return None


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in kilometres (haversine)."""
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def route(start: tuple[float, float], stops: list[tuple[str, tuple[float, float] | None]]) -> dict:
    """Nearest-neighbour ordering from the source, improved with 2-opt. Stops without coordinates go last, unordered.
    Straight-line distances: a planning aid, not road distance."""
    known = [(k, p) for k, p in stops if p]
    unknown = [k for k, p in stops if not p]
    order, cur, left = [], start, known[:]
    while left:
        nxt = min(left, key=lambda s: km(cur, s[1]))
        order.append(nxt)
        cur = nxt[1]
        left.remove(nxt)

    def length(seq):
        pts = [start] + [p for _, p in seq]
        return sum(km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    improved = True
    while improved and len(order) > 2:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if length(cand) + 1e-9 < length(order):
                    order, improved = cand, True
    legs, prev = [], start
    for k, p in order:
        legs.append({"key": k, "km": round(km(prev, p), 1)})
        prev = p
    return {"order": [k for k, _ in order] + unknown, "legs": legs, "total_km": round(sum(x["km"] for x in legs), 1),
            "without_coordinates": unknown, "method": "nearest neighbour + 2-opt, straight-line distance"}
