"""Admin-managed public website (CMS). Editors draft & submit (cms:submit); approvers publish (cms:approve)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require
from app.core.errors import AppError
from app.models import ContactMessage, ContentStatus, ContentVersion, FaqItem, MediaAsset, NewsPost, Page, Resource, SiteBlock
from app.schemas.common import ORM, Msg
from app.services import audit, storage
from app.services.cms import save_version, slugify, transition, unique_slug

router = APIRouter(prefix="/cms", tags=["website CMS"])
NEWS_FIELDS = ["title", "category", "summary", "body", "cover_image", "cover_alt", "language"]
PAGE_FIELDS = ["title", "body", "show_in_nav", "language"]


class Flow(BaseModel):
    action: str = Field(description="submit | return | publish | unpublish | archive")
    note: str = ""


class NewsIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category: str = "Announcement"
    summary: str = ""
    body: str = ""
    cover_image: str = ""
    cover_alt: str = ""
    language: str = "en"
    slug: str | None = None


class NewsOut(ORM, NewsIn):
    id: uuid.UUID
    slug: str
    status: str
    version: int
    published_at: datetime | None
    updated_at: datetime
    review_note: str


class PageIn(BaseModel):
    title: str = Field(min_length=2)
    body: str = ""
    show_in_nav: bool = False
    language: str = "en"


class PageOut(ORM, PageIn):
    id: uuid.UUID
    slug: str
    status: str
    version: int
    published_at: datetime | None
    updated_at: datetime


class BlockIn(BaseModel):
    data: dict


class BlockOut(ORM):
    key: str
    data: dict
    published_data: dict
    status: str
    version: int
    updated_at: datetime


class FaqIn(BaseModel):
    question: str = Field(min_length=3)
    answer: str = Field(min_length=1)
    sort_order: int = 0
    language: str = "en"
    is_published: bool = True


class FaqOut(ORM, FaqIn):
    id: uuid.UUID


class ResourceOut(ORM):
    id: uuid.UUID
    title: str
    description: str
    file_name: str
    content_type: str
    size_bytes: int
    visibility: str
    language: str
    is_published: bool


# ---------------- news ----------------
@router.get("/news", response_model=list[NewsOut])
def news_list(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(NewsPost).order_by(NewsPost.updated_at.desc())).all()


@router.post("/news", response_model=NewsOut, status_code=201)
def news_create(body: NewsIn, request: Request, p: Principal = Depends(require("cms:create")), db: Session = Depends(get_db)):
    n = NewsPost(**body.model_dump(exclude={"slug"}), slug=unique_slug(db, NewsPost, slugify(body.slug or body.title)),
                 created_by=p.id)
    db.add(n)
    db.flush()
    save_version(db, "news", n, body.model_dump(), p)
    audit.record(db, action="CREATE", entity="cms_news", entity_id=n.id, user=p.user, after={"title": n.title}, request=request)
    db.commit()
    return n


@router.get("/news/{nid}", response_model=NewsOut)
def news_get(nid: uuid.UUID, p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    n = db.get(NewsPost, nid)
    if n is None:
        raise AppError(404, "NOT_FOUND", "Post not found.")
    return n


@router.put("/news/{nid}", response_model=NewsOut)
def news_update(nid: uuid.UUID, body: NewsIn, request: Request, p: Principal = Depends(require("cms:edit")),
                db: Session = Depends(get_db)):
    n = db.get(NewsPost, nid)
    if n is None:
        raise AppError(404, "NOT_FOUND", "Post not found.")
    if n.status == ContentStatus.published and not p.can("cms:approve"):
        raise AppError(409, "PUBLISHED_LOCKED", "Published posts can only be changed by an approver. Ask them to unpublish it first.")
    before = audit.snapshot(n, NEWS_FIELDS)
    for k, v in body.model_dump(exclude={"slug"}).items():
        setattr(n, k, v)
    if body.slug:
        n.slug = unique_slug(db, NewsPost, slugify(body.slug), exclude_id=n.id)
    n.updated_by = p.id
    save_version(db, "news", n, body.model_dump(), p)
    audit.record(db, action="UPDATE", entity="cms_news", entity_id=n.id, user=p.user, before=before,
                 after=body.model_dump(), request=request)
    db.commit()
    return n


@router.post("/news/{nid}/workflow", response_model=NewsOut)
def news_flow(nid: uuid.UUID, body: Flow, request: Request, p: Principal = Depends(require("cms:view")),
              db: Session = Depends(get_db)):
    n = db.get(NewsPost, nid)
    if n is None:
        raise AppError(404, "NOT_FOUND", "Post not found.")
    before = n.status.value
    transition(n, body.action, p, body.note)
    audit.record(db, action=body.action.upper(), entity="cms_news", entity_id=n.id, user=p.user,
                 before={"status": before}, after={"status": n.status.value}, reason=body.note, request=request)
    db.commit()
    return n


@router.get("/versions/{entity}/{eid}")
def versions(entity: str, eid: uuid.UUID, p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(ContentVersion).where(ContentVersion.entity == entity, ContentVersion.entity_id == eid)
                      .order_by(ContentVersion.version.desc())).all()
    return [{"version": r.version, "status": r.status, "created_at": r.created_at, "snapshot": r.snapshot} for r in rows]


# ---------------- pages ----------------
@router.get("/pages", response_model=list[PageOut])
def pages_list(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(Page).order_by(Page.title)).all()


@router.put("/pages/{slug}", response_model=PageOut)
def page_upsert(slug: str, body: PageIn, request: Request, p: Principal = Depends(require("cms:edit")),
                db: Session = Depends(get_db)):
    pg = db.scalar(select(Page).where(Page.slug == slugify(slug)))
    created = pg is None
    if created:
        if not p.can("cms:create"):
            raise AppError(403, "FORBIDDEN", "You do not have permission to create pages.")
        pg = Page(slug=slugify(slug), created_by=p.id, **body.model_dump())
        db.add(pg)
        db.flush()
    else:
        if pg.status == ContentStatus.published and not p.can("cms:approve"):
            raise AppError(409, "PUBLISHED_LOCKED", "Published pages can only be changed by an approver.")
        for k, v in body.model_dump().items():
            setattr(pg, k, v)
        pg.updated_by = p.id
    save_version(db, "page", pg, body.model_dump(), p)
    audit.record(db, action="CREATE" if created else "UPDATE", entity="cms_page", entity_id=pg.id, user=p.user,
                 after={"slug": pg.slug, "title": pg.title}, request=request)
    db.commit()
    return pg


@router.post("/pages/{slug}/workflow", response_model=PageOut)
def page_flow(slug: str, body: Flow, request: Request, p: Principal = Depends(require("cms:view")),
              db: Session = Depends(get_db)):
    pg = db.scalar(select(Page).where(Page.slug == slug))
    if pg is None:
        raise AppError(404, "NOT_FOUND", "Page not found.")
    before = pg.status.value
    transition(pg, body.action, p, body.note)
    audit.record(db, action=body.action.upper(), entity="cms_page", entity_id=pg.id, user=p.user,
                 before={"status": before}, after={"status": pg.status.value}, request=request)
    db.commit()
    return pg


# ---------------- homepage blocks (hero, stats) ----------------
@router.get("/blocks", response_model=list[BlockOut])
def blocks(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(SiteBlock).order_by(SiteBlock.key)).all()


@router.put("/blocks/{key}", response_model=BlockOut)
def block_save(key: str, body: BlockIn, request: Request, p: Principal = Depends(require("cms:edit")),
               db: Session = Depends(get_db)):
    b = db.scalar(select(SiteBlock).where(SiteBlock.key == key))
    if b is None:
        raise AppError(404, "NOT_FOUND", "Unknown block.")
    if key == "backgrounds":
        body.data = clean_backgrounds(db, body.data)
    if key == "site":
        allowed = ("phone", "sms_code", "whatsapp", "email", "address", "hours", "languages")
        body.data = {k: str(body.data.get(k) or "").strip()[:200] for k in allowed}
    if key in ("hero", "stats"):
        body.data = {**body.data, "styles": clean_styles(body.data.get("styles"))}
    if key == "hero":
        for f in ("cta_link", "cta2_link"):       # internal path (/opportunities) or an https link; anything else is dropped
            v = str(body.data.get(f) or "").strip()
            ok = (v.startswith("/") and not v.startswith("//")) or v.startswith("https://")
            body.data[f] = v[:300] if ok else ""
    b.data, b.updated_by = body.data, p.id
    if b.status == ContentStatus.published:
        b.status = ContentStatus.draft          # working copy differs from what is live
    save_version(db, "block", b, body.data, p)
    audit.record(db, action="UPDATE", entity="cms_block", entity_id=b.id, user=p.user, after={"key": key}, request=request)
    db.commit()
    return b


@router.post("/blocks/{key}/workflow", response_model=BlockOut)
def block_flow(key: str, body: Flow, request: Request, p: Principal = Depends(require("cms:view")),
               db: Session = Depends(get_db)):
    b = db.scalar(select(SiteBlock).where(SiteBlock.key == key))
    if b is None:
        raise AppError(404, "NOT_FOUND", "Unknown block.")
    transition(b, body.action, p, body.note)
    if b.status == ContentStatus.published:
        b.published_data = dict(b.data)
    audit.record(db, action=body.action.upper(), entity="cms_block", entity_id=b.id, user=p.user,
                 after={"key": key, "status": b.status.value}, request=request)
    db.commit()
    return b


# ---------------- FAQ ----------------
@router.get("/faq", response_model=list[FaqOut])
def faq_list(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(FaqItem).order_by(FaqItem.sort_order)).all()


@router.post("/faq", response_model=FaqOut, status_code=201)
def faq_create(body: FaqIn, request: Request, p: Principal = Depends(require("cms:create")), db: Session = Depends(get_db)):
    f = FaqItem(**body.model_dump(), created_by=p.id)
    db.add(f)
    db.flush()
    audit.record(db, action="CREATE", entity="cms_faq", entity_id=f.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return f


@router.put("/faq/{fid}", response_model=FaqOut)
def faq_update(fid: uuid.UUID, body: FaqIn, request: Request, p: Principal = Depends(require("cms:edit")),
               db: Session = Depends(get_db)):
    f = db.get(FaqItem, fid)
    if f is None:
        raise AppError(404, "NOT_FOUND", "Question not found.")
    if body.is_published and not f.is_published and not p.can("cms:approve"):
        raise AppError(403, "FORBIDDEN", "Publishing needs an approver.")
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    audit.record(db, action="UPDATE", entity="cms_faq", entity_id=f.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return f


@router.delete("/faq/{fid}", response_model=Msg)
def faq_delete(fid: uuid.UUID, request: Request, p: Principal = Depends(require("cms:approve")), db: Session = Depends(get_db)):
    f = db.get(FaqItem, fid)
    if f is None:
        raise AppError(404, "NOT_FOUND", "Question not found.")
    audit.record(db, action="DELETE", entity="cms_faq", entity_id=f.id, user=p.user,
                 before={"question": f.question}, request=request)
    db.delete(f)
    db.commit()
    return Msg(message="Question removed.")


# ---------------- resources (downloads) ----------------
@router.get("/resources", response_model=list[ResourceOut])
def res_list(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(Resource).order_by(Resource.sort_order, Resource.title)).all()


@router.post("/resources", response_model=ResourceOut, status_code=201)
async def res_upload(request: Request, title: str = Form(...), description: str = Form(""),
                     visibility: str = Form("public"), language: str = Form("en"), file: UploadFile = File(...),
                     p: Principal = Depends(require("cms:create")), db: Session = Depends(get_db)):
    if visibility not in ("public", "registered"):
        raise AppError(422, "VALIDATION_ERROR", "Visibility must be public or registered.")
    meta = await storage.save_upload(file, "cms")
    meta.pop("sha256")
    r = Resource(title=title, description=description, visibility=visibility, language=language,
                 is_published=p.can("cms:approve"), created_by=p.id, **meta)
    db.add(r)
    db.flush()
    audit.record(db, action="UPLOAD", entity="cms_resource", entity_id=r.id, user=p.user, after={"title": title}, request=request)
    db.commit()
    return r


@router.post("/resources/{rid}/publish", response_model=ResourceOut)
def res_publish(rid: uuid.UUID, request: Request, published: bool = True, p: Principal = Depends(require("cms:approve")),
                db: Session = Depends(get_db)):
    r = db.get(Resource, rid)
    if r is None:
        raise AppError(404, "NOT_FOUND", "File not found.")
    r.is_published = published
    audit.record(db, action="PUBLISH" if published else "UNPUBLISH", entity="cms_resource", entity_id=r.id,
                 user=p.user, request=request)
    db.commit()
    return r


# ---------------- contact messages ----------------
@router.get("/messages")
def messages(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(200)).all()
    return [{"id": m.id, "name": m.name, "contact": m.contact, "topic": m.topic, "message": m.message,
             "status": m.status, "created_at": m.created_at} for m in rows]


# ---------------- text styles (colour, bold, italic, size, font) ----------------
STYLE_FIELDS = {"eyebrow", "title", "subtitle", "cta_label", "cta2_label", "value", "label"}
STYLE_FONTS = {"aleo", "sans", "lato", "montserrat", "oswald", "merriweather", "poppins"}


def clean_styles(styles) -> dict:
    """Only known fields; colour as #RRGGBB; size 10-96 px; font from the allowed list; bold/italic true/false."""
    import re
    out = {}
    for field, st in (styles or {}).items() if isinstance(styles, dict) else []:
        if field not in STYLE_FIELDS or not isinstance(st, dict):
            continue
        c = {}
        for key in ("color", "bg"):          # bg = button background (buttons only)
            if isinstance(st.get(key), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", st[key]):
                c[key] = st[key].upper()
        for flag in ("bold", "italic"):
            if isinstance(st.get(flag), bool):
                c[flag] = st[flag]
        try:
            if st.get("size") not in (None, ""):
                c["size"] = max(10, min(96, int(st["size"])))
        except (TypeError, ValueError):
            pass
        if st.get("font") in STYLE_FONTS:
            c["font"] = st["font"]
        if c:
            out[field] = c
    return out


# ---------------- images & section backgrounds ----------------
# Places on the public website that can take a background image. Pages use "page:<slug>".
BACKGROUND_SLOTS = {
    "home_hero_media": "Homepage · picture or video beside the headline",
    "home_hero": "Homepage · top banner", "home_audiences": "Homepage · Who it is for", "home_how": "Homepage · How it works",
    "home_food": "Homepage · Food categories", "home_areas": "Homepage · Our reach (Kenya map)", "home_features": "Homepage · Why LisheBora",
    "home_band": "Homepage · Register banner (bottom)",
    "page:about": "About", "page:how-it-works": "How it works", "page:for-suppliers": "For suppliers", "page:for-schools": "For schools",
    "page:for-counties": "For counties & partners", "page:where-we-work": "Where we work", "page:opportunities": "Opportunities",
    "page:news": "News", "page:faq": "FAQ", "page:resources": "Resources", "page:contact": "Contact",
}


def clean_backgrounds(db: Session, data: dict) -> dict:
    """Keep only known slots that point at an uploaded image; overlay 0-90 %; position is a CSS keyword."""
    out = {}
    for slot, v in (data or {}).items():
        if slot == "home_hero_media" and isinstance(v, dict) and v.get("hidden"):
            out[slot] = {"hidden": True}      # no picture, video or animation beside the headline
            continue
        if slot not in BACKGROUND_SLOTS or not isinstance(v, dict) or not v.get("media_id"):
            continue
        try:
            mid = uuid.UUID(str(v["media_id"]))
        except ValueError:
            raise AppError(422, "VALIDATION_ERROR", f"{BACKGROUND_SLOTS[slot]}: unknown image.")
        m = db.get(MediaAsset, mid)
        if m is None:
            raise AppError(422, "VALIDATION_ERROR", f"{BACKGROUND_SLOTS[slot]}: the image no longer exists.")
        kind = "video" if m.content_type.startswith("video/") else "image"
        overlay = max(0, min(90, int(v.get("overlay", 55))))
        pos = v.get("position", "center") if v.get("position") in ("center", "top", "bottom", "left", "right") else "center"
        out[slot] = {"media_id": str(mid), "url": f"/api/v1/public/media/{mid}", "overlay": overlay, "position": pos,
                     "kind": kind, "alt": m.alt or m.title}
    return out


class MediaOut(ORM):
    id: uuid.UUID
    title: str
    alt: str
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


@router.get("/backgrounds/slots")
def background_slots(p: Principal = Depends(require("cms:view"))):
    return [{"key": k, "label": v} for k, v in BACKGROUND_SLOTS.items()]


@router.get("/media", response_model=list[MediaOut])
def media_list(p: Principal = Depends(require("cms:view")), db: Session = Depends(get_db)):
    return db.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()


@router.post("/media", response_model=MediaOut, status_code=201)
async def media_upload(request: Request, title: str = Form(""), alt: str = Form(""), file: UploadFile = File(...),
                       p: Principal = Depends(require("cms:create")), db: Session = Depends(get_db)):
    meta = await storage.save_upload(file, "media", media=True)
    meta.pop("sha256")
    m = MediaAsset(title=(title or meta["file_name"])[:200], alt=alt[:300], created_by=p.id, **meta)
    db.add(m)
    db.flush()
    audit.record(db, action="UPLOAD", entity="cms_media", entity_id=m.id, user=p.user, after={"title": m.title}, request=request)
    db.commit()
    return m


@router.delete("/media/{mid}", response_model=Msg)
def media_delete(mid: uuid.UUID, request: Request, p: Principal = Depends(require("cms:approve")), db: Session = Depends(get_db)):
    m = db.get(MediaAsset, mid)
    if m is None:
        raise AppError(404, "NOT_FOUND", "Image not found.")
    b = db.scalar(select(SiteBlock).where(SiteBlock.key == "backgrounds"))
    used = [BACKGROUND_SLOTS.get(k, k) for d in ((b.data or {}), (b.published_data or {})) if b for k, v in d.items()
            if isinstance(v, dict) and v.get("media_id") == str(mid)]
    if used:
        raise AppError(409, "IMAGE_IN_USE", "This image is used as a background: " + ", ".join(sorted(set(used))) + ". Remove it there first.")
    db.delete(m)
    audit.record(db, action="DELETE", entity="cms_media", entity_id=mid, user=p.user, before={"title": m.title}, request=request)
    db.commit()
    return Msg(message="Image deleted.")
