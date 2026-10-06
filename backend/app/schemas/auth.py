import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import PhoneMixin, normalize_phone


class LoginIn(BaseModel):
    identifier: str = Field(description="Email or mobile number")
    password: str


class TokenOut(BaseModel):
    """Tokens are also set as httpOnly cookies. Bodies carry them for mobile / API clients."""
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None
    sent_to: str | None = None
    dev_code: str | None = None   # only when DEBUG=true


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=6)


class OtpRequestIn(PhoneMixin):
    phone: str


class OtpLoginIn(PhoneMixin):
    phone: str
    code: str = Field(min_length=6, max_length=6)


class RefreshIn(BaseModel):
    refresh_token: str | None = None


class ForgotIn(BaseModel):
    identifier: str


class ResetIn(BaseModel):
    identifier: str
    code: str = Field(min_length=6, max_length=6)
    new_password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class Inclusion(BaseModel):
    leadership: Literal["women", "youth", "pwd", "none", "prefer_not_to_say"] = "prefer_not_to_say"
    pct_women: int | None = Field(default=None, ge=0, le=100)
    pct_youth: int | None = Field(default=None, ge=0, le=100)
    pct_pwd: int | None = Field(default=None, ge=0, le=100)


class SupplierRegisterIn(PhoneMixin):
    account_type: Literal["farmer", "cooperative", "farmer_group", "aggregator", "trader", "processor", "msme"]
    legal_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=200)
    registration_no: str = ""
    kra_pin: str = ""
    phone: str
    email: EmailStr | None = None
    county_id: uuid.UUID
    sub_county: str = ""
    commodities: list[str] = Field(default_factory=list)
    members_count: int | None = Field(default=None, ge=1)
    sms_language: Literal["en", "sw"] = "en"
    inclusion: Inclusion = Inclusion()
    inclusion_consent: bool = False
    accept_terms: bool
    password: str

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v):
        if not v:
            raise ValueError("You must accept the terms of use and privacy notice.")
        return v


class RegisterOut(BaseModel):
    user_id: uuid.UUID
    supplier_id: uuid.UUID
    sent_to: str
    dev_code: str | None = None


class ResendIn(BaseModel):
    user_id: uuid.UUID


class VerifyPhoneIn(BaseModel):
    user_id: uuid.UUID
    code: str = Field(min_length=6, max_length=6)


class RoleGrant(BaseModel):
    role: str
    role_name: str
    org_id: uuid.UUID | None
    org_name: str | None
    org_type: str | None


class MeOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    status: str
    preferred_language: str
    mfa_enabled: bool
    roles: list[RoleGrant]
    permissions: list[str]
    supplier_id: uuid.UUID | None = None
    is_admin: bool = False            # administrator account: uses the administration sign-in
    is_super_admin: bool = False
    menu: list[str] = []              # portal pages this account sees (role defaults + Super Administrator changes)


class ProfileIn(BaseModel):
    full_name: str | None = None
    preferred_language: Literal["en", "sw"] | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str
    ip: str
    created_at: str
    last_used_at: str
    current: bool


def clean_identifier(identifier: str) -> tuple[str, str]:
    """Returns ('email'|'phone', normalized value)."""
    ident = identifier.strip()
    if "@" in ident:
        return "email", ident.lower()
    return "phone", normalize_phone(ident)
