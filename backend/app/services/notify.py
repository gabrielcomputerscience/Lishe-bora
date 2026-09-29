"""SMS and email delivery (SRS §10.2) through a provider-agnostic outbox.

NOTIFY_BACKEND=console        development: messages are printed and marked sent (default)
NOTIFY_BACKEND=africastalking SMS through Africa's Talking (AT_USERNAME, AT_API_KEY, AT_SENDER_ID; AT_SANDBOX=true for tests)
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM  email through any SMTP relay

Every message is written to `outbound_messages` in the caller's transaction, so nothing is lost if the provider is down:
sign-in codes are attempted immediately, everything else is sent by the worker (`python -m app.jobs send`), with retries."""
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models import OutboundMessage

log = logging.getLogger("lishebora.notify")
MAX_ATTEMPTS = 5


class DeliveryError(Exception):
    pass


def _console_sms(to: str, text: str) -> str:
    log.warning("[SMS → %s] %s", to, text)
    print(f"[SMS -> {to}] {text}", flush=True)
    return "console"


def _console_email(to: str, subject: str, text: str) -> str:
    log.warning("[EMAIL → %s] %s: %s", to, subject, text)
    print(f"[EMAIL -> {to}] {subject}: {text}", flush=True)
    return "console"


def _normalise_ke(phone: str) -> str:
    p = phone.replace(" ", "")
    if p.startswith("0") and len(p) == 10:
        return "+254" + p[1:]
    if p.startswith("254"):
        return "+" + p
    return p


def _africastalking_sms(to: str, text: str) -> str:
    host = "https://api.sandbox.africastalking.com" if settings.at_sandbox else "https://api.africastalking.com"
    data = {"username": settings.at_username, "to": _normalise_ke(to), "message": text}
    if settings.at_sender_id:
        data["from"] = settings.at_sender_id
    try:
        r = httpx.post(f"{host}/version1/messaging", data=data, timeout=15,
                       headers={"apiKey": settings.at_api_key, "Accept": "application/json"})
        r.raise_for_status()
        rec = (r.json().get("SMSMessageData", {}).get("Recipients") or [{}])[0]
    except (httpx.HTTPError, ValueError) as e:
        raise DeliveryError(f"Africa's Talking: {e}") from e
    if rec.get("status") not in ("Success", "Sent", "Queued"):
        raise DeliveryError(f"Africa's Talking: {rec.get('status') or 'no recipient status'}")
    return rec.get("messageId", "")


def _smtp_email(to: str, subject: str, text: str) -> str:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = settings.smtp_from, to, subject
    m.set_content(text + "\n\n— LisheBora · STEP School Feeding Project")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            if settings.smtp_starttls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(m)
    except (smtplib.SMTPException, OSError) as e:
        raise DeliveryError(f"SMTP: {e}") from e
    return m.get("Message-ID", "") or "smtp"


def provider_for(channel: str) -> str:
    if channel == "sms":
        return "africastalking" if settings.notify_backend == "africastalking" else "console"
    return "smtp" if settings.smtp_host else "console"


def _send(msg: OutboundMessage) -> str:
    prov = provider_for(msg.channel)
    msg.provider = prov
    if msg.channel == "sms":
        return _africastalking_sms(msg.to, msg.body) if prov == "africastalking" else _console_sms(msg.to, msg.body)
    return _smtp_email(msg.to, msg.subject, msg.body) if prov == "smtp" else _console_email(msg.to, msg.subject, msg.body)


def attempt(msg: OutboundMessage) -> bool:
    now = utcnow()
    msg.attempts += 1
    try:
        msg.provider_ref = (_send(msg) or "")[:120]
    except DeliveryError as e:
        msg.last_error = str(e)[:500]
        msg.status = "failed" if msg.attempts >= MAX_ATTEMPTS else "queued"
        msg.next_attempt_at = now + timedelta(minutes=2 ** msg.attempts)
        log.error("Delivery failed (%s, attempt %s): %s", msg.channel, msg.attempts, e)
        return False
    msg.status, msg.sent_at, msg.next_attempt_at, msg.last_error = "sent", now, None, ""
    if msg.sensitive:
        msg.body = "[redacted after delivery]"
    return True


def deliver(db: Session, channel: str, to: str, body: str, subject: str = "", *, sensitive: bool = False, urgent: bool = False) -> OutboundMessage:
    msg = OutboundMessage(channel=channel, to=to, subject=subject[:200], body=body, sensitive=sensitive, status="queued", attempts=0, last_error="", provider="", provider_ref="",
                          created_at=utcnow(), next_attempt_at=utcnow())
    db.add(msg)
    if urgent or provider_for(channel) == "console":
        attempt(msg)
    return msg


def sms(db: Session, phone: str, text: str, **kw) -> OutboundMessage:
    return deliver(db, "sms", phone, text[:480], **kw)


def email(db: Session, to: str, subject: str, text: str, **kw) -> OutboundMessage:
    return deliver(db, "email", to, text, subject, **kw)


def send_queued(db: Session, limit: int = 200) -> dict:
    """Worker step: send everything due. Safe to run from several workers (rows are claimed with SKIP LOCKED on PostgreSQL)."""
    q = (select(OutboundMessage).where(OutboundMessage.status == "queued",
                                       or_(OutboundMessage.next_attempt_at.is_(None), OutboundMessage.next_attempt_at <= utcnow()))
         .order_by(OutboundMessage.created_at).limit(limit))
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    sent = failed = 0
    for m in db.scalars(q).all():
        if attempt(m):
            sent += 1
        else:
            failed += 1
        db.commit()
    return {"sent": sent, "failed": failed}


def mask_phone(p: str | None) -> str:
    if not p:
        return ""
    return p[:3] + "•" * max(0, len(p) - 6) + p[-3:]
