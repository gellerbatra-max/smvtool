import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BulletinPage } from "../src/pages/BulletinPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { BulletinOut } from "../src/api/types";

// Shaped exactly like a real GET /styles/{id}/bulletin response (confirmed
// against the live backend), including the field names the previous
// LibraryPage bug got wrong on a different endpoint (`operation` there vs.
// `name` here -- this page's schema really does use `name`).
const BULLETIN: BulletinOut = {
  style: {
    id: "style-1",
    name: "Docker Compose Test",
    garment_type: "woven_shirt",
    variant: "CLASSIC",
    size: "M",
    bundle_size: 20,
    notes: null,
    created_at: "2026-08-31T08:18:45.619997",
    updated_at: "2026-08-31T08:18:45.619998",
  },
  smv_min: 12.57272025755471,
  smv_tmu: 20954.534181681858,
  operations: [
    {
      operation_id: "op-1",
      name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      sequence: 0,
      bundle_size: 20,
      latest_result: {
        id: "result-1",
        st_op_s: 15.76,
        st_op_min: 0.2627,
        bt_op_s: 14.17,
        bt_op_min: 0.2361,
        allowance_profile: "WOVEN_TOPS_DECOMPOSED",
        engine_version: "smv_engine_bundle@handoff_v2",
        computed_at: "2026-08-31T08:18:50.0",
        audit_trail: { t_basic_s: 14.17 },
      },
    },
    {
      operation_id: "op-2",
      name: "collar: Topstitch/edge-stitch collar outer edge (size M)",
      sequence: 1,
      bundle_size: 20,
      latest_result: null,
    },
  ],
};

function renderBulletinPage(role: "administrator" | "viewer" = "administrator") {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter initialEntries={["/styles/style-1/bulletin"]}>
      <AuthProvider>
        <Routes>
          <Route path="/styles/:id/bulletin" element={<BulletinPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<BulletinPage />", () => {
  // Same reason as StyleListPage.test.tsx: without this, un-restored spies'
  // accumulated call counts leak across tests in this file.
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the operation breakdown with a running total, from the real BulletinOut shape", async () => {
    vi.spyOn(api, "getBulletin").mockResolvedValue(BULLETIN);

    renderBulletinPage();

    expect(await screen.findByRole("heading", { name: "Docker Compose Test" })).toBeInTheDocument();
    expect(screen.getByText(/12\.5727 min/)).toBeInTheDocument();
    expect(
      screen.getByText("collar: Run-stitch collar (close top+under collar, 3 sides) (size M)")
    ).toBeInTheDocument();
    // Second op has no latest_result yet -- rendered as "—", not a crash.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows an uncomputed empty-state instead of a table total when smv_min is null", async () => {
    vi.spyOn(api, "getBulletin").mockResolvedValue({
      ...BULLETIN,
      smv_min: null,
      smv_tmu: null,
    });

    renderBulletinPage();

    expect(await screen.findByText(/not computed yet/i)).toBeInTheDocument();
    expect(screen.getByText(/click recompute above/i)).toBeInTheDocument();
  });

  it("expands the audit trail for a computed operation on click", async () => {
    vi.spyOn(api, "getBulletin").mockResolvedValue(BULLETIN);

    renderBulletinPage();
    await screen.findByRole("heading", { name: "Docker Compose Test" });

    expect(screen.queryByText(/full audit trail/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /audit trail/i }));
    expect(screen.getByText(/full audit trail/i)).toBeInTheDocument();
  });

  it("calls compute and reloads the bulletin when an administrator clicks Recompute", async () => {
    const getBulletinSpy = vi.spyOn(api, "getBulletin").mockResolvedValue(BULLETIN);
    const computeSpy = vi.spyOn(api, "computeStyle").mockResolvedValue({
      style_id: "style-1",
      smv_min: 12.57272025755471,
      smv_tmu: 20954.534181681858,
      bt_style_min: 11.9,
      allowance_profile: "WOVEN_TOPS_DECOMPOSED",
      engine_version: "smv_engine_bundle@handoff_v2",
      warnings: [],
      results: [],
    });

    renderBulletinPage("administrator");
    await screen.findByRole("heading", { name: "Docker Compose Test" });

    await userEvent.click(screen.getByRole("button", { name: /recompute/i }));

    expect(computeSpy).toHaveBeenCalledWith("style-1", {});
    expect(getBulletinSpy).toHaveBeenCalledTimes(2); // initial load + reload after compute
  });

  it("hides Recompute for a viewer, who cannot write", async () => {
    vi.spyOn(api, "getBulletin").mockResolvedValue(BULLETIN);

    renderBulletinPage("viewer");

    await screen.findByRole("heading", { name: "Docker Compose Test" });
    expect(screen.queryByRole("button", { name: /recompute/i })).not.toBeInTheDocument();
  });

  it("runs costing and shows the real CostingReport fields, not guessed ones", async () => {
    vi.spyOn(api, "getBulletin").mockResolvedValue(BULLETIN);
    vi.spyOn(api, "costing").mockResolvedValue({
      smv_min: 12.57272025755471,
      labour_rate_per_hour: 3.2,
      efficiency: 0.85,
      cost_per_garment: 0.7888765651799035,
    });

    renderBulletinPage();
    await screen.findByRole("heading", { name: "Docker Compose Test" });

    await userEvent.click(screen.getByRole("button", { name: /run costing/i }));

    expect(await screen.findByText(/0\.7889/)).toBeInTheDocument();
    expect(screen.getByText(/85\.0%/)).toBeInTheDocument();
  });
});
