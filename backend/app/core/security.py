import hashlib
import secrets
import uuid
from datetime import timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.timeutil import utcnow


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def password_problems(pw: str) -> list[str]:
    p = []
    if len(pw) < settings.password_min_length:
        p.append(f"Use at least {settings.password_min_length} characters.")
    if pw.lower() == pw or pw.upper() == pw:
        p.append("Mix upper- and lower-case letters.")
    if not any(c.isdigit() for c in pw):
        p.append("Include at least one number.")
    return p


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_token(sub: uuid.UUID, kind: str, minutes: int, extra: dict | None = None) -> str:
    now = utcnow()
    payload = {"sub": str(sub), "typ": kind, "iat": now, "exp": now + timedelta(minutes=minutes), "jti": secrets.token_hex(8)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, kind: str) -> dict:
    data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if data.get("typ") != kind:
        raise jwt.InvalidTokenError("wrong token type")
    return data
