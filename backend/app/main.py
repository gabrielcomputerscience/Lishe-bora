import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core import protection
from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0-pilot",
    description="LisheBora e-Sourcing Platform — STEP School Feeding Project.",
    docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
)


@app.middleware("http")
async def correlation_and_headers(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex
    request.state.correlation_id = cid
    blocked = protection.check(request)
    if blocked is not None:
        blocked.headers["X-Correlation-ID"] = cid
        return blocked
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/v1/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


register_error_handlers(app)
app.include_router(api_router)


@app.get("/api/health", tags=["system"])
def health():
    """Liveness: the process is up."""
    return {"status": "ok", "env": settings.app_env}


@app.get("/api/health/ready", tags=["system"])
def ready():
    """Readiness: database reachable and file storage writable (used by the container healthcheck)."""
    from pathlib import Path
    from sqlalchemy import text
    from app.core.database import engine
    checks = {}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {type(e).__name__}"
    try:
        p = Path(settings.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / ".ready").write_text("ok")
        checks["storage"] = "ok"
    except OSError as e:
        checks["storage"] = f"error: {e.strerror}"
    ok = all(v == "ok" for v in checks.values())
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)
