# SMV Tool — Project Handoff

**Purpose:** self-built replacement for GSD (General Sewing Data), the licensed
predetermined-motion-time software the user's apparel factory currently uses to set
Standard Minute Values (SMV) for garment operations. Built as an IP-clean, computed
engine (no licensed GSD/MTM tables anywhere) rather than a lookup-table clone.

**GitHub repo:** https://github.com/gellerbatra-max/smvtool (a GitHub credential is
required to push further commits — see "Credentials" below)
**Latest commit:** `06fedd3` ("Add React frontend (Vite + TypeScript) - source only, incomplete")
**Commit history:** `6fa5e23` (engine core) → `628b474` (backend + analytics + review fixes)
→ `06fedd3` (frontend, incomplete)

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

Application layer decisions: **PostgreSQL** (tested against SQLite in this sandbox —
disclosed limitation, see below) + **FastAPI** backend, **React SPA** (Vite +
TypeScript) frontend.

## Current status by component

| Component | Status | Tests |
|---|---|---|
| Calculation engine (3 pillars + assembly) | ✅ Complete | 35/35 |
| Calibration module (hierarchical coefficient fitting) | ✅ Complete, validated only on synthetic data | +27 (62 total) |
| Woven-shirt operation library (CLASSIC/SHORT_SLEEVE/BLOUSE_COLLARLESS, 5 sizes) | ✅ Complete | +20 (82 total) |
| Backend (FastAPI + SQLAlchemy schema + JWT auth + audit log) | ✅ Complete, tested against SQLite **and live Postgres** — see below | 34/34 (both backends) |
| Analytics (line balancing, costing, what-if scenarios) | ✅ Complete, standalone | 83/83 |
| Analytics ↔ backend wiring (`analytics_router.py`) | ✅ Complete | included in the 34 |
| **Frontend (React SPA)** | ⚠️ **Source written, UNVERIFIED — see below** | **0 (tests/ is empty)** |
| End-to-end validation (UI → API → DB) | ❌ Not done — blocked on frontend | — |
| Deployment guide | ❌ Not written — blocked on frontend | — |

## ⚠️ The one thing you need to know before doing anything else

The Frontend track (a delegated sub-agent) wrote a substantial, apparently complete
React app — API client, auth, all the pages described in the plan, export utilities —
but **stalled partway through** (45+ minutes with no new activity, almost certainly
stuck inside a long-running `npm install`/`npm run build`/`npm test` command) and had
to be force-stopped to recover its output. As a result:

- **The frontend has never been built, run, or tested.** `npx tsc --noEmit` / `npm run
  build` / `npm run dev` have not been executed successfully against this code — it may
  have compile errors.
- **`frontend/tests/` is empty.** No Vitest/React-Testing-Library tests exist despite
  the plan asking for them.
- **It has never talked to the real backend.** No login → create style → seed from
  library → compute → view bulletin flow has been exercised end-to-end.
- `node_modules/` was deliberately excluded from git (regenerable, `npm install`
  restores it exactly from `package-lock.json`).

**Your first move in a new session should be:** `cd frontend && npm install && npx tsc
-b` to see what breaks, fix it, then run the backend locally (see below) and walk the
one real user flow (login → seed CLASSIC/M style → compute → view bulletin → run a
what-if) by hand before trusting anything else about it.

## How to run the backend locally

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

- **GitHub**: a credential named "GitHub" was configured for this project (Customize →
  Credentials) and used via `os.environ["GITHUB_TOKEN"]` to clone/push
  `gellerbatra-max/smvtool`. If starting fresh on a different account, this credential
  will need to be re-added, or the user can push manually from a local clone.
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
├── backend/                       <- FastAPI application (34 tests)
│   ├── app/
│   │   ├── main.py, models.py, schemas.py, auth.py, audit.py, engine_bridge.py
│   │   ├── analytics/             <- copy of analytics/ wired in via analytics_router.py
│   │   └── routers/               <- auth, users, styles, library, calibration, allowance, analytics
│   ├── smv_engine/                <- VENDORED frozen copy of the root engine (see engine_bridge.py)
│   ├── migrations/                <- Alembic
│   ├── SCHEMA.md                  <- schema + design decisions + Postgres/SQLite disclosure
│   └── tests/
└── frontend/                      <- React SPA — SEE WARNING ABOVE, unverified
    ├── src/{api,auth,components,pages,lib}/
    └── tests/                     <- EMPTY
```

## Suggested next steps, in order

1. `cd frontend && npm install` — see if it even installs cleanly from the committed
   `package-lock.json`.
2. `npx tsc -b` — find and fix any TypeScript errors.
3. `npm run dev` against a locally running backend (see above) — walk the login → seed
   style → compute → bulletin → what-if flow by hand.
4. Write the Vitest/RTL test suite the plan asked for (component tests + at least one
   integration test against a real running backend).
5. Only then: end-to-end validation, deployment guide (Docker Compose for
   Postgres+FastAPI+React is the natural shape), and a real Postgres test run.
6. Separately, whenever the user has floor access: start the real factory time-study
   campaign per `engine_phase1_report.md` §5 — this is the actual bottleneck on the
   engine being trustworthy for payroll-grade numbers, independent of the application
   layer's completeness.
