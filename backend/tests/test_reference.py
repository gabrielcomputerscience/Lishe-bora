"""Programme reference data: survey food categories and the sampled schools."""
from pathlib import Path

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Commodity, Organization, OrgType
from app.seed.reference import FOOD_CATEGORIES, SAMPLED_SCHOOLS
from tests.conftest import login

A = "/api/v1"
CSV = Path(__file__).resolve().parents[2] / "docs" / "data" / "schools_sampled.csv"


def test_food_categories_and_commodities(client):
    cats = client.get(f"{A}/public/food-categories").json()
    assert [c["label"] for c in cats[:16]] == [label for _, label, _, _ in FOOD_CATEGORIES]
    legumes = next(c for c in cats if c["key"] == "legumes")
    assert {x["name"] for x in legumes["commodities"]} == {"Beans", "Cowpeas", "Pigeon peas", "Green grams"}
    with SessionLocal() as db:
        codes = [code for _k, _l, _g, items in FOOD_CATEGORIES for code, _n, _u in items]
        assert len(codes) == 36 and db.scalar(select(func.count()).select_from(Commodity).where(Commodity.is_active, Commodity.code.in_(codes))) == 36
        assert db.scalar(select(Commodity).where(Commodity.code == "MZE-G1")) is None or \
            not db.scalar(select(Commodity).where(Commodity.code == "MZE-G1")).is_active


def test_sampled_schools_seeded_and_csv_matches(client):
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(Organization).where(Organization.type == OrgType.school,
                                                                          Organization.code.in_([s[2] for s in SAMPLED_SCHOOLS])))
        assert n == 32
        k = db.scalar(select(Organization).where(Organization.code == "MAKUENI-SCH001"))
        sc = db.get(Organization, k.parent_id)
        assert (k.name, sc.name, sc.code, db.get(Organization, sc.parent_id).name) == ("Kalulini", "Kibwezi West", "MAKUENI-KIBWEZI-WEST", "Makueni County")
    ah = login(client, "admin@lishebora.local", "ChangeMe!2026")
    r = client.post(f"{A}/system/import/schools", headers=ah, files={"file": ("s.csv", CSV.read_text(), "text/csv")}).json()
    assert r["errors"] == 0 and r["update"] == 32 and r["create"] == 0      # the shipped CSV re-imports onto the seeded codes


def test_home_live_figures(client):
    live = {x["key"]: x["value"] for x in client.get(f"{A}/public/home").json()["live"]}
    assert live["counties"] == 3 and live["schools"] >= 32 and live["foods"] >= 36 and live["suppliers"] >= 2


def test_reach_by_county(client):
    r = client.get(f"{A}/public/reach").json()
    mk = next(c for c in r["counties"] if c["code"] == "MAKUENI")
    assert mk["schools"] >= 16 and mk["suppliers"] >= 2 and mk["food_varieties"] >= 9 and "Kibwezi West" in mk["sub_counties"]
    assert r["totals"]["counties"] == 3 and r["totals"]["schools"] >= 32
