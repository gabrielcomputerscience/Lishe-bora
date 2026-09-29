"""Request protection (SRS §10.1): CSRF origin check for cookie sessions and rate limits on sensitive endpoints.

CSRF: browsers always send an Origin header on cross-site form posts and fetches. A state-changing request that carries
our session cookie and an Origin not in CORS_ORIGINS is refused. Bearer-token calls (API clients, tests) are unaffected.

Rate limits: a small in-process sliding window per client IP. Good enough for a single API instance; with several
instances put the same limits on the reverse proxy (see docs/DEPLOYMENT.md)."""
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# (path prefix, max requests, window seconds)
LIMITS = [
    ("/api/v1/auth/login", 10, 60),
    ("/api/v1/auth/mfa", 10, 60),
    ("/api/v1/auth/register", 5, 600),
    ("/api/v1/auth/forgot", 5, 600),
    ("/api/v1/auth/reset", 10, 600),
    ("/api/v1/auth/verify", 10, 600),
    ("/api/v1/public/contact", 5, 600),
    ("/api/v1/integrations/mpesa/callback", 120, 60),
]
_hits: dict[tuple, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd and settings.trust_proxy else (request.client.host if request.client else "?")


def _error(status: int, code: str, message: str, cid: str):
    return JSONResponse({"success": False, "error": {"code": code, "message": message, "details": []}, "correlation_id": cid}, status_code=status)


def check(request: Request) -> JSONResponse | None:
    cid = getattr(request.state, "correlation_id", "")
    if request.method in UNSAFE and not request.headers.get("authorization", "").lower().startswith("bearer "):
        has_session = "lb_access" in request.cookies or "lb_refresh" in request.cookies
        origin = request.headers.get("origin") or ""
        if not origin and request.headers.get("referer"):
            u = urlparse(request.headers["referer"])
            origin = f"{u.scheme}://{u.netloc}"
        if has_session and origin and origin.rstrip("/") not in {o.rstrip("/") for o in settings.cors_origin_list}:
            return _error(403, "CSRF_ORIGIN", "This request came from a page that is not allowed to act on your account.", cid)
    if settings.rate_limit_enabled and request.method in UNSAFE:
        path = request.url.path
        for prefix, limit, window in LIMITS:
            if path.startswith(prefix):
                key = (prefix, _client_ip(request))
                q, now = _hits[key], time.monotonic()
                while q and now - q[0] > window:
                    q.popleft()
                if len(q) >= limit:
                    r = _error(429, "RATE_LIMITED", "Too many attempts. Please wait a moment and try again.", cid)
                    r.headers["Retry-After"] = str(int(window - (now - q[0])) + 1)
                    return r
                q.append(now)
                break
    return None
