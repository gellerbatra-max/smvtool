"""test_analytics.py -- integration tests for analytics_router.py, the glue
between the standalone Analytics track (line_balancing/costing/what_if) and
the FastAPI application.

These tests go through the real HTTP surface (TestClient), a real
CLASSIC/M library-seeded style, and the real vendored engine -- no mocking
of engine_bridge or the analytics modules -- so a break in the wiring
(wrong operation shape, wrong allowance policy, wrong role gate) shows up
here even though line_balancing.py/costing.py/what_if.py each already have
their own standalone test suites against a different engine-bundle layout.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def classic_m_style(client, engineer_headers):
    r = client.post("/styles", json={
        "name": "Classic Shirt M (analytics fixture)",
        "variant": "CLASSIC", "size": "M", "seed_from_library": True,
    }, headers=engineer_headers)
    assert r.status_code == 201, r.text
    return r.json()


class TestLineBalance:
    def test_line_balance_by_headcount(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/line-balance",
                         json={"n_workstations": 10}, headers=engineer_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_operations"] == len(classic_m_style["operations"])
        assert body["total_smv_min"] > 0
        assert 0.0 < body["theoretical_efficiency"] <= 1.0
        assert body["bottleneck_smv_min"] > 0

    def test_line_balance_by_target_rate(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/line-balance",
                         json={"target_rate_per_hour": 45.0}, headers=engineer_headers)
        assert r.status_code == 200, r.text
        assert r.json()["n_workstations_used"] >= 1

    def test_line_balance_missing_params_is_400(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/line-balance", json={}, headers=engineer_headers)
        assert r.status_code == 400

    def test_line_balance_viewer_can_read(self, client, engineer_headers, viewer_headers, classic_m_style):
        """Line balance is a read-side analysis over already-computed
        engine output -- viewers are allowed to run it, unlike what-if."""
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/line-balance",
                         json={"n_workstations": 10}, headers=viewer_headers)
        assert r.status_code == 200, r.text

    def test_line_balance_unknown_style_404(self, client, engineer_headers):
        r = client.post("/styles/does-not-exist/line-balance",
                         json={"n_workstations": 5}, headers=engineer_headers)
        assert r.status_code == 404


class TestCosting:
    def test_costing_basic(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/costing",
                         json={"labour_rate_per_hour": 3.20, "efficiency": 0.80},
                         headers=engineer_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cost_per_garment"] > 0
        assert body["smv_min"] > 0

    def test_costing_with_target_output(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/costing",
                         json={"labour_rate_per_hour": 3.20, "efficiency": 0.80,
                               "target_output_per_hour": 45.0},
                         headers=engineer_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["required_operators_for_target"]["operators_required"] > 0

    def test_costing_invalid_efficiency_rejected(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/costing",
                         json={"labour_rate_per_hour": 3.20, "efficiency": 1.5},
                         headers=engineer_headers)
        assert r.status_code == 422  # pydantic validation, efficiency must be <= 1.0


class TestWhatIf:
    def test_what_if_machine_swap(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        # side_seam operation exists in every CLASSIC bulletin per shirt_library.py
        side_seam_op = next(o for o in classic_m_style["operations"]
                             if "side seam" in o["name"].lower())
        r = client.post(f"/styles/{style_id}/what-if", json={
            "operation_name": side_seam_op["name"],
            "changes": {"machine_class": "OL-5T-SS"},
            "step_kind": "seam",
        }, headers=engineer_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["operation_delta"]["ST_op_delta_min"] != 0.0
        assert "style_smv_delta_min" in body

    def test_what_if_with_line_balance_and_costing_propagation(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        side_seam_op = next(o for o in classic_m_style["operations"]
                             if "side seam" in o["name"].lower())
        r = client.post(f"/styles/{style_id}/what-if", json={
            "operation_name": side_seam_op["name"],
            "changes": {"machine_class": "OL-5T-SS"},
            "step_kind": "seam",
            "n_workstations": 10,
            "labour_rate_per_hour": 3.20,
        }, headers=engineer_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "line_balance" in body
        assert "costing" in body
        assert "cost_delta_per_garment" in body

    def test_what_if_unknown_operation_is_400(self, client, engineer_headers, classic_m_style):
        style_id = classic_m_style["id"]
        r = client.post(f"/styles/{style_id}/what-if", json={
            "operation_name": "not a real operation name",
            "changes": {"machine_class": "OL-5T-SS"},
        }, headers=engineer_headers)
        assert r.status_code == 400

    def test_what_if_viewer_forbidden(self, client, viewer_headers, classic_m_style):
        """what-if is gated like a write action (require_writer) even
        though it persists nothing -- see analytics_router.py's docstring
        on that route for the rationale."""
        style_id = classic_m_style["id"]
        side_seam_op = next(o for o in classic_m_style["operations"]
                             if "side seam" in o["name"].lower())
        r = client.post(f"/styles/{style_id}/what-if", json={
            "operation_name": side_seam_op["name"],
            "changes": {"machine_class": "OL-5T-SS"},
        }, headers=viewer_headers)
        assert r.status_code == 403
