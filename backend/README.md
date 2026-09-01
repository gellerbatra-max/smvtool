# SMV Application Backend

FastAPI + SQLAlchemy service layer over the vendored SMV calculation engine
(`smv_engine/`, unmodified from the engine handoff bundle). See `SCHEMA.md`
for the database design and an important disclosure about Postgres-vs-SQLite
testing in this environment.

## Layout

```
backend/
  app/
    main.py              FastAPI app, CORS, startup DB init/seeding
    database.py           SQLAlchemy engine/session + dialect-aware JSONBType
    models.py              ORM models (see SCHEMA.md)
    schemas.py              Pydantic request/response models
    auth.py                  JWT auth, bcrypt password hashing, role dependencies
    audit.py                  change_log writer (diff_and_log/log_create/log_delete)
    policy_service.py         allowance_policies versioning bookkeeping
    engine_bridge.py           THE ONLY module that imports the SMV engine
    routers/
      auth_router.py            POST /auth/login, GET /auth/me
      users_router.py            POST/GET /users (admin only)
      styles_router.py            styles CRUD, operations CRUD, compute, bulletin, change-log
      library_router.py            GET /library, GET /library/bulletin
      calibration_router.py         GET /calibration/status
      allowance_router.py            GET/POST /allowance-policies
  smv_engine/                 vendored, unmodified copy of the engine handoff bundle
  migrations/                 Alembic migrations
  scripts/
    seed_demo_styles.py         populate demo Style records (see "Demo data" below)
  tests/                        pytest suite (38 tests as of this addition)
  requirements.txt
  alembic.ini
```

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Running against PostgreSQL (target deployment)

```bash
export SMV_DATABASE_URL="postgresql+psycopg://smv_user:smv_password@localhost:5432/smv_app"
export SMV_JWT_SECRET="<a long random secret -- required in production>"
export SMV_BOOTSTRAP_ADMIN_USER="admin"
export SMV_BOOTSTRAP_ADMIN_PASSWORD="<a real password>"

alembic upgrade head          # apply the schema
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The first startup (via `alembic upgrade head` + the app's own startup hook)
seeds the default allowance policy (v1, from the vendored engine's shipped
`allowance_policy.json`) and a bootstrap administrator account if no users
exist yet. **Change `SMV_BOOTSTRAP_ADMIN_PASSWORD` before any real
deployment** — the app prints a loud warning to stdout if it falls back to
the dev default.

## Running against SQLite (quick local trial / this sandbox)

```bash
export SMV_DATABASE_URL="sqlite:///./smv_app.db"     # this is also the default if unset
uvicorn app.main:app --reload
```

**Important**: this sandbox could not run a real PostgreSQL server (see
`SCHEMA.md`'s "Postgres vs SQLite testing" section for the exact failure
and why) — the SQLite path is what has actually been exercised end-to-end
here. Postgres-specific behavior (JSONB operators, connection pooling under
load, transaction isolation) has NOT been runtime-tested. Before a real
deployment, run the migration and full test suite against an actual
Postgres instance.

## Demo data

The `styles` table starts empty -- every Style is normally created through
the app (Styles -> New style). To populate a running instance with
realistic demo data instead of an empty table, run:

```bash
python scripts/seed_demo_styles.py --base-url http://localhost:8000
```

This creates one style per (variant, size) combination from the seeded
`shirt_library.py` catalog -- 3 variants x 5 sizes = 15 styles -- and
computes each one, so Styles List / Bulletin / Analytics have something to
show immediately. Safe to re-run: it skips any variant/size combo whose
exact name already exists. Defaults to the bootstrap admin credentials;
pass `--username`/`--password` for a different account.

## API surface

- `POST /auth/login`, `GET /auth/me`
- `POST /users`, `GET /users` (administrator only)
- `POST/GET/PUT/DELETE /styles`, `/styles/{id}`
- `POST /styles/{id}/operations`, `PUT/DELETE /styles/{id}/operations/{op_id}`
- `POST /styles/{id}/compute` — runs the engine and persists `smv_results` rows
- `GET /styles/{id}/bulletin` — full operation bulletin + latest audit trail per op
- `GET /styles/{id}/change-log` — full per-field audit history for a style
- `GET /library`, `GET /library/bulletin` — browse the seeded shirt_library.py operation library
- `GET /calibration/status` — honest calibration-pending vs literature-grounded coefficient report
- `GET/POST /allowance-policies`, `GET /allowance-policies/active`

Interactive OpenAPI docs are served at `/docs` once the app is running.

## Roles

- `viewer` — read-only (styles, operations, bulletins, library, calibration status)
- `ie_engineer` — everything `viewer` can do, plus create/edit styles & operations, run computes
- `administrator` — everything `ie_engineer` can do, plus user management and allowance-policy edits

## Running the tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -q
```

38/38 passing as of this addition (against the SQLite fallback in this
sandbox — see `SCHEMA.md` for the Postgres-testing disclosure; note that
Postgres itself has since been exercised in a later session per `HANDOFF.md`).

## What is NOT built yet (out of scope for this backend track)

Per the project's tracked deliverables, the following remain for later
tracks: React frontend, Excel/PDF export, line-balancing module, costing/
production-target module, what-if scenario comparison, and a full-stack
deployment guide (this README covers the backend only).
