# LisheBora backend (FastAPI)

```
app/
├── main.py              app, CORS, security headers, correlation IDs
├── core/                config (.env), database, security (bcrypt, JWT), deps (auth · permissions · data scope), errors
├── models/              SQLAlchemy models: identity, org hierarchy, master data, supplier, procurement, cms, audit
├── schemas/             Pydantic request/response models
├── api/v1/              routers: auth, public, iam (users & roles), masterdata, suppliers, procurement, cms, audit
├── services/            audit, otp, notify (SMS/email adapter), storage (files), auth sessions, cms workflow
└── seed/                matrix.py (SRS role × permission matrix), run.py (idempotent seed)
migrations/              Alembic migrations
tests/                   pytest: auth, RBAC & data scope, prequalification, SoD, CMS workflow
```

## Key design points
- **Authorisation lives in the API.** `require("sup:verify")` checks the permission. `scope_for()` / `ensure_in_scope()` limit records to the user's organisation subtree (county → sub-county → school).
- **Tokens:** a 15-minute access JWT, plus an opaque refresh token that rotates on every use and is stored hashed. Both are sent as httpOnly cookies, and in the response body for mobile/API clients.
- **Status changes** (supplier, CMS content) are explicit state machines. Invalid moves return `409 INVALID_TRANSITION`.
- **Every material action writes an audit row in the same transaction.** No API can edit or delete the audit log.
- **Errors** always use `{"success": false, "error": {"code", "message", "details"}, "correlation_id"}`.

Run: `python -m uvicorn app.main:app --reload`  ·  Tests: `python -m pytest -q`  ·  Seed: `python -m app.seed.run --demo`
