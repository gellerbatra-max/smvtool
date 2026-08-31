# SMV Tool — Project Handoff

**Purpose:** self-built replacement for GSD (General Sewing Data), the licensed
predetermined-motion-time software the user's apparel factory currently uses to set
Standard Minute Values (SMV) for garment operations. Built as an IP-clean, computed
engine (no licensed GSD/MTM tables anywhere) rather than a lookup-table clone.

**GitHub repo:** https://github.com/gellerbatra-max/smvtool
**Commit history:** `6fa5e23` (engine core) → `628b474` (backend + analytics) →
`06fedd3` (frontend, initially incomplete) → `a02a8cf` (frontend fixed: missing
`app.css`, Vitest suite added) → `4c01542` (two Postgres-only bugs found + fixed by
actually running against a live Postgres instance) → `e62b3ad` (CI workflow, all 5
jobs green) → **current** (Docker Compose deployment — see "How to run" below).

## Architecture (as decided with the user)

Three pillars, computed rather than looked up:
1. **Machine time** — deterministic physics: `stitches = seam_length × stitch_density`,
   `time = stitches / effective_SPM`, with an effective-speed model for
   acceleration/curves/pivots (`effective_spm.py`, `machine_time.py`).
2. **Handling time** — Fitts'-law-based parametric model (23-element taxonomy in
   `element_taxonomy.json`), coefficients calibrated to the factory's own time studies,
   NOT a licensed MTM/GSD lookup table (`handling_time.py`).
3. **Allowances** — ILO-published ranges, editable per-factory policy
   (`allowance.py`, `allowance_policy.json`).

Application layer: **PostgreSQL** + **FastAPI** backend, **React SPA** (Vite +
TypeScript) frontend, **Docker Compose** ties all three together.

## Current status by component

| Component | Status | Tests |
|---|---|---|
| Calculation engine (3 pillars + assembly) | ✅ Complete | 82/82 |
| Calibration module (hierarchical coefficient fitting) | ✅ Complete, validated only on synthetic data — see limitations | included above |
| Woven-shirt operation library (CLASSIC/SHORT_SLEEVE/BLOUSE_COLLARLESS, 5 sizes) | ✅ Complete | included above |
| Backend (FastAPI + SQLAlchemy schema + JWT auth + audit log) | ✅ Complete, verified against **both** SQLite and live Postgres | 34/34 (each dialect) |
| Analytics (line balancing, costing, what-if scenarios) | ✅ Complete, standalone | 83/83 |
| Analytics ↔ backend wiring (`analytics_router.py`) | ✅ Complete | included in the 34 |
| Frontend (React SPA) | ✅ Builds clean, type-checks clean, tested | 21/21 |
| End-to-end validation (UI → API → DB) | ✅ Walked by hand over HTTP against both SQLite and Postgres backends | — |
| CI (GitHub Actions) | ✅ All 5 jobs green on every push — engine, analytics, backend×2 dialects, frontend | — |
| Deployment (Docker Compose) | ✅ `docker-compose.yml` + Dockerfiles for db/backend/frontend | — |

**Total: 254 tests, all independently re-run and passing, 0 failing.**

## What changed most recently

Everything above marked ✅ that wasn't true as of `06fedd3` got there across a few
follow-on sessions, each one actually verifying something rather than trusting the
prior write-up:

- **Frontend was fixed** (`a02a8cf`): a missing `app.css` broke the build, plus a
  21-test Vitest suite was added (apiClient, ProtectedRoute/RequireRole,
  CalibrationBadge, LoginPage, a full-App integration test).
- **Postgres was actually tested live** (`4c01542`) — the original sandbox this
  project was built in couldn't start a real Postgres server at all (`shmget EPERM`);
  a plain local install elsewhere could. That live run found and fixed **two real
  Postgres-only bugs** SQLite's test suite structurally could not catch: the initial
  migration's `downgrade()` never dropped the Postgres `user_role` enum type, and
  `DELETE /styles/{id}` hit a `ForeignKeyViolation` on any style with change-log
  history (SQLite doesn't enforce foreign keys by default, so this had silently
  "worked" the whole time under test). Full detail in `backend/SCHEMA.md`.
- **CI added** (`e62b3ad`): all 254 tests now re-run on every push, including a real
  `postgres:16` service container — not just SQLite.
- **Docker Compose added**: `db` + `backend` (runs `alembic upgrade head` on
  container start) + `frontend` (nginx-served static build), wired together with a
  required `.env` so no service can accidentally boot on dev-default secrets.

## How to run the whole stack (Docker Compose)

```bash
cp .env.example .env   # then fill in real values — POSTGRES_PASSWORD, SMV_JWT_SECRET,
                        # SMV_BOOTSTRAP_ADMIN_PASSWORD; compose refuses to start without them
docker compose up --build
# frontend: http://localhost:5173   backend: http://localhost:8000/docs
```

Three services: `db` (Postgres 16, named volume for persistence), `backend`
(runs `alembic upgrade head` on container start, then FastAPI), `frontend`
(Vite build served via nginx, SPA routing configured). See
`docker-compose.yml` / `.env.example` / `backend/Dockerfile` /
`frontend/Dockerfile`.

## How to run the backend locally (without Docker)

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=.:smv_engine uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs
# A bootstrap administrator is auto-seeded on first startup — check app/main.py's
# _run_startup_init() for the seeded username, or create one via the API.
```

Backend tests: `cd backend && PYTHONPATH=.:smv_engine python -m pytest tests/ -q`
(34/34 passing, against SQLite — see next section for why not Postgres).

Engine tests: `cd . && PYTHONPATH=. python -m pytest test_engine.py test_calibration.py
test_shirt_library.py -q` (82/82 passing) — run from the repo root where
`element_taxonomy.json` etc. live.

Analytics tests: `cd analytics && SMV_ENGINE_DIR=$(pwd)/.. PYTHONPATH=. python -m
pytest tests/ -q` (83/83 passing).

## Known, disclosed limitations (not bugs — documented in the code/reports)

1. ~~**PostgreSQL was never actually tested.**~~ **Resolved.** The original sandbox
   this project was built in couldn't start Postgres at all (`initdb` failed with
   `shmget EPERM` at the syscall level), but that turned out to be sandbox-specific,
   not universal — a plain local Postgres 16 install ran it for real: `alembic upgrade
   head` against a live database, a full upgrade→downgrade→upgrade cycle, the same
   34-test backend suite re-run against Postgres instead of SQLite (34/34), and the
   login→seed→compute→bulletin→delete flow exercised by hand over HTTP. This found and
   fixed **two real Postgres-only bugs** that SQLite's test suite structurally could
   not have caught (SQLite has no native enum type and doesn't enforce foreign keys by
   default): the migration's `downgrade()` didn't drop the Postgres `user_role` enum
   type, and deleting a style with change-log history hit a `ForeignKeyViolation`
   because the FK had no `ON DELETE` rule. Both fixed — see `backend/SCHEMA.md`'s
   "Postgres vs SQLite testing" section for the full detail and what's still not
   covered (concurrency/transaction-isolation behavior under load, JSONB operators).
2. **Calibration is validated only against synthetic data.** No real factory time-study
   data has been collected yet. `engine_phase1_report.md` §5 sets a concrete target:
   enough real observations to get the coverage report to ≥80% "sufficient" on scope-1
   symbols. Until that happens, don't trust the engine's absolute SMV numbers for real
   payroll/costing decisions — only its relative rankings and structure.
3. **The `BLOUSE_COLLARLESS` variant is not a genuine blouse silhouette** — it reuses
   the shirt's body pattern with only the neckline/buttonhole set changed. A real blouse
   (darted/princess-seamed body, different sleeve) needs its own points-of-measure spec
   that nobody has supplied yet.
4. **One unresolved numeric discrepancy**, honestly flagged rather than papered over:
   `seam_geometry.json`'s stored `machine_time_crosscheck` field (4.966 min) doesn't
   match what the current code recomputes (3.221 min, ~35% off) via the exact function
   the codebase actually calls. Multiple candidate explanations were tested and ruled
   out (see `phase2_operation_library_report.md` §2) — root cause is genuinely unknown.
   Does not affect the geometry-only crosscheck (stitch-path totals), which passes
   exactly.
5. **A real, fixed bug found and corrected this session:** `line_balancing.py`'s
   `bottleneck_smv_min` used to report the raw binary-search cap value rather than the
   actual realized max station load, causing a tiny (~1e-8 relative) but real
   inconsistency. Fixed to report the actual achieved value; verified exact-equality
   in tests.

## Credentials / access needed to continue

- **GitHub**: push access to `gellerbatra-max/smvtool` is required to land further
  commits. Whether that's available depends entirely on the environment a given
  session is running in (a configured credential, an authenticated `git` credential
  helper, etc.) — it is not something this document can promise session to session.
  If push fails, the user can always push manually from a local clone.
- **Local files**: the user also granted host access to
  `/Users/raveenl/Documents/Claude Code oxaam/SMV tool/smvtool/` (read-write) — an
  earlier, now-stale copy of just the engine bundle lives there (pre-application-layer;
  the GitHub repo is more current).
- No other external credentials are in use (OpenAlex is configured but unused by this
  project).

## Repository layout

```
smvtool/
├── HANDOFF.md                     <- this file
├── README_HANDOFF.md              <- engine-only handoff notes (superseded by this file for overall status)
├── docker-compose.yml, .env.example   <- whole-stack deployment (db + backend + frontend)
├── .github/workflows/ci.yml       <- all 254 tests re-run on every push (5 jobs)
├── *.py, *.json, *.csv, *.md      <- the calculation engine (repo root = engine bundle)
│                                     handling_time.py / machine_time.py / effective_spm.py /
│                                     allowance.py / smv_assembly.py / shirt_library.py /
│                                     calibration_fit.py / calibration_diagnostics.py /
│                                     time_study_loader.py + schema
├── test_engine.py, test_calibration.py, test_shirt_library.py   <- engine tests (82)
├── analytics/                     <- standalone line-balancing/costing/what-if module (83 tests)
│   ├── line_balancing.py, costing.py, what_if.py, engine_loader.py
│   ├── INTEGRATION.md             <- how a backend should call this module
│   └── tests/
├── backend/                       <- FastAPI application (34 tests, both SQLite & Postgres)
│   ├── Dockerfile, docker-entrypoint.sh   <- runs `alembic upgrade head` before uvicorn
│   ├── app/
│   │   ├── main.py, models.py, schemas.py, auth.py, audit.py, engine_bridge.py
│   │   ├── analytics/             <- copy of analytics/ wired in via analytics_router.py
│   │   └── routers/               <- auth, users, styles, library, calibration, allowance, analytics
│   ├── smv_engine/                <- VENDORED frozen copy of the root engine (see engine_bridge.py)
│   ├── migrations/                <- Alembic (verified against live Postgres, see SCHEMA.md)
│   ├── SCHEMA.md                  <- schema + design decisions + Postgres/SQLite verification log
│   └── tests/                     <- conftest.py supports TEST_DATABASE_URL for Postgres runs
└── frontend/                      <- React SPA, builds clean, 21/21 tests passing
    ├── Dockerfile, nginx.conf     <- multi-stage build, served static via nginx
    ├── src/{api,auth,components,pages,lib}/
    └── tests/                     <- apiClient, ProtectedRoute, CalibrationBadge, LoginPage, App integration
```

## Suggested next steps, in order

1. **Expand frontend test coverage.** The current 21 tests cover the API client, auth
   guarding, one page, and one integration smoke test — not every page
   (StyleEditorPage, BulletinPage, AnalyticsPage, LibraryPage don't have dedicated
   component tests yet).
2. **Decide on a LICENSE.** The project's entire premise is being IP-clean; an
   explicit license (even a private/proprietary one) closes that loop formally.
3. **Harden default-secret behavior in the non-Docker path.** `docker-compose.yml`
   already refuses to start without real secrets; running the backend directly with
   `uvicorn` still only logs a warning if `SMV_JWT_SECRET`/
   `SMV_BOOTSTRAP_ADMIN_PASSWORD` are left on their dev defaults.
4. **The real factory time-study campaign**, whenever the user has floor access — per
   `engine_phase1_report.md` §5. This is the actual bottleneck on the engine being
   trustworthy for payroll-grade numbers, independent of the application layer's
   completeness, which is otherwise in good shape.
