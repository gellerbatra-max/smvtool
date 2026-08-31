"""conftest.py -- shared pytest fixtures.

Each test gets a fresh, fully isolated database (one temp SQLite file per
test by default) via FastAPI's dependency_overrides mechanism -- the app
module itself is imported ONCE (module-level global engine untouched), and
app.main's own startup DB-init is skipped for tests (SMV_SKIP_STARTUP_INIT=1);
instead this fixture creates a private engine/session, creates all tables on
it, seeds the default allowance policy + a bootstrap administrator directly,
and overrides app.database.get_db to hand out sessions from that private
engine for the lifetime of the test.

Backend defaults to SQLite (originally the only option -- the sandbox this
project was first built in could not run a Postgres server, see SCHEMA.md).
Set TEST_DATABASE_URL to a postgresql+psycopg://... URL to run this same
suite against a real Postgres instance instead; each test gets its own
schema (created/dropped per test) rather than its own file, since Postgres
has no per-file-database equivalent.
"""
from __future__ import annotations

import os

os.environ["SMV_SKIP_STARTUP_INIT"] = "1"

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import models, auth, policy_service
from app.main import app

ADMIN_PASSWORD = "admin-test-pw-123"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture()
def client(tmp_path):
    if TEST_DATABASE_URL:
        schema = f"test_{uuid.uuid4().hex}"
        engine = create_engine(TEST_DATABASE_URL)

        # Registered before the first checkout below (not just before the
        # first *creation*): a plain "connect" listener only fires when the
        # pool opens a brand-new DBAPI connection, so a connection opened
        # here and later reused from the pool would keep the default
        # search_path and every test would collide in the public schema.
        # "checkout" fires on every lease from the pool, pooled or not.
        @event.listens_for(engine, "checkout", insert=True)
        def _set_search_path(dbapi_conn, _connection_record, _connection_proxy):
            with dbapi_conn.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema}"')
            dbapi_conn.commit()

        with engine.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.commit()
    else:
        db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    policy_service.ensure_seeded(db)
    admin = models.User(
        username="admin", full_name="Test Administrator",
        role=models.UserRole.administrator,
        password_hash=auth.hash_password(ADMIN_PASSWORD),
    )
    db.add(admin)
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()

    if TEST_DATABASE_URL:
        cleanup_engine = create_engine(TEST_DATABASE_URL)
        with cleanup_engine.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.commit()
        cleanup_engine.dispose()


def auth_headers(client: TestClient, username: str, password: str):
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client):
    return auth_headers(client, "admin", ADMIN_PASSWORD)


@pytest.fixture()
def engineer_headers(client, admin_headers):
    r = client.post("/users", json={
        "username": "engineer1", "full_name": "Engineer One",
        "role": "ie_engineer", "password": "engineer-pw-123",
    }, headers=admin_headers)
    assert r.status_code == 201, r.text
    return auth_headers(client, "engineer1", "engineer-pw-123")


@pytest.fixture()
def viewer_headers(client, admin_headers):
    r = client.post("/users", json={
        "username": "viewer1", "full_name": "Viewer One",
        "role": "viewer", "password": "viewer-pw-123",
    }, headers=admin_headers)
    assert r.status_code == 201, r.text
    return auth_headers(client, "viewer1", "viewer-pw-123")
