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
      users_router.py            POST/GET /users, PATCH /users/{id} (admin only)
      styles_router.py            styles CRUD, operations CRUD, compute, bulletin, change-log
      library_router.py            GET /library, GET /library/bulletin
      calibration_router.py         GET /calibration/status
      allowance_router.py            GET/POST /allowance-policies, GET /allowance-policies/{id}
  smv_engine/                 vendored, unmodified copy of the engine handoff bundle
  migrations/                 Alembic migrations
  scripts/
    seed_demo_styles.py         legacy 15-style grid seeder
    seed_demo_database.py       CLI shim for seed_demo/ (see "Demo data" below)
    seed_demo/                  the full demo-dataset seed package (api/dataset/seed/cli)
  tests/                        pytest suite (66 tests as of this addition)
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

Every table starts empty (or near-empty -- just the bootstrap admin and
allowance policy v1) until someone uses the app. Two seed scripts populate
one with demo data; both are entirely API-driven (login, then the same
`POST`/`PUT`/`DELETE` calls a human would make), idempotent, and safe to
re-run.

### `seed_demo_database.py` -- the full demo dataset (recommended)

```bash
python scripts/seed_demo_database.py --base-url http://localhost:8000
```

Populates **all six tables**, not just styles:

- **5 users** across all three roles (`priya.nair`, `tomasz.kowalski` --
  `ie_engineer`; `rita.okafor` -- `administrator`; `mei.lin` -- `viewer`;
  `arjun.devarajan` -- `viewer`, deliberately **disabled**), each logged
  into separately so `created_by_id` / `computed_by_id` /
  `change_log.user_id` vary realistically instead of everything being the
  bootstrap admin. They share one password, `demo-pass-2026` by default
  (**non-production** -- override with `--demo-password` or
  `SMV_SEED_DEMO_PASSWORD`).
- **A second allowance-policy version** (`CONTINGENCY` 1.0% -> 1.5%,
  derived from the live v1 document), created by `rita.okafor` and made
  active.
- **12 realistically-named styles** (several intentionally share an
  initial product name, like a real factory's style list would) with a
  mix of: a style recomputed under both policy versions (two
  `smv_results` generations), an operation rename, a duplicated operation
  left deliberately uncomputed (a "--" row in the Bulletin), a
  machine-class swap + recompute, a deleted operation, a style left
  entirely uncomputed ("Not computed yet."), and plain style-field edits
  -- so the Styles list, Bulletin, Operations editor, Analytics, and each
  style's change-log all have something genuinely varied to show. See
  `scripts/seed_demo/dataset.py`'s `DEMO_STYLES` for the full per-style
  rationale.

Identity is tracked via a `[demo-seed:<key>]` tag in each style's
`notes` (not by name -- see the module docstring for why). Options:

```bash
python scripts/seed_demo_database.py \
  --base-url http://localhost:8000 \
  --username admin --password <bootstrap admin password> \
  --demo-password <shared demo-user password> \
  --wait-for-backend 60 \
  --reset-demo            # delete every previously-seeded demo style first, then reseed
```

Env fallbacks (a flag always wins): `SMV_SEED_BASE_URL`; `SMV_SEED_USERNAME`
falls back to `SMV_BOOTSTRAP_ADMIN_USER` then `admin`; `SMV_SEED_PASSWORD`
falls back to `SMV_BOOTSTRAP_ADMIN_PASSWORD` then `changeme123`;
`SMV_SEED_DEMO_PASSWORD`.

Via Docker Compose (opt-in `demo` profile -- never runs on a plain
`docker compose up`):

```bash
docker compose --profile demo run --rm seed-demo [--reset-demo]
```

### `seed_demo_styles.py` -- the lighter 15-style grid

```bash
python scripts/seed_demo_styles.py --base-url http://localhost:8000
```

Creates one style per (variant, size) combination from the seeded
`shirt_library.py` catalog -- 3 variants x 5 sizes = 15 styles, all named
`"CLASSIC S"` etc. and computed under the default policy -- so Styles
List / Bulletin / Analytics have *something* to show immediately, without
touching users or allowance policies. Safe to re-run: it skips any
variant/size combo whose exact name already exists. Defaults to the
bootstrap admin credentials; pass `--username`/`--password` for a
different account.

## API surface

- `POST /auth/login`, `GET /auth/me`
- `POST /users`, `GET /users`, `PATCH /users/{id}` (administrator only)
- `POST/GET/PUT/DELETE /styles`, `/styles/{id}`
- `POST /styles/{id}/operations`, `PUT/DELETE /styles/{id}/operations/{op_id}`
- `POST /styles/{id}/compute` — runs the engine and persists `smv_results` rows
- `GET /styles/{id}/bulletin` — full operation bulletin + latest audit trail per op
- `GET /styles/{id}/change-log` — full per-field audit history for a style
- `GET /library`, `GET /library/bulletin` — browse the seeded shirt_library.py operation library
- `GET /calibration/status` — honest calibration-pending vs literature-grounded coefficient report
- `GET/POST /allowance-policies`, `GET /allowance-policies/active`, `GET /allowance-policies/{id}` — the last of these includes the full `document` (the list/active endpoints intentionally don't)

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

66/66 passing as of this addition, verified against both SQLite and a
live Postgres 16 instance (`TEST_DATABASE_URL=postgresql+psycopg://...`) —
see `SCHEMA.md` for the Postgres-testing disclosure and `HANDOFF.md` for
when that verification actually happened.

## What is NOT built yet (out of scope for this backend track)

Per the project's tracked deliverables, the following remain for later
tracks: React frontend, Excel/PDF export, line-balancing module, costing/
production-target module, what-if scenario comparison, and a full-stack
deployment guide (this README covers the backend only).
