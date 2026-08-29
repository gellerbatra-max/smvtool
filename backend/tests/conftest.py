"""conftest.py -- shared pytest fixtures.

Each test gets a fresh, fully isolated SQLite database (one temp file per
test) via FastAPI's dependency_overrides mechanism -- the app module itself
is imported ONCE (module-level global engine untouched), and app.main's
own startup DB-init is skipped for tests (SMV_SKIP_STARTUP_INIT=1); instead
this fixture creates a private engine/session bound to the temp file,
creates all tables on it, seeds the default allowance policy + a bootstrap
administrator directly, and overrides app.database.get_db to hand out
sessions from that private engine for the lifetime of the test. See
SCHEMA.md / the top-level report for why SQLite is the test backend here
rather than Postgres (sandbox cannot run a Postgres server).
"""
from __future__ import annotations

import os

os.environ["SMV_SKIP_STARTUP_INIT"] = "1"

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import models, auth, policy_service
from app.main import app

ADMIN_PASSWORD = "admin-test-pw-123"


@pytest.fixture()
def client(tmp_path):
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
