"""
handling_time.py -- Fitts-based handling-time engine for the woven-tops SMV project.

Pillar 2 (HANDLING TIME) of the self-calibrating synthetic engine.

This module is an INTERPRETER for the taxonomy defined in element_taxonomy.json.
It does not hardcode a single time value: every element's time is computed from
its declared phase_program by evaluating small parametric expressions (the
"expression_grammar" section of the taxonomy) against the element's own
parameters and the taxonomy's global_parameters. Nothing is looked up by code
combination -- see element_taxonomy.json.spec.ip_provenance for why.

Public API
----------
    load_taxonomy(path="element_taxonomy.json") -> Taxonomy
    Taxonomy.compute_element(code, **params) -> ElementResult (auditable dict)
    Taxonomy.list_elements() -> list[str]

Every ElementResult carries a full audit trail: every phase's inputs,
intermediate terms (ID, PHI, LAM_M, limb class, whether PHI was clamped) and
the resulting phase time in seconds, plus the element total and which hand was
limiting for bimanual elements. This satisfies assembly_rules.audit_trail_minimum
in element_taxonomy.json (element-level items).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_taxonomy(path: str = "element_taxonomy.json") -> "Taxonomy":
    with open(path) as fh:
        raw = json.load(fh)
    return Taxonomy(raw)


class Taxonomy:
    """Wraps a parsed element_taxonomy.json and exposes the engine's public API."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.version = raw["spec"]["version"]
        self.globals: dict[str, float] = {
            gp["symbol"]: gp["default"] for gp in raw["global_parameters"]
        }
        self.global_meta: dict[str, dict] = {
            gp["symbol"]: gp for gp in raw["global_parameters"]
        }
        self.engine_constants: dict[str, Any] = {
            ec["symbol"]: ec["default"] for ec in raw["engine_constants"]
        }
        self.class_tables: dict[str, dict] = raw["class_tables"]
        self.phase_scale: dict[str, float] = raw["fabric_difficulty_model"]["phase_scale_defaults"]
        self.elements: dict[str, dict] = {e["code"]: e for e in raw["elements"]}

    def list_elements(self) -> list[str]:
        return sorted(self.elements.keys())

    # ---- class-table lookups (mirrors expression_grammar.allowed_functions) ----

    def _class_row(self, table: str, code: str) -> dict:
        for row in self.class_tables[table]["values"]:
            if row["code"] == code:
                return row
        raise KeyError(f"{code!r} not found in class_tables.{table}")

    def W(self, precision_class: str) -> float:
        return self._class_row("precision_class", precision_class)["W_mm"]

    def _limb_row(self, d_mm: float) -> dict:
        for row in self.class_tables["limb_class"]["values"]:
            if row["d_mm_max"] is None or d_mm <= row["d_mm_max"]:
                return row
        raise RuntimeError("no limb class matched (should be unreachable: ARM has no max)")

    def LIMB(self, d_mm: float) -> str:
        return self._limb_row(d_mm)["code"]

    def A_L(self, d_mm: float) -> float:
        return self.globals[self._limb_row(d_mm)["a_symbol"]]

    def B_L(self, d_mm: float) -> float:
        return self.globals[self._limb_row(d_mm)["b_symbol"]]

    def control_base_s(self, control_class: str) -> float:
        return self._class_row("control_class", control_class)["base_s"]

    def tool_base_s(self, tool_class: str) -> float:
        return self._class_row("tool_class", tool_class)["base_s"]

    def tool_action_s(self, tool_class: str) -> float:
        return self._class_row("tool_class", tool_class)["action_s"]

    def tie_open_s(self, tie_type: str) -> float:
        return self._class_row("tie_type", tie_type)["open_s"]

    def tie_close_s(self, tie_type: str) -> float:
        return self._class_row("tie_type", tie_type)["close_s"]

    def inspect_k(self, inspect_class: str) -> float:
        return self._class_row("inspect_class", inspect_class)["k_class"]

    def fabric_descriptors(self, fabric_class: str) -> dict:
        return self._class_row("fabric_class", fabric_class)

    # ---- fabric difficulty model (PHI) ----

    def _z(self, kind: str, fabric_class: str) -> float:
        f = self.fabric_descriptors(fabric_class)
        ref = self.fabric_descriptors("REF_POPLIN")
        if kind == "limp":
            return max(0.0, math.log2(ref["B_uNm"] / f["B_uNm"]))
        if kind == "slip":
            return max(0.0, math.log2(ref["MIU"] / f["MIU"]))
        if kind == "bulk":
            return max(0.0, math.log2(f["t_mm"] / ref["t_mm"]))
        raise ValueError(kind)

    def PHI(self, phase: str, fabric_class: str) -> dict:
        """Returns {'value': float, 'clamped': bool, 'raw': float, 'z_limp':.., ...}."""
        z_limp = self._z("limp", fabric_class)
        z_slip = self._z("slip", fabric_class)
        z_bulk = self._z("bulk", fabric_class)
        scale = self.phase_scale[phase]
        raw = 1.0 + scale * (
            self.globals["phi_limp"] * z_limp
            + self.globals["phi_slip"] * z_slip
            + self.globals["phi_bulk"] * z_bulk
        )
        lo, hi = self.globals["Phi_min"], self.globals["Phi_max"]
        value = min(max(raw, lo), hi)
        return {
            "value": value,
            "raw": raw,
            "clamped": value != raw,
            "z_limp": z_limp,
            "z_slip": z_slip,
            "z_bulk": z_bulk,
            "phase_scale": scale,
        }

    def LAM_M(self, mass_g: float) -> float:
        return 1.0 + self.globals["kappa_m"] * math.log2(1.0 + mass_g / self.globals["m_ref_g"])

    def PLY(self, n: float) -> float:
        return self.globals["g_ply"] * max(n - 1.0, 0.0) ** self.globals["gamma_ply"]

    def ID_POINT(self, d_mm: float, w_mm: float) -> float:
        return math.log2(d_mm / w_mm + 1.0)

    def ID_STEER(self, l_mm: float, w_mm: float, r_mm: float) -> float:
        k_r = self.globals["k_R"]
        r_ref = self.globals["R_ref_mm"]
        curvature_term = 1.0 if math.isinf(r_mm) else 1.0 + k_r * (r_ref / r_mm) ** (1.0 / 3.0)
        return (l_mm / w_mm) * curvature_term

    # ---- expression evaluation ----

    def _eval_namespace(self, element: dict, params: dict) -> dict:
        ns: dict[str, Any] = {}
        ns.update(self.globals)
        ns.update(self.engine_constants)
        ns["true"] = True
        ns["false"] = False
        # element-local lookup tables (e.g. HGD.guide_relief, HBM.mode_base_s)
        for key, spec in element.items():
            if isinstance(spec, dict) and "values" in spec and key not in self.class_tables:
                table = spec["values"]
                ns[key] = (lambda code, _t=table: _t[code])
        # substitute None (JSON null) numeric params with +inf (per taxonomy
        # convention: null_means straight path / infinite radius)
        for k, v in params.items():
            ns[k] = float("inf") if v is None else v
        ns["null"] = float("inf")
        ns["PHASE_SCALE"] = self.phase_scale
        ns["W"] = self.W
        ns["LIMB"] = self.LIMB
        ns["A_L"] = self.A_L
        ns["B_L"] = self.B_L
        ns["ID_POINT"] = self.ID_POINT
        ns["ID_STEER"] = self.ID_STEER
        ns["LAM_M"] = self.LAM_M
        ns["PLY"] = self.PLY
        ns["MIN"] = lambda a, b: min(a, b)
        ns["MAX"] = lambda a, b: max(a, b)
        ns["CLAMP"] = lambda x, lo, hi: min(max(x, lo), hi)
        ns["LOG2"] = math.log2
        ns["IN"] = lambda x, lst: 1.0 if x in lst else 0.0
        ns["control_base_s"] = self.control_base_s
        ns["tool_base_s"] = self.tool_base_s
        ns["tool_action_s"] = self.tool_action_s
        ns["tie_open_s"] = self.tie_open_s
        ns["tie_close_s"] = self.tie_close_s
        ns["inspect_k"] = self.inspect_k
        return ns

    def _eval_expr(self, expr, ns: dict):
        """Evaluate a taxonomy expression. Numbers/bools pass through unchanged;
        strings are evaluated as restricted Python expressions against ns."""
        if expr is None:
            return float("inf")
        if isinstance(expr, (int, float, bool)):
            return expr
        if isinstance(expr, str):
            try:
                return eval(expr, {"__builtins__": {}}, ns)
            except Exception as exc:
                raise ValueError(f"failed to evaluate expression {expr!r}: {exc}") from exc
        raise TypeError(f"unsupported expression type: {type(expr)}")

    # ---- phase-primitive time equations ----

    def _time_point(self, phase: dict, ns: dict) -> dict:
        D = self._eval_expr(phase["D"], ns)
        Wd = self._eval_expr(phase["W"], ns)
        mass_g = self._eval_expr(phase["mass_g"], ns)
        n_sub = self._eval_expr(phase.get("n_sub", 1), ns)
        fabric_class = ns.get("fabric_class", "REF_POPLIN")
        limb = self.LIMB(D)
        a = self.A_L(D)
        b = self.B_L(D)
        idp = self.ID_POINT(D, Wd)
        lam = self.LAM_M(mass_g)
        phi = self.PHI("point", fabric_class)
        lean = self.globals["c_lean"] if D > self.globals["D_trunk_mm"] else 0.0
        t_single = (a + b * idp) * lam * phi["value"] + lean
        t = t_single * n_sub
        return {
            "type": "point", "role": phase.get("role"),
            "D_mm": D, "W_mm": Wd, "mass_g": mass_g, "n_sub": n_sub,
            "limb_class": limb, "a": a, "b": b, "ID": idp, "LAM_M": lam,
            "PHI": phi, "lean_term_s": lean, "t_per_sub_s": t_single, "t_s": t,
        }

    def _time_steer(self, phase: dict, ns: dict) -> dict:
        L = self._eval_expr(phase["L"], ns)
        Wd = self._eval_expr(phase["W"], ns)
        R = self._eval_expr(phase.get("R", None), ns)
        if R is None:
            R = float("inf")
        fabric_class = ns.get("fabric_class", "REF_POPLIN")
        a = self.globals["a_steer"]
        b = self.globals["b_steer"]
        ids = self.ID_STEER(L, Wd, R)
        phi = self.PHI("steer", fabric_class)
        t = (a + b * ids) * phi["value"]
        return {
            "type": "steer", "role": phase.get("role"),
            "L_mm": L, "W_mm": Wd, "R_mm": R, "a_steer": a, "b_steer": b,
            "ID_STEER": ids, "PHI": phi, "t_s": t,
        }

    def _time_grasp(self, phase: dict, ns: dict) -> dict:
        plies = self._eval_expr(phase["plies"], ns)
        extra_s = self._eval_expr(phase.get("extra_s", 0.0), ns)
        fabric_class = ns.get("fabric_class", "REF_POPLIN")
        g0 = self.globals["g_0"]
        ply_term = self.PLY(plies)
        phi = self.PHI("grasp", fabric_class)
        t = (g0 + ply_term + extra_s) * phi["value"]
        return {
            "type": "grasp", "role": phase.get("role"),
            "plies": plies, "extra_s": extra_s, "g_0": g0, "ply_term_s": ply_term,
            "PHI": phi, "t_s": t,
        }

    def _time_fixed(self, phase: dict, ns: dict) -> dict:
        base_s = self._eval_expr(phase["base_s"], ns)
        n_actions = self._eval_expr(phase.get("n_actions", 1), ns)
        fabric_class = ns.get("fabric_class", "REF_POPLIN")
        phi = self.PHI("fixed", fabric_class)
        t = base_s * n_actions * phi["value"]
        return {
            "type": "fixed", "role": phase.get("role"),
            "base_s": base_s, "n_actions": n_actions, "PHI": phi, "t_s": t,
        }

    def _time_cognitive(self, phase: dict, ns: dict) -> dict:
        k_class = self._eval_expr(phase["k_class"], ns)
        n_checks = self._eval_expr(phase.get("n_checks", 1), ns)
        t_look = self.globals["t_look"]
        t = t_look * k_class * n_checks
        return {
            "type": "cognitive", "role": phase.get("role"),
            "t_look": t_look, "k_class": k_class, "n_checks": n_checks, "t_s": t,
        }

    _PHASE_FN = {
        "point": _time_point, "steer": _time_steer, "grasp": _time_grasp,
        "fixed": _time_fixed, "cognitive": _time_cognitive,
    }

    # ---- element assembly ----

    def compute_element(self, code: str, **params) -> dict:
        """Compute one handling element's time with a full audit trail.

        Returns a dict: {code, name, params, phases: [...], combination,
        combined_s (pre-Gamma_skill), t_basic_s (post-Gamma_skill), bimanual}.
        """
        element = self.elements[code]
        resolved = self._resolve_params(element, params)
        ns = self._eval_namespace(element, resolved)

        phase_results = []
        for phase in element["phase_program"]:
            fn = self._PHASE_FN[phase["type"]]
            phase_results.append(fn(self, phase, ns))

        combo = element.get("combination", "sum")
        combined_s, combo_note, limiting_hand = self._combine(combo, element, phase_results, ns)

        gamma = self.globals["Gamma_skill"]
        t_basic = gamma * combined_s

        return {
            "code": code,
            "name": element["name"],
            "params": resolved,
            "phases": phase_results,
            "combination": combo,
            "combination_note": combo_note,
            "limiting_hand": limiting_hand,
            "combined_s": combined_s,
            "Gamma_skill": gamma,
            "t_basic_s": t_basic,
            "allowance_profile": element.get("allowance_profile"),
            "overlaps_machine": element.get("overlaps_machine", False),
        }

    def _resolve_params(self, element: dict, supplied: dict) -> dict:
        resolved = {}
        for p in element["parameters"]:
            name = p["name"]
            if name in supplied:
                value = supplied[name]
            elif "default" in p:
                value = p["default"]
            elif p.get("required", False):
                raise ValueError(f"{element['code']}: missing required parameter {name!r}")
            else:
                continue
            domain = p.get("domain")
            if domain is not None and value is not None:
                lo, hi = domain
                if not (lo <= value <= hi):
                    raise ValueError(
                        f"{element['code']}: parameter {name!r}={value} outside domain [{lo}, {hi}]"
                    )
            resolved[name] = value
        extra = set(supplied) - {p["name"] for p in element["parameters"]}
        if extra:
            raise ValueError(f"{element['code']}: unknown parameter(s) {sorted(extra)}")
        return resolved

    def _combine(self, combo: str, element: dict, phase_results: list[dict], ns: dict):
        total = sum(p["t_s"] for p in phase_results)
        if combo == "sum":
            return total, "plain sum of phase times", None
        if combo == "sum_times_n_events":
            n = ns.get("n_events", 1)
            return total * n, f"sum of phases * n_events({n})", None
        if combo == "sum_times_n_folds":
            n = ns.get("n_folds", 1)
            return total * n, f"sum of phases * n_folds({n})", None
        if combo == "sum_times_n_passes":
            n = ns.get("n_passes", 1)
            return total * n, f"sum of phases * n_passes({n})", None
        if combo == "sum_then_bimanual":
            return self._combine_bimanual(element, phase_results, ns)
        raise ValueError(f"unknown combination rule {combo!r}")

    def _combine_bimanual(self, element: dict, phase_results: list[dict], ns: dict):
        """HAM-style: reach+acquire phases execute simultaneously on both hands
        when hands=='two'. Since the taxonomy's signature provides one
        (symmetric) reach/grasp description rather than distinct left/right
        parameters, both hands perform the identical movement; per
        assembly_rules.bimanual this means t_pair = MAX(t_left, t_right) *
        (1+epsilon_bi) = t_single * (1+epsilon_bi) in the symmetric case, and
        the two hands are tied as co-limiting. Registration phases (any role
        containing 'register') remain sequential and are summed normally."""
        hands = ns.get("hands", "two")
        epsilon_bi = self.globals["epsilon_bi"]
        simultaneous = [p for p in phase_results if p.get("role") not in (None,) and "register" not in p["role"]]
        sequential = [p for p in phase_results if p not in simultaneous]
        t_simul = sum(p["t_s"] for p in simultaneous)
        t_seq = sum(p["t_s"] for p in sequential)
        if hands == "two":
            t_simul_effective = t_simul * (1.0 + epsilon_bi)
            note = (f"reach+acquire phases treated as simultaneous, symmetric "
                    f"both hands (t_left=t_right={t_simul:.4f}s), coupling penalty "
                    f"epsilon_bi={epsilon_bi} applied; registration ({t_seq:.4f}s) sequential")
            limiting_hand = "tied (symmetric two-hand movement)"
        else:
            t_simul_effective = t_simul
            note = "single-hand: no bimanual coupling penalty"
            limiting_hand = "single_hand"
        return t_simul_effective + t_seq, note, limiting_hand


if __name__ == "__main__":
    tax = load_taxonomy("element_taxonomy.json")
    print(f"Loaded taxonomy v{tax.version}: {len(tax.elements)} elements, "
          f"{len(tax.globals)} global parameters, {len(tax.engine_constants)} engine constants")
    r = tax.compute_element("HAG", distance_cm=25.0, precision_class="P2", fabric_class="REF_POPLIN")
    print(f"HAG (acquire_part, 25cm, P2, poplin): t_basic = {r['t_basic_s']:.4f} s")
