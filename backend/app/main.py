"""main.py -- FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload   (from backend/)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, SessionLocal
from app import models, auth, policy_service
from app.routers import (
    auth_router, users_router, styles_router, library_router,
    calibration_router, allowance_router, analytics_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_startup_init()
    yield


app = FastAPI(
    title="SMV Application Layer",
    description="FastAPI service layer over the self-calibrating SMV engine "
                "(garment sewing time estimation).",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("SMV_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(styles_router.router)
app.include_router(library_router.router)
app.include_router(calibration_router.router)
app.include_router(allowance_router.router)
app.include_router(analytics_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def _run_startup_init():
    if os.environ.get("SMV_SKIP_STARTUP_INIT") == "1":
        # Test harness manages its own isolated engine/session and seeds it
        # directly (see tests/conftest.py) -- running this against the
        # process-global engine here would touch the wrong database file.
        return
    init_db()
    db = SessionLocal()
    try:
        # Seed the default allowance policy (v1) from the vendored engine's
        # shipped allowance_policy.json, if not already present.
        policy_service.ensure_seeded(db)
        # Seed a bootstrap administrator if no users exist yet, so a fresh
        # deployment isn't locked out. Credentials come from environment
        # variables; if unset, a fixed dev-only default is used and a
        # warning is printed -- change this before any real deployment.
        if db.query(models.User).count() == 0:
            admin_username = os.environ.get("SMV_BOOTSTRAP_ADMIN_USER", "admin")
            admin_password = os.environ.get("SMV_BOOTSTRAP_ADMIN_PASSWORD", "changeme123")
            admin = models.User(
                username=admin_username, full_name="Bootstrap Administrator",
                role=models.UserRole.administrator,
                password_hash=auth.hash_password(admin_password),
            )
            db.add(admin)
            if admin_password == "changeme123":
                print("WARNING: bootstrap administrator created with the default "
                      "dev password. Set SMV_BOOTSTRAP_ADMIN_PASSWORD before any "
                      "real deployment.")
        db.commit()
    finally:
        db.close()
