import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsPage } from "../src/pages/AnalyticsPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { LineBalanceOut, StyleDetailOut, WhatIfResult } from "../src/api/types";

const STYLE: StyleDetailOut = {
  id: "style-1",
  name: "Docker Compose Test",
  garment_type: "woven_shirt",
  variant: "CLASSIC",
  size: "M",
  bundle_size: 20,
  notes: null,
  created_at: "2026-08-31T08:18:45.619997",
  updated_at: "2026-08-31T08:18:45.619998",
  operations: [
    {
      id: "op-1",
      style_id: "style-1",
      name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      sequence: 0,
      bundle_size: 20,
      steps: [],
      created_at: "2026-08-31T08:18:45.619997",
      updated_at: "2026-08-31T08:18:45.619998",
    },
  ],
};

// Shaped exactly like a real POST /styles/{id}/line-balance response
// (confirmed against the live backend).
const LINE_BALANCE: LineBalanceOut = {
  method: "RPW (Ranked Positional Weight, Helgeson & Birnie 1961) under chain (build-sequence) precedence",
  n_operations: 27,
  total_smv_min: 12.57272025755471,
  bottleneck_workstation: 6,
  bottleneck_smv_min: 1.5522237597386892,
  theoretical_efficiency: 0.809981175630972,
  n_workstations_used: 10,
  workstations: [
    { workstation: 1, operations: ["collar: Run-stitch collar (size M)"], load_min: 1.2948, idle_min: 0.2574 },
  ],
};

// Shaped exactly like a real POST /styles/{id}/what-if response.
const WHAT_IF: WhatIfResult = {
  operation_name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
  change: { machine_class: "OL-5T-SS" },
  operation_delta: { ST_op_delta_min: -0.05, ST_op_delta_pct: -19.03 },
  base_style_smv_min: 12.57272025755471,
  modified_style_smv_min: 12.52,
  style_smv_delta_min: -0.0527,
  style_smv_delta_pct: -0.42,
};

function renderAnalyticsPage(role: "administrator" | "viewer" = "administrator") {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter initialEntries={["/styles/style-1/analytics"]}>
      <AuthProvider>
        <Routes>
          <Route path="/styles/:id/analytics" element={<AnalyticsPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<AnalyticsPage />", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("runs line balance and renders the real LineBalanceOut fields (bottleneck, efficiency, workstations)", async () => {
    vi.spyOn(api, "getStyle").mockResolvedValue(STYLE);
    vi.spyOn(api, "lineBalance").mockResolvedValue(LINE_BALANCE);

    renderAnalyticsPage();
    await screen.findByRole("heading", { name: /analytics — docker compose test/i });

    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText("6")).toBeInTheDocument(); // bottleneck workstation
    expect(screen.getByText(/1\.5522 min/)).toBeInTheDocument();
    expect(screen.getByText(/81\.0%/)).toBeInTheDocument();
  });

  it("sends n_workstations vs. target_rate_per_hour depending on the selected mode", async () => {
    vi.spyOn(api, "getStyle").mockResolvedValue(STYLE);
    const lineBalanceSpy = vi.spyOn(api, "lineBalance").mockResolvedValue(LINE_BALANCE);

    renderAnalyticsPage();
    await screen.findByRole("heading", { name: /analytics — docker compose test/i });

    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));
    expect(lineBalanceSpy).toHaveBeenCalledWith("style-1", { n_workstations: 10 });

    await userEvent.click(screen.getByLabelText(/target rate/i));
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));
    expect(lineBalanceSpy).toHaveBeenLastCalledWith("style-1", { target_rate_per_hour: 10 });
  });

  it("hides the What-if section from a viewer, who lacks ie_engineer/administrator role", async () => {
    vi.spyOn(api, "getStyle").mockResolvedValue(STYLE);

    renderAnalyticsPage("viewer");

    await screen.findByRole("heading", { name: /analytics — docker compose test/i });
    expect(screen.getByRole("heading", { name: /line balance/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /what-if scenario/i })).not.toBeInTheDocument();
  });

  it("runs a what-if comparison and renders the real WhatIfResult delta fields", async () => {
    vi.spyOn(api, "getStyle").mockResolvedValue(STYLE);
    const whatIfSpy = vi.spyOn(api, "whatIf").mockResolvedValue(WHAT_IF);

    renderAnalyticsPage("administrator");
    await screen.findByRole("heading", { name: /what-if scenario/i });

    await userEvent.type(screen.getByLabelText(/new machine_class/i), "OL-5T-SS");
    await userEvent.click(screen.getByRole("button", { name: /compare/i }));

    expect(whatIfSpy).toHaveBeenCalledWith("style-1", {
      operation_name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      changes: { machine_class: "OL-5T-SS" },
      step_kind: "seam",
      n_workstations: null,
      labour_rate_per_hour: null,
    });
    expect(await screen.findByText(/-0\.0527 min/)).toBeInTheDocument();
  });
});
