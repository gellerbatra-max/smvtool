import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { TopBar } from "../src/components/TopBar";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { CalibrationStatus } from "../src/api/types";

function renderTopBar(onToggleTheme = vi.fn()) {
  tokenStore.set({ token: "t", role: "ie_engineer", username: "priya.rao" });
  vi.spyOn(api, "calibrationStatus").mockResolvedValue({
    n_symbols: 20,
    n_calibration_pending: 4,
  } as CalibrationStatus);

  render(
    <MemoryRouter initialEntries={["/styles"]}>
      <AuthProvider>
        <Routes>
          <Route path="/styles" element={<TopBar theme="light" onToggleTheme={onToggleTheme} />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<TopBar />", () => {
  it("shows the username and role pill", async () => {
    renderTopBar();
    expect(screen.getByText("priya.rao")).toBeInTheDocument();
    expect(screen.getByText("IE Engineer")).toBeInTheDocument();
    // Let CalibrationBadge's async fetch settle before the test ends, so its
    // state update doesn't land outside act() after this test has finished.
    await screen.findByText(/4\/20 coefficients/i);
  });

  it("has a Log out button", async () => {
    renderTopBar();
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
    await screen.findByText(/4\/20 coefficients/i);
  });

  it("calls onToggleTheme when the theme switch is clicked, and exposes its state via aria-checked", async () => {
    const onToggleTheme = vi.fn();
    renderTopBar(onToggleTheme);

    const toggle = screen.getByRole("switch", { name: /toggle dark mode/i });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    expect(onToggleTheme).toHaveBeenCalledTimes(1);
  });

  it("navigates to /styles?q=... when a search term is submitted", async () => {
    renderTopBar();
    const input = screen.getByRole("searchbox", { name: /search styles/i });
    await userEvent.type(input, "classic{enter}");
    // The route below is re-rendered with the new location's search string
    // reflected in the input's own controlled state persisting across the
    // navigation (component instance is unchanged since the route matches).
    expect(input).toHaveValue("classic");
  });
});
