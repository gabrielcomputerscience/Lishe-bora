from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import ACCESS_COOKIE, REFRESH_COOKIE
from app.core.errors import AppError
from app.core.security import create_token, new_opaque_token, sha256, verify_password
from app.core.timeutil import as_utc, utcnow
from app.models import AuthSession, User, UserStatus
from app.schemas.auth import clean_identifier
from app.services import audit


def find_user(db: Session, identifier: str) -> User | None:
    try:
        kind, value = clean_identifier(identifier)
    except ValueError:
        return None
    col = User.email if kind == "email" else User.phone
    return db.scalar(select(User).where(col == value))


def needs_mfa(user: User) -> bool:
    return user.mfa_enabled or any(ur.role.requires_mfa for ur in user.roles if ur.is_active)


def check_password_login(db: Session, identifier: str, password: str, request: Request) -> User:
    user = find_user(db, identifier)
    generic = AppError(401, "INVALID_CREDENTIALS", "Email/phone or password is not correct.")
    if user is None:
        verify_password(password, "$2b$12$" + "x" * 53)  # equalise timing
        raise generic
    now = utcnow()
    if user.locked_until and as_utc(user.locked_until) > now:
        raise AppError(423, "ACCOUNT_LOCKED", "Too many failed attempts. Try again later or reset your password.")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
            audit.record(db, action="LOCKOUT", entity="user", entity_id=user.id, user=user, request=request)
        db.commit()
        raise generic
    ensure_can_sign_in(user)
    return user


def ensure_can_sign_in(user: User):
    if user.status == UserStatus.pending_verification:
        raise AppError(403, "PHONE_NOT_VERIFIED", "Verify your phone number to finish creating your account.",
                       [{"user_id": str(user.id)}])
    if user.status != UserStatus.active:
        raise AppError(403, "ACCOUNT_INACTIVE", "This account is not active. Contact the helpdesk.")


def start_session(db: Session, user: User, request: Request, response: Response, reason="LOGIN") -> dict:
    now = utcnow()
    refresh = new_opaque_token()
    db.add(AuthSession(user_id=user.id, refresh_hash=sha256(refresh),
                       user_agent=request.headers.get("user-agent", "")[:300],
                       ip=request.client.host if request.client else "", created_at=now, last_used_at=now,
                       expires_at=now + timedelta(days=settings.refresh_token_days)))
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    audit.record(db, action=reason, entity="user", entity_id=user.id, user=user, request=request)
    db.commit()
    access = create_token(user.id, "access", settings.access_token_minutes)
    set_cookies(response, access, refresh)
    return {"access_token": access, "refresh_token": refresh}


def rotate(db: Session, refresh: str, request: Request, response: Response) -> dict:
    s = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == sha256(refresh)))
    now = utcnow()
    if s is None or s.revoked_at or as_utc(s.expires_at) < now:
        clear_cookies(response)
        raise AppError(401, "SESSION_EXPIRED", "Your session has ended. Please sign in again.")
    user = db.get(User, s.user_id)
    if user is None or user.status != UserStatus.active:
        raise AppError(401, "SESSION_EXPIRED", "Your session has ended. Please sign in again.")
    new_refresh = new_opaque_token()
    s.refresh_hash, s.last_used_at = sha256(new_refresh), now
    db.commit()
    access = create_token(user.id, "access", settings.access_token_minutes)
    set_cookies(response, access, new_refresh)
    return {"access_token": access, "refresh_token": new_refresh}


def set_cookies(response: Response, access: str, refresh: str):
    common = dict(httponly=True, secure=settings.cookie_secure, samesite="lax")
    response.set_cookie(ACCESS_COOKIE, access, max_age=settings.access_token_minutes * 60, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=settings.refresh_token_days * 86400,
                        path="/api/v1/auth", **common)


def clear_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
