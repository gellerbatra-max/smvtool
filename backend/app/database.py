"""
database.py -- SQLAlchemy engine/session setup.

Dialect selection is driven entirely by DATABASE_URL:
  - postgresql+psycopg://...   -> real Postgres, JSONB columns are native JSONB
  - sqlite:///...              -> SQLite fallback (see README/SCHEMA.md for why
                                   this fallback exists), JSONB columns are
                                   shimmed onto SQLite's JSON type via the
                                   JSONBType below so the ORM models are
                                   completely dialect-agnostic.

No code outside this module should import sqlalchemy.dialects.postgresql
directly -- always go through JSONBType so models.py works unchanged against
either backend.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, JSON, TypeDecorator
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB


DATABASE_URL = os.environ.get(
    "SMV_DATABASE_URL",
    "sqlite:///./smv_app.db",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


class JSONBType(TypeDecorator):
    """Dialect-aware JSONB shim.

    On Postgres this behaves exactly like sqlalchemy.dialects.postgresql.JSONB
    (native JSONB column, indexable, binary-stored). On any other dialect
    (SQLite in our test fallback) it degrades to SQLAlchemy's generic JSON
    type, which SQLite stores as TEXT with JSON functions layered on top.
    Semantics for our use (store/retrieve a JSON-serializable dict or list)
    are identical; Postgres-specific operators (e.g. `->>`, `@>`, GIN
    indexing) are NOT available under the SQLite fallback -- flagged in
    SCHEMA.md and the test report.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Used by tests and by the dev bootstrap script.
    Production deployments should use Alembic migrations (migrations/)
    instead of this function."""
    import app.models  # noqa: F401 -- ensure models are registered on Base
    Base.metadata.create_all(bind=engine)
