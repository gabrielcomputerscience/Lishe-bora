"""Website images: upload, use as a section/page background, publish, serve publicly, protect images in use."""
import base64

from tests.conftest import login

A = "/api/v1"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_backgrounds(client):
    ah = login(client, "administrator@demo.lishebora", "Demo!2026pass")
    assert client.post(f"{A}/cms/media", headers=ah, files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")}).status_code == 415
    vid = client.post(f"{A}/cms/media", headers=ah, files={"file": ("v.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "video/mp4")}).json()
    assert vid["content_type"] == "video/mp4"
    ok = client.put(f"{A}/cms/blocks/backgrounds", headers=ah, json={"data": {"page:about": {"media_id": vid["id"], "overlay": 40}}}).json()
    assert ok["data"]["page:about"]["kind"] == "video"          # videos can be section and page backgrounds too
    m = client.post(f"{A}/cms/media", headers=ah, data={"title": "Farmers at a market", "alt": "Farmers selling maize"},
                    files={"file": ("m.png", PNG, "image/png")})
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    slots = {s["key"] for s in client.get(f"{A}/cms/backgrounds/slots", headers=ah).json()}
    assert {"home_hero", "page:where-we-work"} <= slots
    data = {"home_hero": {"media_id": mid, "overlay": 150, "position": "top"}, "bogus": {"media_id": mid}, "page:faq": {"media_id": ""},
            "home_hero_media": {"media_id": vid["id"]}}
    b = client.put(f"{A}/cms/blocks/backgrounds", headers=ah, json={"data": data}).json()
    assert sorted(b["data"]) == ["home_hero", "home_hero_media"] and b["data"]["home_hero"]["overlay"] == 90
    assert b["data"]["home_hero_media"]["kind"] == "video"
    off = client.put(f"{A}/cms/blocks/backgrounds", headers=ah, json={"data": {**data, "home_hero_media": {"hidden": True}}}).json()
    assert off["data"]["home_hero_media"] == {"hidden": True}
    client.put(f"{A}/cms/blocks/backgrounds", headers=ah, json={"data": data})
    assert client.get(f"{A}/public/backgrounds").json() == {}                   # not live until published
    client.post(f"{A}/cms/blocks/backgrounds/workflow", headers=ah, json={"action": "publish"})
    live = client.get(f"{A}/public/backgrounds").json()["home_hero"]
    img = client.get(live["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == PNG
    assert client.delete(f"{A}/cms/media/{mid}", headers=ah).json()["error"]["code"] == "IMAGE_IN_USE"
    # editors can upload but only approvers delete
    eh = login(client, "editor@demo.lishebora", "Demo!2026pass")
    assert client.delete(f"{A}/cms/media/{mid}", headers=eh).status_code == 403


def test_text_styles_are_validated(client):
    ah = login(client, "administrator@demo.lishebora", "Demo!2026pass")
    data = {"title": "Nourishing learners", "styles": {
        "title": {"color": "#2f4520", "bold": True, "italic": False, "size": 300, "font": "oswald"},
        "subtitle": {"color": "red; background:url(x)", "font": "Comic Sans", "size": "abc"},
        "bogus": {"color": "#FFFFFF"}}}
    b = client.put(f"{A}/cms/blocks/hero", headers=ah, json={"data": data}).json()
    assert b["data"]["styles"] == {"title": {"color": "#2F4520", "bold": True, "italic": False, "size": 96, "font": "oswald"}}
    client.post(f"{A}/cms/blocks/hero/workflow", headers=ah, json={"action": "publish"})
    assert client.get(f"{A}/public/home").json()["hero"]["styles"]["title"]["font"] == "oswald"


def test_hero_second_button(client):
    ah = login(client, "administrator@demo.lishebora", "Demo!2026pass")
    data = {"cta2_label": "See tenders", "cta2_link": "/opportunities", "cta_link": "javascript:alert(1)",
            "styles": {"cta2_label": {"color": "#2F4520", "bg": "#F9B916", "bold": True}}}
    b = client.put(f"{A}/cms/blocks/hero", headers=ah, json={"data": data}).json()["data"]
    assert b["cta2_link"] == "/opportunities" and b["cta_link"] == ""
    assert b["styles"]["cta2_label"] == {"color": "#2F4520", "bg": "#F9B916", "bold": True}
