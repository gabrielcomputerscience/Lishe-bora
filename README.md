# LisheBora e-Sourcing Platform

School food procurement and supply-chain platform for the **STEP School Feeding Project**.
Built from *SRS Consolidated Draft v0.3*, with colours and type from the AATF Brand Manual.

```
LisheeBora/
├── backend/     FastAPI · SQLAlchemy · Alembic · PostgreSQL/SQLite   → http://localhost:8000
├── frontend/    Next.js 15 · React 19 · TypeScript                   → http://localhost:3000
├── scripts/     Windows helpers: setup, start, reset
├── docs/        Specification, review, prototype and brand manual
└── docker-compose.yml   optional PostgreSQL + PostGIS
```

The browser only talks to the **frontend**. Next.js forwards `/api/*` to the backend, so auth cookies stay first-party and httpOnly.

## Quick start (Windows + PyCharm)

**You need:** Python 3.11 or newer (your `.venv` is 3.14), and Node.js 20 or newer from https://nodejs.org.

1. Open a terminal in PyCharm at the project root and run:
   ```bat
   scripts\setup.bat
   ```
   This installs the packages, creates the database, and seeds roles, the first admin, pilot geography, commodities and starter website content.
2. Start both servers. There are two ways:
   - **PyCharm:** use the ready-made run configurations (top-right dropdown): **Backend API (uvicorn)** and **Frontend (next dev)**, or **Full stack** to start both together.
   - **Terminal:** run `scripts\start-backend.bat` and `scripts\start-frontend.bat` in two terminals.
3. Open **http://localhost:3000**.

> PyCharm **Community** can't run npm configurations. Use `scripts\start-frontend.bat`, or run `npm run dev` in `frontend/`.

### First sign-in

| | |
|---|---|
| URL | http://localhost:3000/admin/sign-in (administrators have their own sign-in page) |
| Email | `admin@lishebora.local` (Super Administrator) |
| Password | `ChangeMe!2026` (set in `backend/.env` → `SEED_ADMIN_PASSWORD`; **change it**) |

Administrator accounts always use two-step verification. In development there is no SMS gateway, so **the code is shown on screen** and printed in the backend console. `DEBUG=true` turns this on; never enable it in production.

## Demo users (development)

`python -m app.seed.run --demo` creates one user per key role. The password is `SEED_DEMO_PASSWORD` in `backend/.env` (default `Demo!2026pass`).

| Email | Role | Scope |
|---|---|---|
| meals.officer@demo.lishebora | School Meals Officer | Kalulini (MAKUENI-SCH001) |
| school.admin@demo.lishebora | School Administrator | Kalulini (MAKUENI-SCH001) |
| nutrition@demo.lishebora | Nutrition Officer | Makueni County |
| procurement@demo.lishebora | County Procurement Officer | Makueni County |
| finance@demo.lishebora | County Finance Officer | Makueni County |
| county.admin@demo.lishebora | County Administrator | Makueni County |
| approver@demo.lishebora | Approving Officer | Makueni County |
| evaluator1@demo.lishebora, evaluator2@demo.lishebora | Evaluation Committee Members | Makueni County |
| supplier1@demo.lishebora | Umoja Farmers Cooperative (demo) · prequalified, women-led (verified) | own organisation |
| supplier2@demo.lishebora | Tumaini Grain Traders (demo) · prequalified | own organisation |
| administrator@demo.lishebora | Administrator (sign in at `/admin/sign-in`) | national |
| editor@demo.lishebora | Content Editor | website |
| auditor@demo.lishebora | Auditor | national, read-only |
| aggregator@demo.lishebora | Aggregator | Umoja cooperative (includes *Umoja Aggregation Hub*) |
| inspector@demo.lishebora | Quality Inspector | Makueni County |
| warehouse@demo.lishebora | Warehouse Officer | Makueni County Food Store (demo) |
| warehouse.supervisor@demo.lishebora | Warehouse Officer (approves adjustments and counts) | Makueni County |
| logistics@demo.lishebora | Logistics Officer | Makueni County |
| driver@demo.lishebora | Driver | own trips only |
| school2.admin@demo.lishebora | School Administrator | Muatini (MAKUENI-SCH002) |
| risk@demo.lishebora | Risk & Compliance Officer | Makueni County |
| accounts@demo.lishebora | Finance Officer (verifies invoices) | Makueni County |
| payments@demo.lishebora | Finance Officer (records payments) | Makueni County |
| meal@demo.lishebora | Programme / MEAL Officer | national |

The demo seed also creates **PO-DEMO-0001** (acknowledged): maize flour and beans from the Umoja cooperative for Kalulini and Muatini schools, so fulfilment can be tried without running Phase 3 first. The figures are illustrative only.

**Try the Phase 2 flow:**

1. The meals officer creates a Term 3 demand and submits it.
2. The school admin approves it from *My approvals*.
3. The procurement officer consolidates it into a plan and submits it.
4. Finance confirms the budget.
5. The county admin approves the plan, and the budget shows the commitment.

**Try the Phase 3 flow** (after the Phase 2 flow has an approved plan):

1. The procurement officer goes to *Sourcing events*, creates a new event from the plan and submits it.
2. The approver publishes it from *My approvals*. Both suppliers get an SMS and an in-app alert.
3. `supplier1` and `supplier2` bid under *Opportunities*.
4. After the deadline, the officer opens the bids and assigns evaluators.
5. `evaluator1` declares no conflict of interest and scores the bids.
6. The officer consolidates the results and submits the recommendation.
7. Finance does the commitment check, then the approver approves the award.
8. The winner sees the contract and PO under *My contracts & orders* and acknowledges it.

> In development you don't have to wait for a deadline. Set a short closing time, or run the tests, which move the clock with SQL.

**Try the Phase 6 flow** (after goods are delivered and an invoice is approved):

1. `aggregator` opens *My supplier profile → How you get paid* and changes the M-Pesa number. `accounts` approves it under *Payment integrations → Payment details* after calling the registered number.
2. `payments` selects approved invoices under *Payment integrations*, creates the M-Pesa or bank file, then imports the statement CSV. Rows that quote the INV- number are matched and recorded as payments.
3. `inspector` opens a batch under *Traceability*, prints its QR label and, if needed, recalls it. Every school and store holding it gets an SMS, and the public page `/t/BATCH-…` shows "Do not use".
4. `risk` opens the *Risk dashboard* and runs a scan. `meal` views the *Programme map*, *Forecasts & prices* and downloads Excel exports.

**Try the Phase 5 flow** (after the Phase 4 flow has delivered goods on PO-DEMO-0001):

1. `aggregator` opens *Invoices & payments → New invoice*. Only quantities schools accepted can be billed, at the contract price.
2. `accounts` verifies it from *My approvals*, and `finance` (County Finance Officer) approves it. The budget moves from committed to invoiced.
3. `payments` opens the invoice and records the M-Pesa or bank payment. The supplier gets an SMS, and the budget moves to paid.
4. `school.admin` raises a complaint under *Complaints*. `procurement` investigates, `county.admin` resolves, and the school confirms and rates the resolution.
5. On the public *Contact* page, choose "Complaint / grievance". You get a case number and the county sees the case.
6. `procurement` checks *Supplier performance*. `meal` views the *MEAL dashboard* and downloads CSV exports.

**Try the Phase 4 flow** (uses PO-DEMO-0001):

1. `aggregator` records farmer intakes under *Aggregation & intake*, then closes the batch and requests inspection. Switch the browser offline and record one more intake: it waits on the device and syncs when you reconnect.
2. `inspector` inspects the batch under *Quality inspection*. A moisture reading above the limit blocks "accept all".
3. `logistics` plans a dispatch under *Dispatch* (PO, hub, vehicle, driver and quantity per school), then dispatches it.
4. `driver` opens the trip under *Deliveries* and marks it in transit.
5. `school.admin` and `school2.admin` confirm receipt with a signature. Rejecting part of the delivery sends it back to hub stock and opens an exception.
6. `procurement` or `county.admin` follows up under *Exceptions* and traces the batch from farm to school under *Traceability*.
7. `aggregator` requests a write-off under *Inventory*, and `warehouse.supervisor` approves it from *My approvals*.

## Phase 7: pilot readiness (in this build)

| Area | Included |
|---|---|
| PostgreSQL | All migrations and the full test suite verified on PostgreSQL 16 as well as SQLite (`TEST_DATABASE_URL=postgresql+psycopg://…/lishebora_test python -m pytest`). Migrations downgrade to base and back cleanly |
| SMS & email | Every message goes through an **outbox** (`outbound_messages`) in the same transaction as the business change. Adapters for **Africa's Talking** (`NOTIFY_BACKEND=africastalking`, sandbox switch) and **SMTP**; `console` stays the default for development. Sign-in codes and invitations are sent immediately and their text is **wiped once delivered**; everything else is sent by the worker with retries and back-off |
| Background worker | `python -m app.jobs all --loop 60` (or `scripts\start-worker.bat`, or the *Worker* run configuration): sends messages, **reminds approvers of overdue approvals and escalates to the County Administrator after twice the SLA**, checks for late payments, runs the risk scan, and sends expiring-document, contract-end, stock-expiry and stock-out alerts. Each reminder goes out once. Status is shown under *System & onboarding* |
| Security | **CSRF protection**: state-changing requests carrying the session cookie from a page not in `CORS_ORIGINS` are refused. **Rate limits** on sign-in, MFA, registration, password reset, contact form and payment callback. HSTS, `Cache-Control: no-store` on the API, a Content-Security-Policy and Permissions-Policy on the website. **The API refuses to start in production** with DEBUG on, non-HTTPS cookies, SQLite, missing secrets or the default admin password |
| Health | `/api/health` (alive) and `/api/health/ready` (database and storage), used by the container healthcheck |
| Onboarding | *System & onboarding*: rename or add **counties**; **import schools** and **import staff accounts** from CSV, with a template, **a check that previews every row first, and nothing saved unless the whole file is valid**. Segregation-of-duties conflicts are refused; staff get a temporary password by SMS or email |
| Deployment | `backend/Dockerfile`, `frontend/Dockerfile` (standalone), `deploy/docker-compose.prod.yml` (PostGIS, API, worker, web, **Caddy with automatic HTTPS**), `deploy/.env.example`, `scripts/backup.sh` / `restore.sh`. See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** |
| Production seed | Without `--demo` the seed creates roles, permissions, the first admin, the survey food categories and commodities, the sampled schools (Makueni, Embu, Isiolo) and starter website content (no demo users, suppliers or orders) |

## Phase 6: advanced & scale (in this build)

| Area | Included |
|---|---|
| Installable offline app | The site is a Progressive Web App: *Install* prompt, app icon, and a service worker that keeps field pages (intake, inspection, deliveries, inventory, traceability) usable offline, with an offline fallback page. Offline records sync once. A record already confirmed on another device (e.g. a school receipt) counts as synced, not as a conflict |
| QR traceability & recall | Every batch has a printable **QR label** (6 per sheet) linking to a public verification page `/t/{code}`. That page shows the commodity, origin county, aggregator, inspection result, producer count and recall status, **with no personal data**. Phone-camera scanning is on the Traceability page. **Recall** (quality inspector or risk officer): blocks dispatch, transfer and use; flags stock "RECALLED: do not use"; SMS-alerts every school, store and supplier holding the batch; opens a high-priority exception |
| GIS | Coordinates for schools, hubs and stores (field staff tap *Use my location*; every change is audited). The **programme map** (OpenStreetMap) shows schools receiving food or not, hubs, stores, open complaints, stock alerts, and trips on the road with their last GPS position. **Suggested stop order** for each dispatch (nearest-neighbour + 2-opt, straight-line km) can be saved to the trip. PostGIS can replace the helpers later without changing the API |
| Forecasting | **Stock-out outlook** per school and commodity: days left from the last 30 days of recorded use, or from the demand plan. **Next-term requirement**: latest approved plans minus school stock, valued at reference prices. Both use plain, checkable methods |
| Price intelligence | Awarded unit prices per commodity: min / median / max / weighted average / latest, compared with the reference price, with trend. Staff only (hidden from suppliers) |
| Risk flags | Rules for late deliveries, school acceptance, inspection rejection, recalls, open fraud/safeguarding complaints, returned invoices, expired documents, price outliers (≥ 3 contracts), single-bid awards and near-expiry stock. The supplier risk ranking has high 3 / medium 2 / low 1 points. **Run scan** opens an exception case per new medium/high flag (never twice). Thresholds are editable (`risk.rules` setting) and audited |
| Buyer-side performance | Per county: average days to pay, share paid within target, average approval time, overdue approvals, time for schools to confirm deliveries, complaints resolved on time |
| Payment integrations | **Verified supplier payment details**: changes wait for finance, who must call the registered number; SMS alert on every change (anti-diversion). **Bulk payment files** (M-Pesa B2C / bank EFT CSV) only for payable invoices with verified details, respecting SoD. **Statement import** auto-reconciles rows quoting an INV- number, skips duplicates and lists the rest. **Signed M-Pesa callback** (`/api/v1/integrations/mpesa/callback`, HMAC-SHA256, idempotent). **IFMIS export** with budget line and funding source. **Payment ageing** (0–15 / 16–30 / 31–60 / 61+ days). Everything is written to the **integration log** |
| Exports | Every MEAL dataset is also available as a formatted **Excel** workbook |

Not built, and left for the programme to decide: native Android/iOS apps (the PWA covers the offline field use), USSD, live bank/M-Pesa API connections (the file exchange and callback are the adapters), road-network routing, and AI decision support.

## Phase 5: finance & performance (in this build)

| Area | Included |
|---|---|
| Invoices | Suppliers (or finance, for a paper invoice) invoice against a PO with an optional PDF or photo copy. **Automatic three-way match**: invoiced quantity ≤ quantity accepted at schools (e-POD) and ≤ ordered, and unit price ≤ contract price (tolerance `INVOICE_PRICE_TOLERANCE_PCT`, default 0). Mismatches are blocked with the reason shown. Duplicate supplier invoice numbers are refused. The match evidence is stored with the invoice and re-checked at verification |
| Approval | Finance verification (`fin:verify`) → payment approval (`fin:approve`), in the shared approval engine. **Verifier, approver and payer must be three different people**, and none of them can be the person who captured the invoice. Returned or rejected invoices free the quantities so a corrected invoice can be sent |
| Payments | Full or part payments by bank, M-Pesa, cheque or IFMIS reference. Duplicate transaction references and overpayments are blocked. The supplier gets an SMS for each payment. Invoices approved but unpaid after `PAYMENT_TARGET_DAYS` (default 30) open a **late-payment exception**, which closes automatically when the invoice is paid |
| Budget | On approval, the contract commitment becomes *invoiced*. On payment it becomes *paid*, so budget pages show committed / invoiced / paid / available |
| Complaints | Raised by schools, suppliers, staff, or the public through the Contact page (with a case number). Categories include food quality, deliveries, conduct, payment, procurement fairness, safeguarding and fraud. Due dates are 3/7/14 days by priority. Safeguarding, fraud and staff-conduct cases are always high priority, go to the risk officer and are **hidden from the supplier concerned**. Flow: investigate → supplier response → resolution by the County Administrator → the complainant confirms and rates it, or reopens it. Complainants can stay anonymous |
| Supplier performance | Scorecards from platform records: on-time delivery, acceptance at schools, order fill, inspection pass rate, complaints and days to pay. Weights are provisional (30/30/20/10/10), with Good/Fair/Needs-improvement bands. Suppliers see only their own |
| MEAL dashboard | Reach (schools, learners, meals recorded), food (accepted kg, acceptance, on-time), inclusive sourcing (smallholder share, verified women/youth-led share, same-county share, producers, women and youth producers), finance (paid, days to pay, pending) and accountability (exceptions, complaints resolved on time), with monthly trends by county and date range. **Every figure comes from platform transactions; nothing is estimated** |
| Exports | CSV exports of deliveries, invoices and payments, scorecards, producer participation (**aggregated by hub, no names or phones**), exceptions and complaints (no contact details). Every export is written to the audit trail |

## Phase 4: supply-chain fulfilment (in this build)

| Area | Included |
|---|---|
| Aggregation | Hubs sit under the supplier's organisation. Farmer intake records producer, group, village, optional gender and youth (for inclusion reporting only), commodity, variety and quantity. Intakes of the same commodity join one open **batch** (`BATCH-YYYY-NNNNNN`, QR-ready). The aggregator closes the batch and requests inspection, and inspectors are notified |
| Quality | Measured parameters are checked against the commodity specification (e.g. `max_moisture_pct`), alongside visual checks (pests, mould, foreign matter, smell). Results are accept, partial, downgrade or reject, with quantities that must add up. A reason is required unless everything is accepted. Photos, expiry date and a corrective action can be recorded. **SoD-09: nobody can inspect a batch they recorded intake for.** Accepted quantity goes into stock. Rejections open an exception, and the supplier is notified by SMS |
| Inventory | A movement ledger (receipt, issue, transfer, adjustment, return, write-off). **Balances are always calculated from posted movements.** Transfers between hub, store and school. **Adjustments and write-offs stay pending until someone else with `inv:verify` approves them.** Physical counts post their variances once approved, and a variance above 2% opens an exception. Expiry alerts. Schools record food used for meals (first-expiring first) |
| Dispatch | Planned from an acknowledged PO: hub, vehicle, driver and quantity per school per line. The system checks cleared stock and blocks sending more than the PO still needs; rejected goods can be re-sent. Dispatching posts the stock issue, updates the PO line and notifies schools and the driver by SMS |
| Driver | Drivers see only their own trips. They mark the trip in transit, arrival at each school and delivery. GPS is attached when the phone allows it |
| e-POD | The school confirms accepted and rejected quantities per item, the condition on arrival, the receiver, a **drawn signature** and photos. Accepted goods post a receipt into school stock, and rejected goods return to the hub. The PO becomes partially fulfilled or fulfilled. **Works offline**: the receipt is saved on the device with a unique reference and synced once, even if it is sent twice. The dispatch closes when every school has confirmed |
| Exceptions | Opened automatically for quality rejection, rejected goods, short delivery, poor condition, late delivery and stock-count variance. Each has a severity, an owner role, a due date and a notification. Officers record corrective action and county administrators (or risk officers) resolve them |
| Traceability | One page per batch: farmers and inclusion summary → inspection → every stock movement → the schools that received it, and when |

## Phase 3: e-procurement (in this build)

| Area | Included |
|---|---|
| Sourcing events | Created from an approved plan (each plan line becomes a lot); RFQ, competitive tender or framework; configurable criteria and technical/financial weights (must total 100); required documents; contract period; **approval before publishing** |
| Suppliers | *Opportunities* limited to eligible, prequalified categories with verified documents; questions and answers shared with everyone anonymously; formal amendments sent to everyone |
| Sealed bids | Encrypted (Fernet) the moment they're saved; revisable until the deadline; a submit receipt with checksum; **automatic closing**; late bids rejected; officers see only metadata; formal opening decrypts, checks integrity and records an opening register |
| Evaluation | Panel of Evaluation Committee Members (the event creator can't sit on it); **conflict-of-interest declaration before any bid is visible**, and a declared conflict excludes the evaluator; per-criterion scores within limits; **automatic inclusion score only for verified women/youth/PWD-led suppliers**; financial score = weight × lowest price ÷ price; responsiveness checks (eligibility, full quantity) |
| Award | Recommendation → **finance commitment check → Approving Officer approval**; winners and unsuccessful bidders notified by SMS and in-app; public award notice; award queries |
| Contracts & POs | One contract per winning supplier; purchase contracts issue a PO for the full quantity; **framework agreements take call-off orders that can't exceed the remaining balance**; supplier acknowledgement; expiry and usage alerts |
| Budget | On award, the plan's hold is released and each contract value is committed to the same budget line |
| Notifications | In-app notification centre (the bell in the header) with an SMS/email copy through the notification adapter |

## Phase 2: demand, nutrition & budget (in this build)

| Area | Included |
|---|---|
| Terms & menus | Academic terms with feeding days; menu cycles with grams per learner per meal; food-group diversity check; nutrition validation workflow |
| School demand | Learners × attendance × feeding days × menu portions × (1 + wastage) − stock; quantity overrides with reasons; validation (blocking errors and warnings); approval: validate → approve |
| Consolidation | Approved demand is grouped into lots (cluster × category, or county-wide) → procurement plan, with reference prices for estimates |
| Budget | Budget lines per funding source, county and period; approved / committed / invoiced / paid / available; alerts at a threshold and on over-commitment |
| Controls | A plan can't be submitted without a budget line and prices; submission is blocked if the budget is insufficient, unless an approved **budget exception** exists; funds are held (committed) when the county approves |
| Approval engine | Reusable multi-stage workflows with permission + scope checks, *no self-approval*, one person per stage, SLA due dates, return/reject with a mandatory reason, full history, and **My approvals** inbox |

## What's in this build: Phase 1, the platform foundation

| Area | Included |
|---|---|
| Public website | Home, About, How it works, Opportunities (open notices and awards), News, Resources, FAQ, Contact, privacy/terms. **All content is admin-managed.** |
| Accounts | Supplier self-registration (farmer, cooperative, aggregator, trader) with phone OTP; sign-in by password or SMS code; two-step verification for privileged roles; lockout after 5 failed tries; password reset; session list and remote sign-out |
| Roles & scope | All 24 roles and 111 permissions from the SRS matrix; **User → Role → Data scope → Permission** enforced in the API; segregation-of-duties checks (conflicting roles, no self-assignment) |
| Supplier registry | Documents (PDF/JPG/PNG, versioned, checksummed, type-sniffed); verification by county officers; inclusion claims verified before they count; prequalification state machine with separate verify and approve permissions |
| Website CMS | Hero, statistics, news, pages and FAQ; the Content Editor drafts and submits, an approver publishes; version history |
| Sourcing (slice) | Create and publish sourcing notices to the website. Bids and evaluation come in Phase 3. |
| Audit trail | Append-only log of every material action, readable only by Auditor/Admin roles |
| API | Versioned REST `/api/v1`, OpenAPI docs at http://localhost:8000/api/docs, standard error envelope with correlation IDs |

**Next phases** follow SRS §12: 4 · supply-chain fulfilment (aggregation & quality, inventory, dispatch, offline e-proof of delivery) → 5 · finance & performance (three-way match, payments, complaints, MEAL dashboards).

## Common tasks

| Task | Command (from `backend/`, with the venv active) |
|---|---|
| Run tests | `python -m pytest -q` (43 tests) |
| New migration after changing models | `python -m alembic revision --autogenerate -m "describe change"` then `python -m alembic upgrade head` |
| Reset the local database | `scripts\reset-db.bat` |
| Switch to PostgreSQL | `docker compose up -d db`, then set `DATABASE_URL` in `backend/.env` (see `.env.example`) and run the migrations |
| Frontend type-check / build | `npm run typecheck` / `npm run build` (in `frontend/`) |

## Before production (not done yet)

- An SMS gateway and email provider adapter in `backend/app/services/notify.py`, replacing the console sender.
- `BID_ENCRYPTION_KEY`: a Fernet key, **backed up with your secrets**. Without it, unopened bids can't be decrypted.
- `JWT_SECRET`, `COOKIE_SECURE=true`, `DEBUG=false`, `APP_ENV=production`; PostgreSQL; S3-compatible storage in `services/storage.py`; a malware-scan hook.
- Rate limiting at the gateway, plus a CSRF token for cookie-authenticated form posts (SameSite=Lax is the current mitigation).
- Offline: the PWA caches pages visited while online. Visit each field page once after installing. For devices shared by several users, sign out at the end of the day.
- Set `PUBLIC_SITE_URL` before printing QR labels, and `MPESA_CALLBACK_SECRET` once a gateway adapter is contracted. Serve the site over HTTPS; service workers and camera scanning require it.
- Confirmed pilot counties, thresholds and legal texts (SRS §14 questions). The seed uses **placeholders**: `[x]` statistics, platform-assigned school codes until NEMIS codes are supplied.

## Changes from SRS v0.3 made during the build

1. **New `cms` permission domain** and a **Content Editor** role for the admin-managed website.
2. **"View" is implied** by any other permission on a domain. In the matrix, admins had create/edit on users but no view. Records stay limited to the role's data scope.
3. Supplier registration reuses the **Supplier / Farmer Group / Aggregator** roles, scoped to the supplier's own organisation.
4. **Budget is held when a plan is approved**, not only when a PO is raised, so two plans can't spend the same money. Phase 3 turns this hold into the PO commitment.
5. Menus created by county-scoped users belong to their county. Programme-wide templates need a national-scope user.
6. School demand allows the same person (e.g. a head teacher) to validate and then approve, because small schools may have one administrator. The person who *submitted* it can never approve it.
7. Supplier accounts see only their own supplier record, opportunities and orders. Internal planning menus are hidden from them.
8. **Hubs are organisations under the supplier**, so an aggregator's own-organisation scope covers its hubs and a county-scoped inspector or logistics officer covers every hub in the county.
9. **Warehouse supervisors** are Warehouse Officers assigned at county level. The matrix gives `inv:verify` only to warehouse officers, so someone at county level is needed to approve hub adjustments.
10. **Driver scope is "own trips"**: a driver can update only trips assigned to them, whatever their org assignment.
11. Exceptions are resolved by roles holding `rsk:approve` or `rsk:edit` (County Administrator, Risk & Compliance Officer). Officers with `rsk:create` record corrective action. The full exceptions centre with risk scoring was added in Phase 5 (late payments).
12. **Farmer Group / Cooperative accounts can view invoices but not submit them** (matrix: `fin` V). In the demo, the cooperative's *Aggregator* user submits invoices. Change the matrix if cooperatives should invoice directly.
13. **Schools record meals served** when they record food used, so the dashboard can report meals without a separate attendance module.
14. **Recall permission**: quality inspectors (`agg:approve`) and risk officers (`rsk:approve`/`rsk:edit`) can recall a batch. Aggregators cannot recall their own batches.
15. **Payment details** are a new supplier field that finance must verify before any payment file uses it. The SRS lists the control and this build implements it.

## Programme reference data (real data)

| What | Where | Seeded |
|---|---|---|
| 16 survey food categories and their 36 food items (Food_Categories_foodcat.xlsx) | `backend/app/seed/reference.py` → `FOOD_CATEGORIES` | Every mode. Each food item is a commodity; the category is the supplier prequalification category. `GET /api/v1/public/food-categories` lists them |
| 32 sampled schools in Makueni (16), Embu (8) and Isiolo (8), with sub-counties (Schools-Sampled.xlsx) | `SAMPLED_SCHOOLS`, and `docs/data/schools_sampled.csv` in the importer format | Every mode |
| School contact persons and phone numbers | `docs/data/school_contacts_for_import.csv` (import format for *System & onboarding → Import staff accounts*) | **Not seeded.** It is personal data, and importing it sends each person an SMS invitation, so import it only once the heads have agreed. Check the roles (all set to `school_admin`) before importing |

Things the source files do not contain, so the platform does not invent them:
- **School codes**: assigned in file order (`MAKUENI-SCH001` …). Replace with NEMIS codes when available.
- **GPS coordinates and enrolment**: blank. School admins capture GPS on site (or add `lat,lng` to the CSV and re-import); enrolment is entered on each term's demand plan. Until then, schools do not appear on the map and route planning shows 0 km.
- **Prices and quality thresholds**: the demo sets illustrative prices and moisture limits on the commodities the demo menu uses; production has none until the county sets them.
- **Nutrition groups**: each category is mapped to the broad groups the menu-diversity rule counts (Cereal, Legume, Vegetable, Fruit, Animal-source, Oil, Roots & tubers; salt has none). Nutrition officers should confirm the mapping.

Earlier development builds used placeholder counties (Pilot County A/B) and different commodity codes. The seed now deactivates the old commodity codes. For a clean demo, reset the local database with `scripts\reset-db.bat`.

## Administrator accounts

| | Super Administrator | Administrator |
|---|---|---|
| Sign-in | `/admin/sign-in` only, always with a code | `/admin/sign-in` only, always with a code |
| Website (home page, news, pages, FAQs, downloads) | Write, review, publish | Write, review, publish |
| Master data (counties, schools, commodities, food categories, menus and terms) | Full | Full (*Master data* page) |
| Users | All users, including administrators | All users **except** administrator accounts |
| Onboarding imports, jobs, messages | Yes | Yes |
| Operational records (demand, sourcing, deliveries, finance) | Read only | Read only (cannot approve, award or pay) |

Rules (in `backend/app/services/admin_access.py`):
- The main sign-in page, SMS-code sign-in and supplier flows refuse administrator accounts. The administration sign-in page refuses everyone else.
- An administrator account holds administrator roles only. If a person also has an operational job, such as county finance, they get a second, ordinary account for it.
- Only a Super Administrator can create an administrator (*Users & roles → Invite*, choose *Administrator*) or change an administrator's account. Administrator roles cannot be given through the CSV import.
- Every administrator sign-in is recorded in the audit trail (`LOGIN_ADMIN`); a refused attempt is recorded as `ADMIN_LOGIN_REFUSED`.

## Pilot with real data

1. **Create the pilot database** (keeps the demo database for training): stop the backend and run `scripts\setup-pilot.bat`.
   It builds `backend\lishebora_pilot.db` with the roles, the 3 pilot counties, the 32 sampled schools, the 36 foods and the
   starter website pages, with **no demo accounts, suppliers, orders or prices**, and points `backend\.env` at it.
   Switch between the two with `scripts\use-demo.bat` and `scripts\use-pilot.bat` (restart the backend after switching).
2. **Sign in** at `/admin/sign-in` as the Super Administrator (`SEED_ADMIN_EMAIL`), change the password, and open
   **Administration → Pilot readiness**. It lists everything still needed, with a Fix button for each.
3. **Download the pilot data workbook** (Pilot readiness or System & onboarding). It is pre-filled with the schools, foods, role
   codes and organisation codes. Fill the shaded cells (enrolment, GPS, NEMIS codes, staff accounts, reference prices) and upload
   the same workbook to *Import schools*, *Import staff accounts* and *Import reference prices*. Every import previews first.
4. Nutrition officers set up the pilot menu and term dates; county finance adds budget lines; the content team fills in the
   website pages and the **Contact details** (Website content → Homepage), which appear in the footer and on the sign-in pages.
5. For a pilot server (rather than a laptop), follow `docs/DEPLOYMENT.md`: PostgreSQL, HTTPS, the SMS gateway, email and the worker.
