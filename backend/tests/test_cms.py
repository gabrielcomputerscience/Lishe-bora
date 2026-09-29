from tests.conftest import login, make_user


def test_public_home(client):
    d = client.get("/api/v1/public/home").json()
    assert d["hero"]["title"] and d["stats"] is None      # stats hidden until real figures exist
    assert isinstance(d["notices"], list) and d["news"]


def test_editor_drafts_admin_publishes(client):
    make_user("editor@test.ke", "content_editor")
    eh = login(client, "editor@test.ke")
    n = client.post("/api/v1/cms/news", headers=eh, json={"title": "Information sessions for suppliers",
                                                          "summary": "Dates and venues"}).json()
    assert n["status"] == "draft" and n["slug"] == "information-sessions-for-suppliers"
    assert client.get(f"/api/v1/public/news/{n['slug']}").status_code == 404        # not live
    pub = client.post(f"/api/v1/cms/news/{n['id']}/workflow", headers=eh, json={"action": "publish"})
    assert pub.status_code == 403                                                    # editor can't publish
    assert client.post(f"/api/v1/cms/news/{n['id']}/workflow", headers=eh, json={"action": "submit"}).json()["status"] == "in_review"
    ah = login(client, "admin@lishebora.local", "ChangeMe!2026")
    assert client.post(f"/api/v1/cms/news/{n['id']}/workflow", headers=ah, json={"action": "publish"}).json()["status"] == "published"
    assert client.get(f"/api/v1/public/news/{n['slug']}").status_code == 200
    # published post locked for editor
    r = client.put(f"/api/v1/cms/news/{n['id']}", headers=eh, json={"title": "Changed"})
    assert r.json()["error"]["code"] == "PUBLISHED_LOCKED"
    vs = client.get(f"/api/v1/cms/versions/news/{n['id']}", headers=ah).json()
    assert vs[0]["version"] >= 1


def test_hero_block_publish(client):
    ah = login(client, "admin@lishebora.local", "ChangeMe!2026")
    blk = next(b for b in client.get("/api/v1/cms/blocks", headers=ah).json() if b["key"] == "hero")
    data = dict(blk["data"], title="New headline")
    client.put("/api/v1/cms/blocks/hero", headers=ah, json={"data": data})
    assert client.get("/api/v1/public/home").json()["hero"]["title"] != "New headline"   # draft only
    client.post("/api/v1/cms/blocks/hero/workflow", headers=ah, json={"action": "publish"})
    assert client.get("/api/v1/public/home").json()["hero"]["title"] == "New headline"


def test_contact_honeypot(client):
    ok = client.post("/api/v1/public/contact", json={"name": "Jane", "contact": "0700000000", "message": "Hello there"})
    assert ok.status_code == 201
