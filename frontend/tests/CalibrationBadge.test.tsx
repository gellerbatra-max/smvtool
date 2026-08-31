import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalibrationBadge } from "../src/components/CalibrationBadge";
import { api } from "../src/api/client";
import type { CalibrationStatus } from "../src/api/types";

// Matches the real payload shape returned by GET /calibration/status
// (backend/app/engine_bridge.py::calibration_status_summary) verbatim.
function makeStatus(overrides: Partial<CalibrationStatus> = {}): CalibrationStatus {
  return {
    engine_version: "1.0.0",
    taxonomy_version: "2026.08",
    n_symbols: 10,
    n_calibration_pending: 10,
    n_literature_grounded_or_fitted: 0,
    symbols: [
      {
        scope: "global_parameter",
        symbol: "a_steer",
        name: "steering-law coefficient a",
        units: "s",
        default: 0.12,
        status: "calibration-pending",
        source: null,
      },
    ],
    real_factory_calibration_run: false,
    note: "No real factory time-study data has been loaded into this application yet.",
    ...overrides,
  };
}

describe("<CalibrationBadge />", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a loading state before the calibration status resolves", () => {
    vi.spyOn(api, "calibrationStatus").mockReturnValue(new Promise(() => {})); // never resolves
    render(<CalibrationBadge />);
    expect(screen.getByText(/calibration…/i)).toBeInTheDocument();
  });

  it("renders the pending/total count and applies the 'danger' level when >=50% of coefficients are calibration-pending", async () => {
    vi.spyOn(api, "calibrationStatus").mockResolvedValue(makeStatus({ n_symbols: 10, n_calibration_pending: 10 }));
    render(<CalibrationBadge />);

    const badge = await screen.findByRole("button", { name: /10\/10 coefficients calibration-pending/i });
    expect(badge.className).toContain("calibration-badge-danger");
  });

  it("applies the 'ok' level when zero coefficients are pending", async () => {
    vi.spyOn(api, "calibrationStatus").mockResolvedValue(
      makeStatus({ n_symbols: 10, n_calibration_pending: 0 })
    );
    render(<CalibrationBadge />);

    const badge = await screen.findByRole("button", { name: /0\/10 coefficients calibration-pending/i });
    expect(badge.className).toContain("calibration-badge-ok");
  });

  it("expands a popover on click showing the honest not-yet-calibrated disclosure and per-symbol table", async () => {
    vi.spyOn(api, "calibrationStatus").mockResolvedValue(makeStatus());
    render(<CalibrationBadge />);

    const badge = await screen.findByRole("button", { name: /coefficients calibration-pending/i });
    await userEvent.click(badge);

    expect(screen.getByRole("dialog", { name: /calibration status/i })).toBeInTheDocument();
    expect(screen.getByText(/has NOT been run/i)).toBeInTheDocument();
    expect(screen.getByText("a_steer")).toBeInTheDocument();
  });

  it("renders nothing (fails closed) if the status request errors, rather than showing stale/fake data", async () => {
    vi.spyOn(api, "calibrationStatus").mockRejectedValue(new Error("network down"));
    const { container } = render(<CalibrationBadge />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
