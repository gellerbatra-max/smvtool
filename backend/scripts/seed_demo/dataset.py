"""dataset.py -- the declarative demo dataset: users, styles, operation
edits, and the allowance-policy v2 derivation. Kept separate from
seed.py's orchestration so the *data* can be read without reading control
flow. See backend/README.md's "Demo data" section for the rendered table.

Idempotency note: several styles below deliberately share their initial
product name (e.g. three different CLASSIC styles are all named "Oxford
Button-Down, Classic" before size-specific ones and a renamed one
diverge) -- exactly like a real factory's style list would. That makes
name-based "does this already exist" matching genuinely ambiguous, so
identity is tracked purely through the `[demo-seed:<key>]` marker each
style's `notes` field carries (see `demo_tag` / `demo_key_from_notes`
below), never through the name.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal, Optional

DEMO_TAG_PREFIX = "[demo-seed:"


def demo_tag(key: str) -> str:
    return f"{DEMO_TAG_PREFIX}{key}]"


def with_tag(notes: Optional[str], key: str) -> str:
    """Appends this style's demo-seed tag to `notes` if it isn't already
    present. Idempotent: calling it twice with the same (notes, key) is a
    no-op the second time."""
    tag = demo_tag(key)
    base = (notes or "").rstrip()
    if tag in base:
        return base
    return f"{base}\n{tag}" if base else tag


def demo_key_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes:
        return None
    start = notes.find(DEMO_TAG_PREFIX)
    if start == -1:
        return None
    end = notes.find("]", start)
    if end == -1:
        return None
    return notes[start + len(DEMO_TAG_PREFIX):end]


# --------------------------------------------------------------------- users

@dataclass(frozen=True)
class DemoUser:
    username: str
    full_name: str
    role: str
    disabled: bool = False


DEMO_USERS: list[DemoUser] = [
    DemoUser("priya.nair", "Priya Nair", "ie_engineer"),
    DemoUser("tomasz.kowalski", "Tomasz Kowalski", "ie_engineer"),
    DemoUser("rita.okafor", "Rita Okafor", "administrator"),
    DemoUser("mei.lin", "Mei Lin", "viewer"),
    DemoUser("arjun.devarajan", "Arjun Devarajan", "viewer", disabled=True),
]

# NON-PRODUCTION: every demo user above shares this one password unless
# --demo-password / SMV_SEED_DEMO_PASSWORD overrides it. Never reuse this
# for a real account.
DEMO_USER_PASSWORD_DEFAULT = "demo-pass-2026"

# Sentinel `created_by` value meaning "whichever account the seed itself
# logged in as" (the bootstrap admin, or --username), rather than one of
# the DEMO_USERS above.
SEED_LOGIN_ACTOR = "__seed_login__"


# ---------------------------------------------------------- allowance policy

POLICY_NAME = "wt-allowance-policy"


def build_policy_v2_document(v1_document: dict) -> dict:
    """Derives a plausible v2 from the seeded v1 document: raises
    CONTINGENCY (applies to every time component, so the change is visible
    on every computed SMV, unlike e.g. BUNDLE_ALLOWANCE which the shirt
    library never triggers a "bundle" step for) from 1.0% to 1.5% --
    comfortably inside validation.max_total_percent (40) and
    warn_total_percent_above (32) in allowance_policy.json.

    `spec.demo_seed = True` is the idempotency marker this seed looks for
    on re-run (see seed.py's _seed_policy_v2). allowance.py only reads
    spec.id/version, categories, profiles, and validation, so the extra
    key is inert to the engine."""
    doc = copy.deepcopy(v1_document)
    # `profiles` is a JSON array of {code, ...} records, not a dict keyed
    # by code (confirmed against a live GET /allowance-policies/{id} --
    # the schema's own "profiles[]" naming was the tell this session's
    # first draft missed).
    profile = next(p for p in doc["profiles"] if p["code"] == "WOVEN_TOPS_DECOMPOSED")
    profile["values_percent"]["CONTINGENCY"] = 1.5
    doc["spec"]["version"] = "0.1.1"
    doc["spec"]["change_reason"] = (
        "Factory A pilot: contingency allowance raised after Q3 downtime review"
    )
    doc["spec"]["demo_seed"] = True
    return doc


def policy_v2_marker_present(document: dict) -> bool:
    return bool((document or {}).get("spec", {}).get("demo_seed"))


# --------------------------------------------------------------- style edits

@dataclass(frozen=True)
class OpEdit:
    kind: Literal["rename", "duplicate", "delete", "swap_machine"]
    op_prefix: str
    """Matches an operation by `name.startswith(op_prefix)`. Operation
    names embed the style's size (e.g. "... (size M)"), so prefixes stop
    just before that -- never the full name -- to work at any size."""
    new_name_suffix: Optional[str] = None   # rename / duplicate
    machine_class: Optional[str] = None      # swap_machine


@dataclass(frozen=True)
class StyleSpec:
    key: str
    name: str
    variant: str
    size: str
    bundle_size: int
    notes: str
    created_by: str            # a DEMO_USERS username, or SEED_LOGIN_ACTOR
    phase: Literal["A", "B"]   # A = seeded before policy v2 exists; B = after
    compute: bool = True
    profile: str = "WOVEN_TOPS_DECOMPOSED"
    edits: tuple[OpEdit, ...] = ()
    recompute_after_edits: bool = False
    style_update: Optional[dict] = None
    recompute_under_active: bool = False  # phase C: recompute once policy v2 is active

    @property
    def tagged_notes(self) -> str:
        return with_tag(self.notes, self.key)


DEMO_STYLES: list[StyleSpec] = [
    StyleSpec(
        key="WS-2401", name="Oxford Button-Down, Classic",
        variant="CLASSIC", size="M", bundle_size=20,
        notes="Core reference style for the Oxford program.",
        created_by="priya.nair", phase="A",
        recompute_under_active=True,
    ),
    StyleSpec(
        key="WS-2402", name="Oxford Button-Down, Classic",
        variant="CLASSIC", size="L", bundle_size=20,
        notes="Large-size grading check.",
        created_by="priya.nair", phase="A",
        style_update={"name": "Oxford Button-Down, Classic (rev B)", "bundle_size": 16},
    ),
    StyleSpec(
        key="WS-2403", name="Poplin Short Sleeve, Camp",
        variant="SHORT_SLEEVE", size="M", bundle_size=20,
        notes="Requested a front-pocket template guide for new operators.",
        created_by="priya.nair", phase="A",
        edits=(OpEdit(kind="rename", op_prefix="pocket: Set pocket to front",
                       new_name_suffix=" — template guide"),),
        recompute_under_active=True,
        style_update={"notes": "Front-pocket template guide added per training request."},
    ),
    StyleSpec(
        key="WS-2404", name="Linen Blouse, Collarless",
        variant="BLOUSE_COLLARLESS", size="S", bundle_size=24,
        notes="Second button station trial for the S run.",
        created_by="priya.nair", phase="A",
        edits=(OpEdit(kind="duplicate", op_prefix="all: Button sew",
                       new_name_suffix=" (2nd station)"),),
        # Deliberately NOT recomputed after the duplicate: the new
        # operation has no smv_results row yet, so the Bulletin shows one
        # "—" row -- a realistic partially-computed style.
    ),
    StyleSpec(
        key="WS-2405", name="Oxford Classic — safety-stitch side seam trial",
        variant="CLASSIC", size="M", bundle_size=20,
        notes="Machine-swap trial: side seam on the 5-thread safety-stitch overlock.",
        created_by="tomasz.kowalski", phase="A",
        edits=(OpEdit(kind="swap_machine", op_prefix="side_seam: Close side seam",
                       machine_class="OL-5T-SS"),),
        recompute_after_edits=True,  # mirrors analytics/demo.py's what-if scenario
    ),
    StyleSpec(
        key="WS-2406", name="Oxford Button-Down, Classic — no pocket bartack",
        variant="CLASSIC", size="XL", bundle_size=18,
        notes="Bartack dropped per buyer spec revision 3.",
        created_by="tomasz.kowalski", phase="A",
        edits=(OpEdit(kind="delete", op_prefix="pocket: Bartack, pocket mouth corners"),),
        style_update={"notes": "Bartack dropped per buyer spec revision 3 "
                                "(see the operation deletion in this style's change log)."},
    ),
    StyleSpec(
        key="WS-2407", name="Poplin Short Sleeve, Camp",
        variant="SHORT_SLEEVE", size="XXL", bundle_size=15,
        notes="Costed under the ILO-floor allowance profile for comparison.",
        created_by=SEED_LOGIN_ACTOR, phase="A",
        # NOT "APPAREL_CONVENTIONAL": that profile is deliberately blocked
        # by allowance.py's resolve_element_allowance() (it requires the
        # separate resolve_element_allowance_conventional() entry point
        # instead, per validation.error_if) -- discovered as a live 500
        # from POST /compute during this seed's own smoke test, not from
        # reading the code. ILO_CONSTANT_ONLY (PERSONAL + BASIC_FATIGUE
        # only, no parametric/MACHINE_DELAY categories) goes through the
        # normal path and still demonstrates profile variety.
        profile="ILO_CONSTANT_ONLY",
    ),
    StyleSpec(
        key="WS-2408", name="Poplin Short Sleeve, Camp",
        variant="SHORT_SLEEVE", size="S", bundle_size=24,
        notes="Small-size run for the spring order.",
        created_by="priya.nair", phase="B",
    ),
    StyleSpec(
        key="WS-2409", name="Oxford Button-Down, Classic",
        variant="CLASSIC", size="S", bundle_size=24,
        notes="Small-size run for the spring order.",
        created_by="priya.nair", phase="B",
    ),
    StyleSpec(
        key="WS-2410", name="Linen Blouse, Collarless — costing request",
        variant="BLOUSE_COLLARLESS", size="L", bundle_size=20,
        notes="Awaiting seam spec sign-off before computing.",
        created_by="tomasz.kowalski", phase="B",
        compute=False,
    ),
    StyleSpec(
        key="WS-2411", name="Linen Blouse, Collarless",
        variant="BLOUSE_COLLARLESS", size="M", bundle_size=20,
        notes="Core run, mid-size.",
        created_by="tomasz.kowalski", phase="B",
    ),
    StyleSpec(
        key="WS-2412", name="Chambray Short Sleeve, Camp",
        variant="SHORT_SLEEVE", size="L", bundle_size=20,
        notes="New fabrication trial: chambray in the camp-shirt block.",
        created_by="tomasz.kowalski", phase="B",
    ),
]
