from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "LisheBora e-Sourcing Platform API"
    app_env: str = "development"
    debug: bool = True

    database_url: str = f"sqlite:///{BASE_DIR / 'lishebora.db'}"

    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    mfa_token_minutes: int = 5

    otp_minutes: int = 10
    otp_max_attempts: int = 5
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    password_min_length: int = 10

    cors_origins: str = "http://localhost:3000"
    public_site_url: str = "http://localhost:3000"   # used in QR codes printed on batch labels
    mpesa_callback_secret: str = ""                    # HMAC secret for payment callbacks; empty = callbacks disabled
    cookie_secure: bool = False

    storage_dir: str = str(BASE_DIR / "storage")
    max_upload_mb: int = 10
    media_max_mb: int = 30          # website images and short videos
    allowed_upload_types: str = "application/pdf,image/jpeg,image/png"

    # Fernet key for sealed bids. Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    bid_encryption_key: str = ""
    bid_min_evaluators: int = 1
    invoice_price_tolerance_pct: float = 0.0      # allowed unit-price variance above the PO price
    payment_target_days: int = 30                 # approved invoices unpaid after this open a late-payment exception

    # Messaging (Phase 7). console = print only.
    notify_backend: str = "console"            # console | africastalking
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_sender_id: str = ""
    at_sandbox: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "LisheBora <no-reply@lishebora.local>"
    smtp_starttls: bool = True
    rate_limit_enabled: bool = True
    trust_proxy: bool = False                  # true behind Caddy/nginx so X-Forwarded-For gives the client IP

    seed_admin_email: str = "admin@lishebora.local"
    seed_admin_password: str = "ChangeMe!2026"
    seed_demo_password: str = "Demo!2026pass"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def validate(s: Settings) -> Settings:
    """Refuse to start in production with development defaults."""
    if s.is_production and s.jwt_secret.startswith("change-me"):
        raise RuntimeError("JWT_SECRET must be set in production")
    if s.is_production and not s.bid_encryption_key:
        raise RuntimeError("BID_ENCRYPTION_KEY must be set in production")
    if s.is_production:
        problems = []
        if s.debug:
            problems.append("DEBUG must be false (it exposes sign-in codes)")
        if not s.cookie_secure:
            problems.append("COOKIE_SECURE must be true (serve over HTTPS)")
        if s.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL")
        if s.seed_admin_password == "ChangeMe!2026":
            problems.append("SEED_ADMIN_PASSWORD must be changed")
        if s.notify_backend == "africastalking" and not s.at_api_key:
            problems.append("AT_API_KEY is required for Africa's Talking")
        if problems:
            raise RuntimeError("Unsafe production settings: " + "; ".join(problems))
    return s


@lru_cache
def get_settings() -> Settings:
    return validate(Settings())


settings = get_settings()
