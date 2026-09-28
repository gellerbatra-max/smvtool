"""seed.py -- orchestrates the demo dataset (dataset.py) against a running
backend via the REST API (api.py). See backend/README.md's "Demo data"
section for the rendered dataset table and how to run this.

Order: login as the seed operator -> (optional --reset-demo) -> demo
users (+ log in as each, disabling the one meant to be inactive) ->
Phase A styles (created & computed while the seeded v1 allowance policy
is still active) -> allowance-policy v2 (created by rita.okafor if she
logged in, else the seed operator) -> Phase B styles (created & computed
once v2 is active) -> Phase C: recompute the subset of styles flagged
`recompute_under_active`, producing a second smv_results generation
under v2 for styles that were first computed under v1.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from .api import Actor, ApiSession, SeedApiError
from .dataset import (
    DEMO_STYLES,
    DEMO_USER_PASSWORD_DEFAULT,
    DEMO_USERS,
    POLICY_NAME,
    SEED_LOGIN_ACTOR,
    OpEdit,
    StyleSpec,
    build_policy_v2_document,
    demo_key_from_notes,
    policy_v2_marker_present,
    with_tag,
)


@dataclass
class SeedReport:
    login_failed: bool = False
    users_created: list[str] = field(default_factory=list)
    users_skipped: list[str] = field(default_factory=list)
    users_disabled: list[str] = field(default_factory=list)
    policy_v2: str = "not_attempted"  # created | skipped | unavailable | failed
    styles_created: list[str] = field(default_factory=list)
    styles_skipped: list[str] = field(default_factory=list)
    styles_deleted: list[str] = field(default_factory=list)
    computes: list[tuple[str, str]] = field(default_factory=list)   # (key, "initial"|"after_edits"|"under_active_policy")
    edits: list[tuple[str, str]] = field(default_factory=list)      # (key, OpEdit.kind)
    warnings: list[str] = field(default_factory=list)
    failed: list[tuple[str, int, str]] = field(default_factory=list)  # (context, status, detail)
    manifest: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.login_failed and not self.failed


def _try(fn, context: str, report: SeedReport):
    """Runs fn(); on SeedApiError, records it in report.failed and returns
    None so one bad item doesn't abort the whole seed. Success always
    returns a non-None value (api.py's delete() returns True rather than
    None for a 204, specifically so this stays unambiguous)."""
    try:
        return fn()
    except SeedApiError as e:
        report.failed.append((context, e.status, e.detail))
        return None


# ------------------------------------------------------------------- users

def _seed_users(api: ApiSession, admin: Actor, demo_password: str,
                 report: SeedReport) -> dict[str, Actor]:
    existing = _try(lambda: api.get("/users", admin), "GET /users", report) or []
    existing_by_username = {u["username"]: u for u in existing}

    actors: dict[str, Actor] = {}
    for du in DEMO_USERS:
        row = existing_by_username.get(du.username)
        if row is None:
            row = _try(
                lambda du=du: api.post("/users", admin, json={
                    "username": du.username, "full_name": du.full_name,
                    "role": du.role, "password": demo_password,
                }),
                f"create user {du.username}", report,
            )
            if row is None:
                continue
            report.users_created.append(du.username)
        else:
            report.users_skipped.append(du.username)

        if du.disabled:
            if row.get("is_active", True):
                updated = _try(
                    lambda row=row: api.patch(f"/users/{row['id']}", admin, json={"is_active": False}),
                    f"disable user {du.username}", report,
                )
                if updated is not None:
                    report.users_disabled.append(du.username)
            continue  # never log in as a disabled account

        actor = _try(lambda du=du: api.login(du.username, demo_password),
                     f"login as {du.username}", report)
        if actor is not None:
            actors[du.username] = actor
    return actors


# --------------------------------------------------------------- allowance policy

def _seed_policy_v2(api: ApiSession, actor: Actor, report: SeedReport) -> None:
    policies = _try(lambda: api.get("/allowance-policies", actor), "GET /allowance-policies", report)
    if policies is None:
        report.policy_v2 = "failed"
        return

    matching = [p for p in policies if p["policy_name"] == POLICY_NAME]
    if not matching:
        report.warnings.append(f"no {POLICY_NAME!r} policy rows found; cannot derive v2")
        report.policy_v2 = "unavailable"
        return

    for p in matching:
        detail = _try(lambda p=p: api.get(f"/allowance-policies/{p['id']}", actor),
                       f"GET /allowance-policies/{p['id']}", report)
        if detail is not None and policy_v2_marker_present(detail.get("document")):
            report.policy_v2 = "skipped"
            return

    max_version = max(p["version"] for p in matching)
    if max_version > 1:
        report.warnings.append(
            f"{POLICY_NAME!r} already has version {max_version} with no demo_seed marker on "
            "any version -- leaving it alone rather than deactivating a real policy version"
        )
        report.policy_v2 = "unavailable"
        return

    v1 = next(p for p in matching if p["version"] == 1)
    v1_detail = _try(lambda: api.get(f"/allowance-policies/{v1['id']}", actor),
                      f"GET /allowance-policies/{v1['id']}", report)
    if v1_detail is None:
        report.policy_v2 = "failed"
        return

    v2_document = build_policy_v2_document(v1_detail["document"])
    created = _try(
        lambda: api.post("/allowance-policies", actor, json={
            "policy_name": POLICY_NAME, "document": v2_document,
        }),
        "create allowance policy v2", report,
    )
    report.policy_v2 = "created" if created is not None else "failed"


# ------------------------------------------------------------------ styles

def _existing_demo_styles(api: ApiSession, admin: Actor, report: SeedReport) -> dict[str, dict]:
    """key -> the existing style's JSON, for every style currently tagged
    with a recognized [demo-seed:<key>] marker in its notes. Identity is
    tracked purely by tag (see dataset.py's module docstring for why)."""
    styles = _try(lambda: api.get("/styles", admin), "GET /styles", report) or []
    result: dict[str, dict] = {}
    for s in styles:
        key = demo_key_from_notes(s.get("notes"))
        if key is not None:
            result[key] = s
    return result


def _reset_demo_styles(api: ApiSession, admin: Actor, report: SeedReport) -> None:
    """Deletes every currently-tagged demo style (regardless of whether its
    key still appears in DEMO_STYLES), then the normal seed proceeds as if
    starting fresh. Never touches a style without the tag."""
    styles = _try(lambda: api.get("/styles", admin), "GET /styles (reset)", report) or []
    for s in styles:
        key = demo_key_from_notes(s.get("notes"))
        if key is None:
            continue
        deleted = _try(lambda s=s: api.delete(f"/styles/{s['id']}", admin),
                        f"delete style {s['name']!r} ({key})", report)
        if deleted is not None:
            report.styles_deleted.append(key)


def _find_op(operations: list[dict], prefix: str) -> dict:
    for op in operations:
        if op["name"].startswith(prefix):
            return op
    raise SeedApiError(f"find operation matching {prefix!r}", 0, "no matching operation on this style")


def _apply_edit(api: ApiSession, actor: Actor, style_id: str, edit: OpEdit,
                 operations: list[dict]) -> bool:
    op = _find_op(operations, edit.op_prefix)

    if edit.kind == "rename":
        payload = {
            "name": op["name"] + (edit.new_name_suffix or ""),
            "sequence": op["sequence"], "bundle_size": op["bundle_size"], "steps": op["steps"],
        }
        api.put(f"/styles/{style_id}/operations/{op['id']}", actor, json=payload)

    elif edit.kind == "duplicate":
        max_seq = max((o["sequence"] for o in operations), default=-1)
        payload = {
            "name": op["name"] + (edit.new_name_suffix or " (copy)"),
            "sequence": max_seq + 1, "bundle_size": op["bundle_size"],
            "steps": copy.deepcopy(op["steps"]),
        }
        api.post(f"/styles/{style_id}/operations", actor, json=payload)

    elif edit.kind == "delete":
        api.delete(f"/styles/{style_id}/operations/{op['id']}", actor)

    elif edit.kind == "swap_machine":
        steps = copy.deepcopy(op["steps"])
        seam_step = next((s for s in steps if s.get("kind") in ("seam", "cycle")), None)
        if seam_step is None:
            raise SeedApiError(f"swap_machine on {edit.op_prefix!r}", 0,
                                "operation has no seam/cycle step to retarget")
        seam_step["machine_class"] = edit.machine_class
        payload = {
            "name": op["name"], "sequence": op["sequence"],
            "bundle_size": op["bundle_size"], "steps": steps,
        }
        api.put(f"/styles/{style_id}/operations/{op['id']}", actor, json=payload)

    else:  # pragma: no cover -- exhaustive over OpEdit.kind's Literal
        raise ValueError(f"unknown OpEdit.kind {edit.kind!r}")

    return True


def _seed_style(api: ApiSession, actors: dict[str, Actor], spec: StyleSpec,
                 report: SeedReport) -> Optional[str]:
    actor = actors.get(spec.created_by)
    if actor is None:
        report.failed.append((f"create style {spec.key}", 0,
                               f"actor {spec.created_by!r} is not authenticated (its own login "
                               "may have failed -- see earlier failures)"))
        return None

    style = _try(
        lambda: api.post("/styles", actor, json={
            "name": spec.name, "garment_type": "woven_shirt", "variant": spec.variant,
            "size": spec.size, "bundle_size": spec.bundle_size, "notes": spec.tagged_notes,
            "seed_from_library": True,
        }),
        f"create style {spec.key}", report,
    )
    if style is None:
        return None
    style_id = style["id"]
    report.styles_created.append(spec.key)
    report.manifest.setdefault("styles", {})[spec.key] = style_id

    if spec.compute:
        computed = _try(
            lambda: api.post(f"/styles/{style_id}/compute", actor,
                              json={"allowance_profile": spec.profile}),
            f"compute {spec.key}", report,
        )
        if computed is not None:
            report.computes.append((spec.key, "initial"))

    if spec.edits:
        detail = _try(lambda: api.get(f"/styles/{style_id}", actor), f"GET style {spec.key}", report)
        if detail is not None:
            for edit in spec.edits:
                ok = _try(
                    lambda edit=edit: _apply_edit(api, actor, style_id, edit, detail["operations"]),
                    f"{spec.key}: {edit.kind} {edit.op_prefix!r}", report,
                )
                if ok:
                    report.edits.append((spec.key, edit.kind))

    if spec.recompute_after_edits:
        computed = _try(
            lambda: api.post(f"/styles/{style_id}/compute", actor,
                              json={"allowance_profile": spec.profile}),
            f"recompute {spec.key} after edits", report,
        )
        if computed is not None:
            report.computes.append((spec.key, "after_edits"))

    if spec.style_update:
        payload = dict(spec.style_update)
        if "notes" in payload:
            payload["notes"] = with_tag(payload["notes"], spec.key)
        _try(lambda: api.put(f"/styles/{style_id}", actor, json=payload),
             f"update style {spec.key}", report)

    return style_id


def _recompute_under_active(api: ApiSession, actors: dict[str, Actor],
                             styles_by_key: dict[str, str], report: SeedReport) -> None:
    for spec in DEMO_STYLES:
        if not spec.recompute_under_active:
            continue
        style_id = styles_by_key.get(spec.key)
        if style_id is None:
            continue  # already existed before this run, or failed to create -- leave it alone
        actor = actors.get(spec.created_by)
        if actor is None:
            continue  # the earlier failure was already reported when the style itself was created
        computed = _try(
            lambda style_id=style_id, actor=actor, spec=spec: api.post(
                f"/styles/{style_id}/compute", actor, json={"allowance_profile": spec.profile}
            ),
            f"recompute {spec.key} under active policy", report,
        )
        if computed is not None:
            report.computes.append((spec.key, "under_active_policy"))


# ------------------------------------------------------------------- entry point

def seed(client, *, admin_username: str = "admin", admin_password: str = "changeme123",
         demo_password: str = DEMO_USER_PASSWORD_DEFAULT, reset_demo: bool = False) -> SeedReport:
    report = SeedReport()
    api = ApiSession(client)

    admin = _try(lambda: api.login(admin_username, admin_password), "login as seed operator", report)
    if admin is None:
        report.login_failed = True
        return report

    if reset_demo:
        _reset_demo_styles(api, admin, report)

    actors = _seed_users(api, admin, demo_password, report)
    actors[SEED_LOGIN_ACTOR] = admin

    existing = _existing_demo_styles(api, admin, report)
    styles_by_key: dict[str, str] = {}

    for spec in DEMO_STYLES:
        if spec.phase != "A":
            continue
        if spec.key in existing:
            report.styles_skipped.append(spec.key)
            report.manifest.setdefault("styles", {})[spec.key] = existing[spec.key]["id"]
            continue
        style_id = _seed_style(api, actors, spec, report)
        if style_id is not None:
            styles_by_key[spec.key] = style_id

    # Created by rita.okafor when she's available, so the policy's
    # created_by_id isn't always the seed operator; falls back to admin
    # (with a warning) if her account/login failed.
    if "rita.okafor" in actors:
        policy_actor = actors["rita.okafor"]
    else:
        policy_actor = admin
        report.warnings.append(
            "rita.okafor is not authenticated; allowance policy v2 (if created) will be "
            "attributed to the seed operator instead"
        )
    _seed_policy_v2(api, policy_actor, report)

    for spec in DEMO_STYLES:
        if spec.phase != "B":
            continue
        if spec.key in existing:
            report.styles_skipped.append(spec.key)
            report.manifest.setdefault("styles", {})[spec.key] = existing[spec.key]["id"]
            continue
        style_id = _seed_style(api, actors, spec, report)
        if style_id is not None:
            styles_by_key[spec.key] = style_id

    _recompute_under_active(api, actors, styles_by_key, report)

    report.manifest["users"] = {
        du.username: actors[du.username].user_id for du in DEMO_USERS if du.username in actors
    }
    return report
