# APEX — Data Entry Platform

Enterprise data-entry web application with a premium glassmorphism UI, built with **Python (Flask)**,
**HTML/CSS/JavaScript**, **Supabase** (database + Auth) and deployed on **Vercel** from **GitHub**.
No Node.js, no build step, no third-party front-end libraries (charts are hand-rolled SVG).

## Features

**Authentication & security**
- Associate Login / Admin Login tabs validated against the Supabase `User` masterlist (`DOMAIN` / `PASSWORD`)
- `ROLE = Associate` → Associate Login only; any other role → Admin Login only
- Forced first-time setup: new password (8+ chars, upper, lower, number) → Carelon email → "Account Successfully Created"
- Supabase Auth identity per user + PBKDF2 hash written back to `PASSWORD`
- RBAC re-validated against the database on every request; signed HTTP-only session with idle/absolute timeout;
  CSRF on every form and JSON call; strict CSP (`'self'` only)

**Program selection** — after login the user's `PROGRAM` is highlighted (glow). Blank `PROGRAM` → all programs
glow and the user picks one. Only **DISPUTES AND INTAKES** is active; COB, NON COB, CASH CONTROL, IQT and PREPAY
are placeholders.

**Disputes and Intakes — Associate module** (`/di/...`, `ROLE = Associate`)
| Tab | What it does |
|---|---|
| Task Entry | Creates a `Pend` row. STATUS = Pending, optional free-text SUB_STATUS, DATE_PENDED defaults to today, ASSIGNED_TO / DOMAIN / MANAGER auto-filled from the `User` table. PENDED_DAYS is calculated by the database and not shown. |
| Update Pends | The user's own pends with Inquiry Number search, date range and status filters. Select a row to see full details and update STATUS, SUB_STATUS, LAST_NOTE; LAST_DATE_UPDATE is set to today. |
| Reviewed Pends | Reviewer feedback (PEND_REVIEW, REVIEWER, REVIEWER_REMARKS, DATE_REVIEWED). Invalid reviews must be **ACKNOWLEDGED**; until then a banner and badge are shown everywhere in the module. |
| My Dashboard | Total / Pending / Completed / Valid / Invalid cards, Valid-vs-Invalid donut, 12-month trend, 30-day pends-by-date chart, and a searchable Pend History timeline. |

**Disputes and Intakes — Admin module** (`/di/admin/...`, every role except Associate)
| Tab | What it does |
|---|---|
| Pend Reports | Review queue: all `Pend` rows with STATUS = Pending and no REVIEWER_DOMAIN. Search by Inquiry Number; filter by Manager, Assigned To, Sub Status. Clicking an Inquiry Number opens a **Review** tab. |
| Review | Full pend details + form: Pend Review (Valid/Invalid), Reviewer Name (default: your ASSOCIATE NAME), Reviewer Domain (your DOMAIN, read-only), Date Reviewed (default today), Reviewer Remarks (required). Saving is rejected if someone else reviewed it first. |
| Reviewed Pends | Reviews where REVIEWER_DOMAIN = you **and STATUS is not Completed**, with STATUS / PEND REVIEW colour chips, search and a Valid/Invalid filter. Clicking an Inquiry Number opens an **Edit Review** tab showing the current values and allowing changes to STATUS, PEND REVIEW and REVIEWER REMARKS. Setting STATUS to Completed moves the pend out of the list. |
| My Dashboard | Total Reviewed / Valid / Invalid / Valid Rate, Valid-vs-Invalid donut and a stacked trend chart with Daily / Weekly / Monthly views and a date range. |
| Export to Excel | On Pend Reports and Reviewed Pends: *Export Filtered Results* (current view) or *Export All* (whole `Pend` table). Generates a real `.xlsx` with Python's standard library only. |

Reviewers are notified when an associate acknowledges their review, updates a pend they reviewed, or when a review result changes.

**Executive Dashboard** (left-nav *Dashboard*, Associate `/di/dashboards` and Admin `/di/admin/dashboards`) — a
skeuomorphic executive view of the **entire** `Pend` table (not filtered by user; both audiences see the same data).
Filters: Manager, Assigned To, Sub Status, Date Pended range — every widget refreshes on change. KPI cards (Total
Pending / Completed / Valid / Invalid), Manager Analytics cards, charts (Pending vs Completed, Valid vs Invalid,
Status Distribution, Manager Performance Breakdown, Review Trend by Date) and a Pend Report with search, column
sorting, pagination (25/page) and Export to Excel (filtered results or the entire Pend table). This is separate from
the per-user *My Dashboard* tabs.

**Header** — partner logos switch with theme (light: cb, ct, pi black, ignite · dark: cw, ctw, pi white, ignite),
notification bell with unread counter, dropdown and full history page.

**Profile** — view and edit Associate Name, Employee Number, Program, Manager, Email Address (Carelon-validated).
DOMAIN is the login identity and is read-only. Changes are saved to the `User` table.

**Settings (saved per user in Supabase)** — electric border on/off, accent theme (Blue, Violet, Green, Orange, Pink,
Grey), Light/Dark mode, Landscape/Portrait layout.

## Database setup (one time)

1. In Supabase → **Database → Extensions**, enable **pg_cron**.
2. Open **SQL Editor** and run `supabase/migrations/001_disputes_and_intakes.sql`. It is idempotent and only adds:
   - missing `Pend` columns (+ `id`, acknowledgement and audit columns) and indexes
   - `apex_pend_history`, `apex_notification`, `apex_user_settings` (RLS on, no public access)
   - triggers that compute `PENDED_DAYS`, record history, reset acknowledgement when a review changes,
     and create notifications for reviews, status changes, Valid and Invalid
   - a pg_cron job that recalculates `PENDED_DAYS` daily at 00:05 Asia/Manila
3. Run `supabase/migrations/002_admin_reviews.sql` — adds `REVIEWER_DOMAIN`, `SUB_STATUS`, reviewer notifications,
   and keeps a reviewer-entered `DATE_REVIEWED`.
4. Run `supabase/migrations/003_reviewer_status_edit.sql` — reviewers aren't notified about their own status edits.
5. Run `python scripts/validate_db.py` — it checks the `User` table, program mapping, `Pend` columns and new tables.

Always run migration files **in number order**; each one is safe to re-run.

Because notifications and history are created by **database triggers**, they fire no matter what writes to `Pend`
(the APEX app, a reviewer tool, or a manual edit in the Supabase table editor).

`PENDED_DAYS` (current date − `DATE_PENDED`) is **backend-only**: it is never shown or editable in the app and is
kept for reports, aging and analytics. The database sets it on every insert/update and the pg_cron job refreshes all
rows daily. If you change `APEX_TIMEZONE`, update `public.apex_today()` in the SQL to match.

## Project structure

```
api/index.py              Vercel serverless entry (exposes the Flask WSGI app)
apex/
  __init__.py             App factory, security headers, template context, error pages
  config.py               All settings from environment variables
  supabase.py             PostgREST + Supabase Auth client (server-side only)
  users.py                User table repository + profile field mapping
  pends.py                Pend repository: create/update/acknowledge, dashboard metrics, history
  reviews.py              Reviewer side: review queue, reviews, reviewer dashboard, export rows
  enterprise.py           Executive Dashboard over the whole Pend table (KPIs, managers, charts, report)
  xlsx.py                 Dependency-free .xlsx writer (standard library only)
  notifications.py        Notification inbox
  preferences.py          Per-user appearance settings
  programs.py             Program registry (activate a program by giving it an endpoint)
  dates.py                Timezone-aware business date helpers
  security.py             Password policy/hashing, CSRF, session, route guards
  rbac.py                 Roles, portals and permissions
  navigation.py           Sidebar + tab registry per program
  routes/auth.py          Login, first-time setup, logout
  routes/main.py          Programs, profile, settings, notifications, administration
  routes/di.py            Disputes and Intakes — Associate tabs
  routes/di_admin.py      Disputes and Intakes — Admin tabs, review, export
  templates/              Jinja2 templates
public/static/            CSS, JS, web-optimised images (served by Vercel's CDN)
supabase/migrations/      SQL to run in the Supabase SQL Editor
scripts/validate_db.py    Supabase connection + schema validation
tests/                    Unit/integration tests (in-memory Supabase stand-in)
```

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then fill in SUPABASE_SECRET_KEY and APEX_SECRET_KEY
.\.venv\Scripts\python scripts\validate_db.py
$env:PORT=5055; .\.venv\Scripts\python run.py   # http://127.0.0.1:5055
```

Run tests: `.\.venv\Scripts\python -m unittest discover -s tests -t .`

`truststore` makes Python use the Windows certificate store, which is required on networks that inspect HTTPS.

## Environment variables

See `.env.example`. Required: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `APEX_SECRET_KEY`.
`SUPABASE_SECRET_KEY` is used only on the server and must never be committed or exposed to the browser.

## Deploy (GitHub → Vercel)

1. Create a GitHub repository and push this folder (`.env` and `.venv` are git-ignored):
   ```
   git init && git add . && git commit -m "APEX: Disputes and Intakes module"
   git branch -M main && git remote add origin https://github.com/<org>/apex.git && git push -u origin main
   ```
2. In Vercel: **Add New → Project → Import** the repository. Framework preset: **Other**. No build command.
3. **Settings → Environment Variables**: add every variable from `.env.example` (generate a fresh `APEX_SECRET_KEY`).
4. Deploy. Vercel serves `public/` from its CDN and routes everything else to `api/index.py`.

## Adding the next program module (e.g. COB)

1. Add permissions in `apex/rbac.py`, sidebar/tabs in `apex/navigation.py` under the program key.
2. Create `apex/routes/cob.py` with `@login_required("<permission>", program="cob")` and register it in `apex/__init__.py`.
3. Set `"endpoint"` for the program in `apex/programs.py` — it becomes selectable on the Program Selection page.
