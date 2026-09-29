"""Administrator accounts are kept apart from operational accounts.

- Super Administrator and Administrator accounts sign in only at the administration sign-in (/admin/sign-in, API
  POST /auth/admin/login), always with two-step verification. The normal sign-in, SMS-code sign-in and supplier flows
  refuse them, and the administration sign-in refuses everyone else.
- An administrator account holds administrator roles only (no school, county, supplier or finance roles), so an
  administrator's session can never also act in procurement or payment workflows.
- Only a Super Administrator can create administrators, give or remove administrator roles, or change an
  administrator account. Administrators manage all other users and all content (website, master data, onboarding)."""
from app.core.errors import AppError
from app.models import User

ADMIN_ROLES = {"super_admin", "system_admin"}
SUPER = "super_admin"


def role_keys(user: User) -> set[str]:
    return {ur.role.key for ur in user.roles if ur.is_active}


def is_admin_account(user: User) -> bool:
    return bool(role_keys(user) & ADMIN_ROLES)


def is_super(user: User) -> bool:
    return SUPER in role_keys(user)


def use_admin_sign_in() -> AppError:
    return AppError(403, "USE_ADMIN_SIGN_IN", "Administrator accounts sign in on the administration sign-in page.",
                    [{"href": "/admin/sign-in"}])


def not_an_admin() -> AppError:
    return AppError(403, "NOT_AN_ADMIN", "This sign-in is for administrators only. Please use the main sign-in page.",
                    [{"href": "/sign-in"}])


def check_role_mix(existing: set[str], new_role: str):
    """Administrator roles cannot be combined with any other role on the same account."""
    if not existing:
        return
    if (new_role in ADMIN_ROLES) != bool(existing & ADMIN_ROLES) or (new_role in ADMIN_ROLES and existing - ADMIN_ROLES):
        raise AppError(409, "ADMIN_ROLE_SEPARATE", "Administrator roles are held on a separate administrator account. "
                                                   "Create a separate account for this person's other role.")


def check_can_manage(actor: User, target: User | None = None, role_key: str | None = None):
    """Only a Super Administrator can grant administrator roles or change an administrator account."""
    if is_super(actor):
        return
    if (role_key in ADMIN_ROLES) or (target is not None and is_admin_account(target)):
        raise AppError(403, "SUPER_ADMIN_ONLY", "Only a Super Administrator can manage administrator accounts.")
