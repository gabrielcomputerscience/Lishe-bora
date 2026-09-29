"""File storage. Local disk in development; swap for S3-compatible storage in production (SRS §9.4).
Files are stored by opaque key, never by user-supplied path."""
import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError

MAGIC = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png"}


def _sniff(head: bytes) -> str | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    for sig, ct in MAGIC.items():
        if head.startswith(sig):
            return ct
    return None


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/webm"}


async def save_upload(file: UploadFile, folder: str, images_only: bool = False, media: bool = False) -> dict:
    """media=True: website images and short videos (MP4/WebM, up to MEDIA_MAX_MB)."""
    if media:
        allowed = IMAGE_TYPES | VIDEO_TYPES
    else:
        allowed = IMAGE_TYPES if images_only else {t.strip() for t in settings.allowed_upload_types.split(",")}
    limit = settings.media_max_mb if media else settings.max_upload_mb
    data = await file.read(limit * 1024 * 1024 + 1)
    if len(data) > limit * 1024 * 1024:
        raise AppError(413, "FILE_TOO_LARGE", f"Files must be under {limit} MB.")
    if not data:
        raise AppError(400, "FILE_EMPTY", "The file is empty.")
    ct = _sniff(data[:12])
    if ct is None or ct not in allowed:
        raise AppError(415, "FILE_TYPE", "Upload a JPG, PNG or WebP image, or an MP4 or WebM video." if media
                       else "Upload a JPG, PNG or WebP image." if images_only else "Upload a PDF, JPG or PNG file.")
    # TODO(production): malware scan hook here (SRS §10.1 Documents)
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm"}[ct]
    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"file_key": key, "file_name": (file.filename or "upload")[:200], "content_type": ct,
            "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def open_path(key: str) -> Path:
    base = Path(settings.storage_dir).resolve()
    p = (base / key).resolve()
    if base not in p.parents or not p.is_file():
        raise AppError(404, "NOT_FOUND", "File not found.")
    return p
