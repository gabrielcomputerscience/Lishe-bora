from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import new_otp, sha256
from app.core.timeutil import as_utc, utcnow
from app.models import OtpCode, OtpPurpose, User
from app.services import notify

TEXT = {
    OtpPurpose.verify_phone: "Your LisheBora verification code is {code}. It expires in {m} minutes.",
    OtpPurpose.login: "Your LisheBora sign-in code is {code}. Do not share it.",
    OtpPurpose.mfa: "Your LisheBora security code is {code}. Do not share it.",
    OtpPurpose.reset_password: "Your LisheBora password reset code is {code}.",
}


def issue(db: Session, user: User, purpose: OtpPurpose) -> str:
    """Invalidate previous codes for this purpose, create a new one and send it. Returns the code (dev only)."""
    now = utcnow()
    db.execute(update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.purpose == purpose,
                                     OtpCode.consumed_at.is_(None)).values(consumed_at=now))
    code = new_otp()
    db.add(OtpCode(user_id=user.id, purpose=purpose, code_hash=sha256(code), created_at=now,
                   expires_at=now + timedelta(minutes=settings.otp_minutes)))
    text = TEXT[purpose].format(code=code, m=settings.otp_minutes)
    if user.phone:
        notify.sms(db, user.phone, text, sensitive=True, urgent=True)
    elif user.email:
        notify.email(db, user.email, "LisheBora code", text, sensitive=True, urgent=True)
    return code


def verify(db: Session, user: User, purpose: OtpPurpose, code: str) -> None:
    otp = db.scalar(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.purpose == purpose,
                                          OtpCode.consumed_at.is_(None)).order_by(OtpCode.created_at.desc()))
    if otp is None or as_utc(otp.expires_at) < utcnow():
        raise AppError(400, "OTP_EXPIRED", "This code has expired. Request a new one.")
    if otp.attempts >= settings.otp_max_attempts:
        raise AppError(429, "OTP_LOCKED", "Too many attempts. Request a new code.")
    if sha256(code.strip()) != otp.code_hash:
        otp.attempts += 1
        db.commit()
        raise AppError(400, "OTP_INVALID", "The code is not correct.")
    otp.consumed_at = utcnow()
