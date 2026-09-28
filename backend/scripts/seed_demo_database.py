"""seed_demo_database.py -- thin CLI shim for the seed_demo package.

See backend/README.md's "Demo data" section for the full dataset this
populates (5 users across all three roles, a second allowance-policy
version, 12 realistically-named styles with a mix of computed/uncomputed/
edited/multi-generation results) and backend/scripts/seed_demo_styles.py
for the earlier, simpler 15-style grid seeder this doesn't replace (that
one still works and its own tests still pass; this is a richer, separate
dataset covering all six tables rather than just styles).

    python backend/scripts/seed_demo_database.py --base-url http://localhost:8000

Run `python backend/scripts/seed_demo_database.py --help` for every option.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_demo.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
