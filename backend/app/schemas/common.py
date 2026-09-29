import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

PHONE_RE = re.compile(r"^(?:\+?254|0)(7|1)\d{8}$")


def normalize_phone(v: str | None) -> str | None:
    """Kenyan mobile numbers → +2547XXXXXXXX / +2541XXXXXXXX."""
    if v is None or v == "":
        return None
    s = re.sub(r"[\s\-()]", "", v)
    if not PHONE_RE.match(s):
        raise ValueError("Enter a valid Kenyan mobile number, e.g. 0712 345 678")
    return "+254" + s[-9:]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page_(BaseModel):
    total: int
    items: list


class Msg(BaseModel):
    message: str


class OrgOut(ORM):
    id: uuid.UUID
    type: str
    name: str
    code: str
    parent_id: uuid.UUID | None = None
    is_active: bool


class Ts(ORM):
    created_at: datetime
    updated_at: datetime


class PhoneMixin(BaseModel):
    @field_validator("phone", mode="before", check_fields=False)
    @classmethod
    def _phone(cls, v):
        return normalize_phone(v)
