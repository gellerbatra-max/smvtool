# SMV Application — Database Schema

## Overview

This backend persists **inputs to** and **outputs of** the SMV calculation
engine — it never stores a hardcoded SMV number, timing constant, or
GSD/MTM/PMTS-style lookup table. Every number in `smv_results` is the live
output of a call into `smv_engine/` (vendored, unmodified, from the engine
handoff bundle) at the moment it was computed; every `operations.steps` row
is only geometry/element-selection **input** (path lengths, element codes,
machine classes) that could be fed straight back into
`smv_assembly.assemble_operation()` to reproduce that same SMV.

Target database: **PostgreSQL** (JSONB columns, native). See "Postgres vs
SQLite testing" below for an important disclosure about how this schema was
actually tested in this environment.

## Entity-relationship summary

```
users ──< allowance_policies (created_by)
users ──< styles (created_by)
users ──< smv_results (computed_by)
users ──< change_log (user)

styles ──< operations (style_id, cascade delete)
styles ──< smv_results (style_id, cascade delete)
styles ──< change_log (style_id, denormalized for fast per-style audit queries)

operations ──< smv_results (operation_id, cascade delete)

allowance_policies ──< smv_results (allowance_policy_version_id)
```

## Tables

### `users`
Login accounts. `role` is a Postgres ENUM (`ie_engineer` / `viewer` /
`administrator`) — see `models.UserRole`. `password_hash` is a bcrypt hash
(via the `bcrypt` library directly, hashed/verified in `app/auth.py`'s
`hash_password()`/`verify_password()`). No plaintext password ever touches
the database.

### `allowance_policies`
Versioned snapshots of an allowance-policy document (the same JSON shape as
the engine's own `allowance_policy.json`, consumed directly by
`allowance.AllowancePolicy(raw_dict)`). **A factory may edit its allowance
policy over time** (categories, profile percentages, application rules);
each edit inserts a **new row** with `version = max(version for that
policy_name) + 1` and flips `is_active` — it never mutates an existing row.
This is the mechanism that keeps a historical SMV reproducible: `smv_results`
stamps the exact `allowance_policies.id` (hence exact document) that was
active when it was computed, so re-running `assemble_operation()` against
that stored document reproduces the same number even after the factory has
since revised its policy. `document` is `JSONB`.

### `styles`
A garment style: `garment_type` (currently `woven_shirt`), `variant`
(`CLASSIC` / `SHORT_SLEEVE` / `BLOUSE_COLLARLESS` — matching
`shirt_library.py`'s variants), `size` (`S`–`XXL`), `bundle_size` (operator-
station bundle size, a style/line parameter per `smv_assembly.py`'s own
docstring — not a fitted constant). `created_by`/timestamps for audit
provenance at the whole-style level (per-field history lives in
`change_log`).

### `operations`
One row per operation belonging to a style, in `sequence` order. `steps` is
the **raw step list** in exactly `smv_assembly.py`'s step-dict grammar
(`{"kind": "handling"|"bundle"|"seam"|"cycle", ...}`) — this is what gets
handed to `sa.Operation(name, steps, bundle_size)` and
`sa.assemble_operation()` to (re)compute. Storing the raw steps rather than
a computed SMV is what makes an operation's timing fully re-derivable (e.g.
after an allowance-policy version bump, or after a future calibration run
updates the taxonomy's fitted constants) without ever having stored a
substitute number. `steps` is `JSONB`.

### `smv_results`
One **immutable** row per computed-SMV event for an operation — a recompute
inserts a new row rather than updating in place, so the full history of
"what did this operation's SMV read at time T" is preserved for
payroll/incentive audit. Carries:
  - `st_op_s` / `st_op_min` / `bt_op_s` / `bt_op_min` — the engine's own
    `ST_op_s`/`ST_op_min`/`BT_op_s`/`BT_op_min` output fields.
  - `audit_trail` (`JSONB`) — the full `assemble_operation()` return dict
    (per-step records: element/seam/cycle basic+standard time, binding
    choice for `MAX(t_machine, t_guide)`, resolved allowance percentages),
    exactly as the engine produced it — the "defensible under audit"
    requirement from the project brief is met by storing this whole-cloth,
    not a summary.
  - `allowance_profile` + `allowance_policy_version_id` — which profile
    (e.g. `WOVEN_TOPS_DECOMPOSED`) and which **exact policy document
    version** were applied.
  - `engine_version` — a stamp identifying the vendored engine bundle
    (`engine_bridge.ENGINE_VERSION`); bump this string if the vendored
    `smv_engine/` is ever updated to a new handoff bundle, so historical
    rows stay attributable to the code that produced them.
  - `calibration_version` — `NULL` today (no real-factory calibration has
    been run against this application's data yet; see
    `engine_phase1_report.md`). Once `calibration_fit.calibrate_all()` is
    run against real time-study data and its fitted taxonomy is wired into
    `engine_bridge`, stamp a version identifier here so historical SMVs
    stay attributable to the calibration state that produced them.

One design note: `audit_trail` occasionally contains `+inf` for a straight
seam's curvature radius (physically correct — Fitts-law steering has no
curvature term for a zero-curvature path) which is not valid JSON. The
application sanitizes this at the API/persistence boundary only
(`engine_bridge._sanitize_json`, `inf`/`-inf`/`NaN` → `null`) — the engine's
own computation is never touched, only how its output is serialized.

### `change_log`
Append-only audit trail. **One row per changed field** per write (never one
row summarizing a whole multi-field update) — `app.audit.diff_and_log()`
compares a before/after snapshot dict and writes a row per differing key;
`app.audit.log_create()`/`log_delete()` write one whole-entity row
(`field="*"`) for creates/deletes. `entity_type` is `"style"` /
`"operation"` / `"allowance_policy"` / `"user"`; `style_id` is denormalized
onto every row (even operation-level changes) so `GET
/styles/{id}/change-log` is a single indexed query rather than a join
through `operations`. `prior_value`/`new_value` are JSON-stringified `TEXT`
(not `JSONB` — an audit trail is read sequentially, never queried
structurally, so there's no benefit to binary JSON storage here, and TEXT
keeps the diff human-readable in a raw `SELECT`).

A no-op update (new value equals old value) writes **zero** change_log rows
— this is intentional audit semantics (see `test_audit.py::
test_noop_update_writes_no_change_log_row`): a change_log row asserts "this
field's value changed at this time", not "a save button was clicked".

## Design decisions

- **JSONB via a dialect-shimmed type (`app.database.JSONBType`)** rather
  than importing `sqlalchemy.dialects.postgresql.JSONB` directly into
  `models.py`. On Postgres it IS `JSONB` (verified: see "Postgres vs SQLite
  testing"); on any other dialect it degrades to SQLAlchemy's generic
  `JSON`. This keeps `models.py` fully dialect-agnostic so the exact same
  ORM classes work against the SQLite test fallback.
- **String UUIDs as primary keys** (not Postgres-native `UUID` type) so the
  same schema also works verbatim under SQLite (which has no native UUID
  type) without a second shim layer, at the cost of a few bytes per row and
  losing Postgres's binary UUID storage/index efficiency. Given SMV data
  volumes (thousands of operations per factory, not billions), this
  trade-off is a non-issue.
- **Versioned allowance policy, immutable SMV results** — both driven by
  the same requirement in the project brief: "every SMV feeds
  payroll/incentive schemes and must be defensible under audit." Anything
  that could silently change the meaning of a historical number (the policy
  it was computed against) is versioned; the number itself, once computed,
  is never updated in place.
- **`change_log` is a first-class table, not a generic
  "audit"/"revisions" JSON blob** — per-field prior/new values in plain
  columns make "what changed, by whom, when" directly queryable/reportable
  without JSON-path gymnastics, which is what an IE audit or payroll
  dispute actually needs.

## Postgres vs SQLite testing

**Update:** this schema and backend have now been exercised against a real,
live PostgreSQL 16 server (Homebrew, macOS), not just SQLite plus a
DDL-compile check. The original sandbox this project was first built in
could not start Postgres at all — `initdb` failed unconditionally with
`shmget EPERM`, a System-V-IPC restriction at the sandbox level, not a
Postgres misconfiguration — so every prior claim in this section was
necessarily SQLite-only. That restriction does not apply everywhere; a
plain local install was enough to run the real thing. The historical
detail is kept below for anyone hitting the same sandbox limitation.

**What was actually run against live Postgres, not just SQLite:**

- `alembic upgrade head` against a fresh database — real DDL execution, not
  a compile check. Confirms `document`/`steps`/`audit_trail` land as
  genuine `jsonb` columns (verified via `\d` and `jsonb_typeof()`), not the
  SQLite `JSON`/`TEXT` fallback.
- A full `upgrade head` → `downgrade base` → `upgrade head` cycle.
- The complete backend pytest suite (34/34) with `TEST_DATABASE_URL`
  pointed at Postgres instead of SQLite (each test gets its own Postgres
  *schema*, created and dropped per test, in place of SQLite's per-test
  temp file — see `tests/conftest.py`).
- The real login → seed style from library → compute → bulletin → delete
  flow, exercised by hand over HTTP against a Postgres-backed server.

**Two real, Postgres-only bugs were found and fixed by this — both were
structurally invisible under SQLite:**

1. **The initial migration's `downgrade()` dropped tables but never dropped
   the `user_role` enum type Postgres creates for `sa.Enum` columns.**
   SQLite has no native enum type, so there was nothing to leave behind;
   on Postgres, a `downgrade` → `upgrade` cycle failed on re-upgrade with
   `type "user_role" already exists`. Fixed: `downgrade()` now explicitly
   drops the enum (`sa.Enum(...).drop(bind, checkfirst=True)`), a no-op on
   SQLite.
2. **Deleting a style with change-log history raised a
   `ForeignKeyViolation` on Postgres** (`change_log.style_id → styles.id`
   had no `ON DELETE` rule, so Postgres defaulted to blocking the delete).
   SQLite doesn't enforce foreign keys by default, so `DELETE /styles/{id}`
   silently "worked" under the SQLite test suite the whole time by leaving
   an orphaned FK value SQLite never checked. Fixed with `ondelete="SET
   NULL"` on that column (`models.py` and the migration) — the audit row
   survives the delete with `style_id` nulled, which matches the schema's
   own stated intent (`style_id` was already nullable, documented as
   "denormalized for fast per-style audit queries") and this project's
   broader audit-defensibility requirement: deleting a style must not
   erase its history.

**Still not verified**, and worth doing before a real deployment:
Postgres-specific concurrency/transaction-isolation behavior under
concurrent writers, connection-pool sizing under production load, and
`JSONB`-specific operators (`->>`, `@>`, GIN indexing) if the application
ever grows to query inside `steps`/`audit_trail` rather than just
storing/retrieving them whole.

<details>
<summary>Historical note: the original sandbox's Postgres restriction (for reference)</summary>

The environment this backend was first built in could not run a real
PostgreSQL server. A `postgresql` conda package was installed
(`initdb`/`pg_ctl`/`postgres` 18.6, verified present in `$PATH`), but
`initdb`'s bootstrap step failed unconditionally with:

```
FATAL:  could not create shared memory segment: Operation not permitted
DETAIL:  Failed system call was shmget(key=..., size=56, 03600).
```

This was reproduced across multiple configurations
(`shared_memory_type=mmap`, `dynamic_shared_memory_type=posix`, reduced
`shared_buffers`/`max_connections`, `--no-sync`) and confirmed at the
syscall level: a direct `shmget(IPC_PRIVATE, ...)` call succeeded in that
sandbox, but `shmget(<nonzero key>, ..., IPC_CREAT|IPC_EXCL, 0600)` — the
exact call Postgres's postmaster makes for its small anchor/control
segment, made regardless of `shared_memory_type` — failed with `EPERM`.
That is a sandbox-level System-V-IPC restriction, not a Postgres
misconfiguration, and could not be worked around by GUC tuning. It simply
did not reproduce in a plain local (non-sandboxed) environment.

</details>
