"""seed_demo -- the demo-database seed package.

See backend/README.md's "Demo data" section for what this populates and
why, and backend/scripts/seed_demo_database.py for the CLI entry point.
"""
from .dataset import DEMO_STYLES, DEMO_USER_PASSWORD_DEFAULT, DEMO_USERS
from .seed import SeedReport, seed

__all__ = ["seed", "SeedReport", "DEMO_USERS", "DEMO_STYLES", "DEMO_USER_PASSWORD_DEFAULT"]
