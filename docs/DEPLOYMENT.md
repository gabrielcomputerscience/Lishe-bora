# LisheBora pilot deployment runbook

This runbook takes the platform from a developer laptop to a pilot server with HTTPS, PostgreSQL, SMS/email,
the background worker and nightly backups. Commands assume an Ubuntu 22.04/24.04 server with Docker installed.

## 1. What runs

| Service | Image | Purpose |
|---|---|---|
| `db` | postgis/postgis:16 | PostgreSQL database (PostGIS ready for later GIS work) |
| `backend` | built from `backend/` | FastAPI. On start it runs migrations and seeds roles and permissions (no demo data) |
| `worker` | same image as backend | `python -m app.jobs all --loop 60`: sends SMS and email, sends overdue-approval reminders and escalations, checks for late payments, runs the risk scan, and sends document, contract and stock expiry alerts |
| `frontend` | built from `frontend/` | Next.js website and portal (standalone server) |
| `caddy` | caddy:2 | HTTPS with automatic Let's Encrypt certificates. Routes `/api/*` to the backend and everything else to the frontend |

Sizing for a pilot of a few hundred users: 2 vCPU, 4 GB RAM, 40 GB disk plus backup storage.

## 2. Before you start

1. **Domain**: point a DNS A record (e.g. `lishebora.<organisation>.org`) at the server. Open ports 80 and 443.
2. **Secrets**: have these ready (store them in the organisation's password manager):
   - `JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `BID_ENCRYPTION_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
     **If this key is lost, unopened bids can never be decrypted.** Back it up separately from the server.
   - A strong `POSTGRES_PASSWORD` and `SEED_ADMIN_PASSWORD`.
3. **SMS**: an Africa's Talking account (username and API key). Keep `AT_SANDBOX=true` until the sender ID is approved.
4. **Email**: an SMTP relay (host, port, user, password, from address).

## 3. Install

```bash
sudo mkdir -p /opt/lishebora && sudo chown $USER /opt/lishebora
cd /opt/lishebora && unzip lishebora_phase7.zip          # or git clone
cp deploy/.env.example deploy/.env && nano deploy/.env    # fill in every value
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env ps
curl -fsS https://<DOMAIN>/api/health/ready                # {"status":"ok",...}
```

The API **refuses to start** in production if any of these hold: `DEBUG` is on, cookies aren't HTTPS-only, the database is SQLite, secrets are
missing, or the admin password is still the default. Read the error with `docker compose ... logs backend`.

## 4. First sign-in and onboarding

1. Sign in as `SEED_ADMIN_EMAIL` at `https://<DOMAIN>/admin/sign-in` (administrators have a separate sign-in page). Invite the Administrators under *Users & roles* (choose *Administrator*). The MFA code arrives by SMS or email. Change the password under *My profile & security*.
2. **Counties and schools**: the seed creates Makueni, Embu and Isiolo counties and the 32 sampled schools. To add schools, or to add NEMIS codes, GPS and enrolment to the existing ones, edit `docs/data/schools_sampled.csv` (or the template), then go to *System & onboarding → Import schools*, click **Check file**, fix any errors, then **Import**. Add any further county under *Counties* first.
3. **School contacts**: `docs/data/school_contacts_for_import.csv` holds the contact persons from the sampling file. Import it under *Import staff accounts* only once the heads have agreed, because each person gets an SMS.
4. **Staff**: *System & onboarding → Import staff accounts*, the same way. Each person gets a temporary password by SMS or email.
5. **Suppliers** register themselves on the public website. County procurement officers review them under *Supplier registry*.
6. **Budget lines and menus**: county finance creates budget lines; nutrition officers approve the menu.
7. Check *System & onboarding*: jobs show a recent "Last run", and the outbox has no failed messages.

Never run `python -m app.seed.run --demo` on the pilot server. Demo users share one known password.

## 5. Operations

| Task | How |
|---|---|
| Logs | `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env logs -f backend worker` |
| Update to a new version | unzip over `/opt/lishebora` (keep `deploy/.env`), then `up -d --build`. Migrations run automatically |
| Backup (nightly) | `scripts/backup.sh` via cron at 01:30. It writes a database dump plus uploaded files and keeps 14 days. **Copy the backup folder off the server** (e.g. rclone to the organisation's cloud storage) |
| Restore | `scripts/restore.sh <db-dump> <storage-tgz>` (stops the API and worker while restoring) |
| Test a restore | once a month, restore the latest backup on a spare machine and sign in |
| Failed SMS/email | *System & onboarding → Messages that could not be sent → Retry* |
| Rotate `JWT_SECRET` | change it in `.env` and restart the backend. Everyone has to sign in again |
| Never rotate | `BID_ENCRYPTION_KEY` while any sourcing event has unopened bids |

## 6. Security checklist (pilot go-live)

- [ ] HTTPS works and `http://` redirects (Caddy does this automatically).
- [ ] `deploy/.env` is readable only by the service account (`chmod 600`) and is not in version control.
- [ ] The super-admin password has been changed and MFA works. Other admins have their own accounts; no shared logins.
- [ ] Only ports 80/443 (and SSH restricted by IP or key) are open. PostgreSQL is **not** exposed.
- [ ] Backups run, are copied off-site, and one restore has been tested.
- [ ] The SMS sender ID is approved, and `AT_SANDBOX=false`.
- [ ] The retention period for audit logs and supplier documents is agreed with the data protection officer (Kenya Data Protection Act 2019).
- [ ] Rate limits: the API limits sign-in, registration and password reset per IP. If you run more than one backend instance, add the same limits at the proxy.
- [ ] A penetration test or independent security review is scheduled before scaling beyond the pilot.

## 7. Running on Windows without Docker (training / demo laptop)

The PyCharm setup in the README still works: `scripts\setup.bat`, then `scripts\start-backend.bat`, `scripts\start-frontend.bat` and
`scripts\start-worker.bat` (or the *Worker* run configuration). To use PostgreSQL locally, run `docker compose up -d db` and set
`DATABASE_URL=postgresql+psycopg://lishebora:lishebora@localhost:5432/lishebora` in `backend\.env`.

## 8. What was verified in this build

- All 7 migrations run on **PostgreSQL 16** and on SQLite, and downgrade to base and back.
- The full automated suite (43 tests, covering every phase, the reference data and administrator access) passes on **both** databases.
- A production-mode run (PostgreSQL, `DEBUG=false`, HTTPS cookies, CSP headers, standalone Next.js server): sign-in with MFA, the main pages, service worker registration, with **no Content-Security-Policy violations**. Sign-in codes are not shown on screen.
- `docker compose config` validates the production stack. The images themselves could not be built in the build environment (no registry access), so the first `up --build` on the server is the first real image build.
