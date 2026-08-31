#!/bin/sh
# Applies the Alembic migration chain before the app starts, rather than
# relying on app.main's create_all() fallback -- see backend/SCHEMA.md's
# "Postgres vs SQLite testing" section for why the migration path (not
# create_all) is the one that's actually been exercised against Postgres.
set -e

echo "Running database migrations..."
alembic upgrade head

exec "$@"
