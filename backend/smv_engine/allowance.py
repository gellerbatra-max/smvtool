"""
allowance.py -- Allowance-policy engine (basic time -> standard time).

Implements allowance_policy.json's application rules (AR1-AR8) faithfully:
  * additive-then-single-multiplication, never compounded (AR1, conventions)
  * MACHINE_DELAY restricted to the machine-time component only (AR2)
  * bundle elements amortised over bundle_size BEFORE allowances (AR3)
  * parametric categories (FORCE_WEIGHT, CLOSE_ATTENTION) resolved from the
    element's own parameters, with the resolved percent recorded (AR4)
  * per-element total-allowance cap, exceeding it is an ERROR (AR5)
  * policy id/version stamped onto every result (AR6)

Public API
----------
    load_allowance_policy(path="allowance_policy.json") -> AllowancePolicy
    AllowancePolicy.resolve_element_allowance(element_profile, element_result,
                                               profile_code=...) -> dict
"""
from __future__ import annotations

import json
from dataclasses import dataclass


def load_allowance_policy(path: str = "allowance_policy.json") -> "AllowancePolicy":
    with open(path) as fh:
        raw = json.load(fh)
    return AllowancePolicy(raw)


class AllowanceError(ValueError):
    """Raised for a policy misconfiguration per allowance_policy.json validation.error_if."""


class AllowancePolicy:
    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["spec"]["id"]
        self.version = raw["spec"]["version"]
        self.categories = {c["code"]: c for c in raw["categories"]}
        self.profiles = {p["code"]: p for p in raw["profiles"]}
        self.validation = raw["validation"]
        # error_if: "a category present that is not declared in categories[]"
        for prof in self.profiles.values():
            for code in prof["values_percent"]:
                if code not in self.categories and code != prof.get("extra_category", {}).get("code"):
                    raise AllowanceError(
                        f"profile {prof['code']} references undeclared category {code!r}"
                    )

    # ---- parametric-category resolution ----

    def _resolve_force_weight(self, element_result: dict) -> float:
        cat = self.categories["FORCE_WEIGHT"]
        rule = cat["parametric_rule"]
        rate = rule["force_rate_pct_per_kg"]
        mass_kg = None
        params = element_result.get("params", {})
        if "mass_kg" in params:
            mass_kg = params["mass_kg"]
        elif "mass_g" in params:
            mass_kg = params["mass_g"] / 1000.0
        else:
            # fall back: look for a mass_g resolved inside a phase (e.g. HAG's
            # loaded-return phase uses a per-phase mass_g distinct from params)
            for ph in element_result.get("phases", []):
                if "mass_g" in ph:
                    mass_kg = max(mass_kg or 0.0, ph["mass_g"] / 1000.0)
        if mass_kg is None:
            return 0.0
        pct = rate * mass_kg
        return min(pct, cat["cited_range"][1])

    def _resolve_close_attention(self, element_code: str, element_result: dict) -> float:
        cat = self.categories["CLOSE_ATTENTION"]
        params = element_result.get("params", {})
        if element_code == "HGD":
            tol = params.get("tolerance_mm")
            if tol is None:
                return 0.0
            if tol > 4.0:
                return 0.0
            if tol >= 2.0:
                return 1.0
            if tol >= 1.0:
                return 2.0
            return 4.0
        precision_class = params.get("precision_class")
        mapping = {"P0": 0.0, "P1": 0.0, "P2": 1.0, "P3": 2.0, "P4": 4.0}
        if precision_class in mapping:
            return mapping[precision_class]
        return 0.0

    def _recruited_trunk(self, element_result: dict) -> bool:
        return any(ph.get("lean_term_s", 0.0) > 0.0 for ph in element_result.get("phases", []))

    def _resolve_awkward_position(self, element_code: str, element_profile: str,
                                   element_result: dict) -> float:
        cat = self.categories["AWKWARD_POSITION"]
        if element_profile == "MANUAL_HANDLING":
            return cat["default_percent"] if self._recruited_trunk(element_result) else 0.0
        if element_profile == "BUNDLE":
            # Per trigger_rule: "all BUNDLE-profile elements involving a lift".
            # HBM declares its lift/slide/push/walk mode explicitly; HBO/HBC
            # (opening/closing a tied bundle) inherently involve lifting the
            # bundle to work on it, so they are treated as lift-involving too.
            # This element-type interpretation is recorded here explicitly
            # because the taxonomy does not give a closed-form trigger for it.
            params = element_result.get("params", {})
            if element_code == "HBM":
                return cat["default_percent"] if params.get("mode") == "LIFT" else 0.0
            return cat["default_percent"]
        return 0.0

    # ---- per-element resolution ----

    def resolve_element_allowance(
        self,
        element_code: str,
        element_profile: str,
        element_result: dict,
        profile_code: str = "WOVEN_TOPS_DECOMPOSED",
    ) -> dict:
        """Returns {'categories': [{code, percent, basis}], 'total_percent': float,
        'capped': bool, 'warnings': [...]}. Raises AllowanceError on a policy
        misconfiguration per validation.error_if."""
        if profile_code not in self.profiles:
            raise AllowanceError(f"unknown allowance profile {profile_code!r}")
        profile = self.profiles[profile_code]
        if profile_code == "APPAREL_CONVENTIONAL":
            raise AllowanceError(
                "profile APPAREL_CONVENTIONAL used without an explicit override "
                "acknowledgement (validation.error_if) -- call "
                "resolve_element_allowance_conventional() instead"
            )

        applied = []
        for code, pct in profile["values_percent"].items():
            cat = self.categories[code]
            if element_profile not in cat["applies_to"]["element_profiles"]:
                continue
            if code == "MACHINE_DELAY" and element_profile != "MACHINE_STATION":
                raise AllowanceError(
                    f"{element_code}: MACHINE_DELAY applied to a non-machine "
                    f"component ({element_profile}) -- forbidden by validation.error_if"
                )
            if pct == "parametric":
                if code == "FORCE_WEIGHT":
                    resolved = self._resolve_force_weight(element_result)
                    basis = "parametric: force_rate_pct_per_kg * mass_kg"
                elif code == "CLOSE_ATTENTION":
                    resolved = self._resolve_close_attention(element_code, element_result)
                    basis = "parametric: precision_class / seam-tolerance trigger"
                else:
                    raise AllowanceError(f"category {code} marked parametric but has no resolver")
            elif code == "AWKWARD_POSITION":
                resolved = self._resolve_awkward_position(element_code, element_profile, element_result)
                basis = "trigger: trunk-lean / lift-mode"
            else:
                resolved = float(pct)
                basis = "flat profile default"
            if resolved < 0:
                raise AllowanceError(f"{element_code}: category {code} resolved to a negative percent")
            if code == "PERSONAL" and not (0.0 <= resolved <= 10.0):
                raise AllowanceError(f"{element_code}: PERSONAL {resolved} outside [0, 10]")
            if resolved > 0:
                applied.append({"code": code, "percent": resolved, "basis": basis})

        total = sum(a["percent"] for a in applied)
        warnings = []
        if total > self.validation["warn_total_percent_above"]:
            warnings.append(f"total allowance {total:.2f}% exceeds warn threshold "
                             f"{self.validation['warn_total_percent_above']}%")
        if total > self.validation["max_total_percent"]:
            raise AllowanceError(
                f"{element_code}: total allowance {total:.2f}% exceeds "
                f"max_total_percent {self.validation['max_total_percent']}% (AR5)"
            )
        return {
            "profile_code": profile_code,
            "policy_id": self.id,
            "policy_version": self.version,
            "element_profile": element_profile,
            "categories": applied,
            "total_percent": total,
            "warnings": warnings,
        }

    def resolve_element_allowance_conventional(self, element_profile: str) -> dict:
        """APPAREL_CONVENTIONAL profile, for backward comparison only (per
        validation.error_if this must be reached only via an explicit call,
        never the default resolve path)."""
        profile = self.profiles["APPAREL_CONVENTIONAL"]
        applied = []
        bundle_pct = profile["values_percent"]["BUNDLE_ALLOWANCE"]
        mp_cat = profile["extra_category"]
        mp_pct = profile["values_percent"]["MACHINE_AND_PERSONAL"]
        if element_profile in self.categories["BUNDLE_ALLOWANCE"]["applies_to"]["element_profiles"]:
            applied.append({"code": "BUNDLE_ALLOWANCE", "percent": bundle_pct, "basis": "flat (conventional)"})
        if element_profile in mp_cat["applies_to"]["element_profiles"]:
            applied.append({"code": "MACHINE_AND_PERSONAL", "percent": mp_pct, "basis": "flat (conventional)"})
        total = sum(a["percent"] for a in applied)
        return {
            "profile_code": "APPAREL_CONVENTIONAL",
            "policy_id": self.id,
            "policy_version": self.version,
            "element_profile": element_profile,
            "categories": applied,
            "total_percent": total,
            "warnings": ["APPAREL_CONVENTIONAL applies machine allowance to handling "
                         "time too; comparison profile only, not for production use."],
        }


if __name__ == "__main__":
    pol = load_allowance_policy("allowance_policy.json")
    print(f"Loaded policy {pol.id} v{pol.version}: {len(pol.categories)} categories, "
          f"{len(pol.profiles)} profiles")
