"""Standard error envelope (SRS §10.3):
{"success": false, "error": {"code", "message", "details"}, "correlation_id"}"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: list | None = None):
        self.status_code, self.code, self.message, self.details = status_code, code, message, details or []


def _body(request: Request, code: str, message: str, details=None):
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details or []},
        "correlation_id": getattr(request.state, "correlation_id", None),
    }


def register_error_handlers(app):
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        codes = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT"}
        return JSONResponse(_body(request, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)),
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body(request, "VALIDATION_ERROR", "Some fields are invalid.", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # never leak internals
        import logging
        logging.getLogger("lishebora").exception("Unhandled error", exc_info=exc)
        return JSONResponse(_body(request, "INTERNAL_ERROR", "Something went wrong. Please try again."), status_code=500)
