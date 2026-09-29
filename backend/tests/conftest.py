import os
import tempfile

# SQLite by default; set TEST_DATABASE_URL (e.g. postgresql+psycopg://…/lishebora_test) to run the suite on PostgreSQL.
# The test database is wiped at the start of every run.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DEBUG"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"   # the suite signs in hundreds of times from one address
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Organization, Role, User, UserRole, UserStatus  # noqa: E402
from app.seed import run as seed  # noqa: E402

PW = "Str0ngPassw0rd!"


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed.main(demo=True)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def org_id(code):
    with SessionLocal() as db:
        return db.scalar(select(Organization.id).where(Organization.code == code))


def make_user(email, role_key, org_code=None, phone=None):
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        if u:
            return u.id
        u = User(full_name=email.split("@")[0], email=email, phone=phone, password_hash=hash_password(PW),
                 status=UserStatus.active)
        db.add(u)
        db.flush()
        role = db.scalar(select(Role).where(Role.key == role_key))
        oid = db.scalar(select(Organization.id).where(Organization.code == org_code)) if org_code else None
        db.add(UserRole(user_id=u.id, role_id=role.id, org_id=oid))
        db.commit()
        return u.id


def login(client, email, password=PW):
    r = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    if r.status_code == 403 and r.json()["error"]["code"] == "USE_ADMIN_SIGN_IN":      # administrators sign in separately
        r = client.post("/api/v1/auth/admin/login", json={"identifier": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    if data["mfa_required"]:
        r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": data["mfa_token"], "code": data["dev_code"]})
        assert r.status_code == 200, r.text
        data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}
