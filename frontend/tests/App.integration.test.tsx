import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { tokenStore } from "../src/api/client";

/**
 * NOTE ON SCOPE: this stands in for the real end-to-end check the project's
 * HANDOFF.md calls for ("login -> seed style -> compute -> view bulletin ->
 * what-if, against the live backend") until that can be run against an
 * actual running FastAPI server + browser -- this sandbox cannot bind a
 * listening port (confirmed: `uvicorn` fails with EPERM here), so a real
 * live-backend walkthrough has to happen in a local dev environment
 * (e.g. Claude Code) that can run `uvicorn` + `npm run dev` side by side.
 *
 * What this test DOES verify, faithfully: the full React tree (App ->
 * AuthProvider -> Router -> pages) wired against `fetch`, using response
 * payloads shaped exactly like backend/app/schemas.py's Token/StyleOut/
 * CalibrationStatus models -- i.e. that the frontend's contract with the
 * backend, as far as static inspection of both sides can confirm it, holds.
 */

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("App integration (mocked backend)", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.clear();
    window.history.pushState({}, "", "/login");
  });

  it("walks login -> styles list -> logout back to the login screen", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/auth/login")) {
        return jsonResponse(200, {
          access_token: "jwt-token",
          token_type: "bearer",
          role: "ie_engineer",
          username: "priya",
        });
      }
      if (url.includes("/styles")) {
        return jsonResponse(200, [
          {
            id: "style-1",
            name: "CLASSIC shirt, size M",
            garment_type: "woven_shirt",
            variant: "CLASSIC",
            size: "M",
            bundle_size: 20,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
          },
        ]);
      }
      if (url.includes("/calibration/status")) {
        return jsonResponse(200, {
          engine_version: "1.0.0",
          taxonomy_version: "2026.08",
          n_symbols: 4,
          n_calibration_pending: 4,
          n_literature_grounded_or_fitted: 0,
          symbols: [],
          real_factory_calibration_run: false,
          note: "synthetic only",
        });
      }
      throw new Error(`unexpected fetch to ${url}`);
    });

    render(<App />);

    // Unauthenticated -> ProtectedRoute bounces to /login.
    expect(await screen.findByText(/sign in to continue/i)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    // Post-login: NavBar renders with the authenticated username, and the
    // seeded style from the mocked /styles response is listed.
    expect(await screen.findByText("priya")).toBeInTheDocument();
    expect(await screen.findByText("CLASSIC shirt, size M")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/login"),
      expect.anything()
    );

    await userEvent.click(screen.getByRole("button", { name: /log out/i }));

    // Logout clears auth and NavBar (which renders null when logged out)
    // disappears along with the token.
    await waitFor(() => expect(tokenStore.get()).toBeNull());
    expect(screen.queryByText("priya")).not.toBeInTheDocument();
  });

  it("shows the incorrect-credentials message and does not navigate away from /login on a 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse(401, { detail: "Incorrect username or password" })
    );

    render(<App />);
    await userEvent.type(await screen.findByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect username or password/i);
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument(); // still on login
  });
});
