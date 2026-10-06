import uuid

import jwt
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import REFRESH_COOKIE, Principal, current_principal, load_principal
from app.core.errors import AppError
from app.core.security import create_token, decode_token, hash_password, password_problems, verify_password
from app.core.timeutil import utcnow
from app.models import (AuthSession, Organization, OrgType, OtpPurpose, Role, Supplier, SupplierStatus,
                        SupplierType, User, UserRole, UserStatus)
from app.schemas.auth import (ChangePasswordIn, ForgotIn, LoginIn, MeOut, MfaIn, OtpLoginIn, OtpRequestIn,
                              ProfileIn, RefreshIn, ResendIn, SupplierRegisterIn, RegisterOut,
                              ResetIn, RoleGrant, SessionOut, TokenOut, VerifyPhoneIn)
from app.schemas.common import Msg
from app.services import audit, otp
from app.services.menu import menu_for
from app.services.admin_access import is_admin_account, not_an_admin, use_admin_sign_in
from app.services.auth import (check_password_login, clear_cookies, ensure_can_sign_in, find_user, needs_mfa,
                               rotate, start_session)
from app.services.notify import mask_phone

router = APIRouter(prefix="/auth", tags=["auth"])
dev = lambda code: code if settings.debug else None  # noqa: E731


def _pw_ok(pw: str):
    probs = password_problems(pw)
    if probs:
        raise AppError(422, "WEAK_PASSWORD", " ".join(probs), [{"field": "password", "message": m} for m in probs])


def _password_sign_in(db: Session, user: User, request: Request, response: Response, portal: str) -> TokenOut:
    if portal == "admin" or needs_mfa(user):
        code = otp.issue(db, user, OtpPurpose.mfa)
        db.commit()
        return TokenOut(mfa_required=True, mfa_token=create_token(user.id, "mfa", settings.mfa_token_minutes, {"portal": portal}),
                        sent_to=mask_phone(user.phone) or user.email, dev_code=dev(code))
    return TokenOut(**start_session(db, user, request, response))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Sign-in for schools, counties, suppliers and all operational staff. Administrator accounts are refused."""
    user = check_password_login(db, body.identifier, body.password, request)
    if is_admin_account(user):
        raise use_admin_sign_in()
    return _password_sign_in(db, user, request, response, "app")


@router.post("/admin/login", response_model=TokenOut)
def admin_login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Separate sign-in for Super Administrators and Administrators. Two-step verification is always required."""
    user = check_password_login(db, body.identifier, body.password, request)
    if not is_admin_account(user):
        audit.record(db, action="ADMIN_LOGIN_REFUSED", entity="user", entity_id=user.id, user=user, request=request)
        db.commit()
        raise not_an_admin()
    return _password_sign_in(db, user, request, response, "admin")


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(body: MfaIn, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        data = decode_token(body.mfa_token, "mfa")
    except jwt.PyJWTError:
        raise AppError(401, "MFA_EXPIRED", "Your sign-in attempt expired. Please sign in again.")
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None:
        raise AppError(401, "MFA_EXPIRED", "Please sign in again.")
    if is_admin_account(user) != (data.get("portal") == "admin"):   # the code must come from the right sign-in page
        raise use_admin_sign_in() if is_admin_account(user) else not_an_admin()
    otp.verify(db, user, OtpPurpose.mfa, body.code)
    return TokenOut(**start_session(db, user, request, response, reason="LOGIN_ADMIN" if data.get("portal") == "admin" else "LOGIN_MFA"))


@router.post("/otp/request", response_model=TokenOut)
def otp_request(body: OtpRequestIn, db: Session = Depends(get_db)):
    """Passwordless sign-in by SMS. Always answers the same way to avoid revealing registered numbers."""
    user = db.scalar(select(User).where(User.phone == body.phone))
    code = None
    if user is not None and user.status == UserStatus.active and not is_admin_account(user):   # no SMS-only sign-in for admins
        code = otp.issue(db, user, OtpPurpose.login)
        db.commit()
    return TokenOut(sent_to=mask_phone(body.phone), dev_code=dev(code))


@router.post("/otp/login", response_model=TokenOut)
def otp_login(body: OtpLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.phone == body.phone))
    if user is None:
        raise AppError(400, "OTP_INVALID", "The code is not correct.")
    if is_admin_account(user):
        raise use_admin_sign_in()
    ensure_can_sign_in(user)
    otp.verify(db, user, OtpPurpose.login, body.code)
    return TokenOut(**start_session(db, user, request, response, reason="LOGIN_OTP"))


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AppError(401, "SESSION_EXPIRED", "Please sign in.")
    return TokenOut(**rotate(db, token, request, response))


@router.post("/logout", response_model=Msg)
def logout(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    from app.core.security import sha256
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if token:
        s = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == sha256(token)))
        if s and not s.revoked_at:
            s.revoked_at = utcnow()
            db.commit()
    clear_cookies(response)
    return Msg(message="Signed out.")


@router.post("/register/supplier", response_model=RegisterOut, status_code=201)
def register_supplier(body: SupplierRegisterIn, request: Request, db: Session = Depends(get_db)):
    """Self-registration for farmers, groups/cooperatives, aggregators and traders (FR-SUP-01/02/03)."""
    _pw_ok(body.password)
    county = db.get(Organization, body.county_id)
    if county is None or county.type != OrgType.county:
        raise AppError(422, "VALIDATION_ERROR", "Choose a valid county.", [{"field": "county_id", "message": "Unknown county"}])
    existing = db.scalar(select(User).where(User.phone == body.phone))
    if existing and existing.status != UserStatus.pending_verification:
        raise AppError(409, "PHONE_IN_USE", "This mobile number is already registered. Sign in instead.")
    if body.email and db.scalar(select(User).where(User.email == body.email.lower(), User.phone != body.phone)):
        raise AppError(409, "EMAIL_IN_USE", "This email is already registered.")
    if existing:  # restart an unfinished registration
        db.delete(existing)
        db.flush()

    stype = SupplierType("cooperative" if body.account_type == "cooperative" else body.account_type)
    org = Organization(type=OrgType.supplier, name=body.legal_name, parent_id=county.id,
                       code=f"SUP-{uuid.uuid4().hex[:10].upper()}")
    db.add(org)
    db.flush()
    user = User(full_name=body.contact_name, phone=body.phone, email=body.email.lower() if body.email else None,
                password_hash=hash_password(body.password), status=UserStatus.pending_verification,
                preferred_language=body.sms_language)
    db.add(user)
    db.flush()
    group = stype in (SupplierType.cooperative, SupplierType.farmer_group)
    role_key = "farmer_group" if group else ("aggregator" if stype == SupplierType.aggregator else "supplier")
    role = db.scalar(select(Role).where(Role.key == role_key)) or db.scalar(select(Role).where(Role.key == "supplier"))
    db.add(UserRole(user_id=user.id, role_id=role.id, org_id=org.id))
    sup = Supplier(organization_id=org.id, county_id=county.id, supplier_type=stype, legal_name=body.legal_name,
                   registration_no=body.registration_no, kra_pin=body.kra_pin, phone=body.phone,
                   email=body.email or "", sub_county=body.sub_county, commodities=body.commodities,
                   members_count=body.members_count, sms_language=body.sms_language,
                   inclusion_claim=body.inclusion.model_dump() if body.inclusion_consent else {},
                   inclusion_consent=body.inclusion_consent, status=SupplierStatus.draft, created_by=user.id)
    db.add(sup)
    db.flush()
    audit.record(db, action="REGISTER", entity="supplier", entity_id=sup.id, user=None,
                 after={"legal_name": sup.legal_name, "type": stype.value, "county": county.name}, request=request)
    code = otp.issue(db, user, OtpPurpose.verify_phone)
    db.commit()
    return RegisterOut(user_id=user.id, supplier_id=sup.id, sent_to=mask_phone(user.phone), dev_code=dev(code))


@router.post("/register/resend", response_model=TokenOut)
def resend_verification(body: ResendIn, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None or user.status != UserStatus.pending_verification:
        return TokenOut()
    code = otp.issue(db, user, OtpPurpose.verify_phone)
    db.commit()
    return TokenOut(sent_to=mask_phone(user.phone), dev_code=dev(code))


@router.post("/verify-phone", response_model=TokenOut)
def verify_phone(body: VerifyPhoneIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None or user.status != UserStatus.pending_verification:
        raise AppError(400, "NOTHING_TO_VERIFY", "This account is already verified. Sign in instead.")
    otp.verify(db, user, OtpPurpose.verify_phone, body.code)
    user.status = UserStatus.active
    sup = db.scalar(select(Supplier).where(Supplier.created_by == user.id))
    if sup and sup.status == SupplierStatus.draft:
        sup.status = SupplierStatus.submitted   # enters the prequalification queue
        audit.record(db, action="SUBMIT", entity="supplier", entity_id=sup.id, user=user,
                     before={"status": "draft"}, after={"status": "submitted"}, request=request)
    return TokenOut(**start_session(db, user, request, response, reason="LOGIN_FIRST"))


@router.post("/password/forgot", response_model=TokenOut)
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    user = find_user(db, body.identifier)
    code = None
    if user is not None and user.status == UserStatus.active:
        code = otp.issue(db, user, OtpPurpose.reset_password)
        db.commit()
    return TokenOut(sent_to="your registered phone or email", dev_code=dev(code))


@router.post("/password/reset", response_model=Msg)
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    user = find_user(db, body.identifier)
    if user is None:
        raise AppError(400, "OTP_INVALID", "The code is not correct.")
    _pw_ok(body.new_password)
    otp.verify(db, user, OtpPurpose.reset_password, body.code)
    user.password_hash = hash_password(body.new_password)
    user.failed_logins, user.locked_until = 0, None
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        s.revoked_at = utcnow()   # sign out everywhere
    audit.record(db, action="PASSWORD_RESET", entity="user", entity_id=user.id, user=user, request=request)
    db.commit()
    return Msg(message="Password updated. Please sign in.")


@router.get("/me", response_model=MeOut)
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    grants = []
    for ur in p.user.roles:
        if not ur.is_active:
            continue
        org = db.get(Organization, ur.org_id) if ur.org_id else None
        grants.append(RoleGrant(role=ur.role.key, role_name=ur.role.name, org_id=ur.org_id,
                                org_name=org.name if org else None, org_type=org.type.value if org else None))
    sup = None
    for ur in p.user.roles:
        if ur.org_id:
            s = db.scalar(select(Supplier.id).where(Supplier.organization_id == ur.org_id))
            if s:
                sup = s
                break
    u = p.user
    return MeOut(id=u.id, full_name=u.full_name, email=u.email, phone=u.phone, status=u.status.value,
                 preferred_language=u.preferred_language, mfa_enabled=needs_mfa(u), roles=grants,
                 permissions=sorted(p.grants), supplier_id=sup, is_admin=is_admin_account(u),
                 is_super_admin="super_admin" in {g.role for g in grants}, menu=menu_for(db, u))


@router.patch("/me", response_model=Msg)
def update_me(body: ProfileIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    u = db.get(User, p.id)
    if body.full_name:
        u.full_name = body.full_name
    if body.preferred_language:
        u.preferred_language = body.preferred_language
    db.commit()
    return Msg(message="Profile updated.")


@router.post("/password/change", response_model=Msg)
def change_password(body: ChangePasswordIn, request: Request, p: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)):
    u = db.get(User, p.id)
    if not verify_password(body.current_password, u.password_hash):
        raise AppError(400, "INVALID_CREDENTIALS", "Your current password is not correct.")
    _pw_ok(body.new_password)
    u.password_hash = hash_password(body.new_password)
    audit.record(db, action="PASSWORD_CHANGE", entity="user", entity_id=u.id, user=p.user, request=request)
    db.commit()
    return Msg(message="Password changed.")


@router.get("/sessions", response_model=list[SessionOut])
def sessions(request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from app.core.security import sha256
    cur = request.cookies.get(REFRESH_COOKIE)
    cur_hash = sha256(cur) if cur else None
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == p.id, AuthSession.revoked_at.is_(None))
                      .order_by(AuthSession.last_used_at.desc())).all()
    return [SessionOut(id=s.id, user_agent=s.user_agent, ip=s.ip, created_at=s.created_at.isoformat(),
                       last_used_at=s.last_used_at.isoformat(), current=s.refresh_hash == cur_hash) for s in rows]


@router.delete("/sessions/{session_id}", response_model=Msg)
def revoke_session(session_id: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = db.get(AuthSession, session_id)
    if s is None or s.user_id != p.id:
        raise AppError(404, "NOT_FOUND", "Session not found.")
    s.revoked_at = utcnow()
    db.commit()
    return Msg(message="Session signed out.")
