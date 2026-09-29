"""Sealed bids (FR-PRO-05): payloads are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) and can only be
decrypted by the formal bid-opening step after the closing time. The key never leaves server config.
Losing BID_ENCRYPTION_KEY makes unopened bids unreadable — back it up with the database secrets."""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import AppError


def _fernet() -> Fernet:
    key = settings.bid_encryption_key
    if not key:  # development fallback, deterministic per JWT secret
        key = base64.urlsafe_b64encode(hashlib.sha256((settings.jwt_secret + "|bids").encode()).digest()).decode()
    return Fernet(key.encode())


def seal(payload: dict) -> tuple[str, str]:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return _fernet().encrypt(raw).decode(), hashlib.sha256(raw).hexdigest()


def unseal(token: str, expected_sha256: str | None = None) -> dict:
    try:
        raw = _fernet().decrypt(token.encode())
    except InvalidToken:
        raise AppError(500, "SEAL_BROKEN", "A sealed bid could not be decrypted. Check BID_ENCRYPTION_KEY.")
    if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise AppError(500, "SEAL_TAMPERED", "A sealed bid failed its integrity check.")
    return json.loads(raw)
