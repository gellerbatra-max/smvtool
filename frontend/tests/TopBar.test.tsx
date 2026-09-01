import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
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

  it("wraps the username in its own element, not bare text, so app.css can hide it on mobile", async () => {
    // Found via a live browser walkthrough at a narrow viewport: the topbar
    // overflowed and forced the whole page to scroll horizontally.
    // app.css's ".topbar-user span:not(.role-pill)" rule is supposed to
    // hide the plain username at <768px, keeping only the role pill --
    // but a CSS element selector can never match a bare text node, so if
    // the username isn't wrapped in its own element, that rule is
    // permanently dead and the username can never actually be hidden.
    renderTopBar();
    const usernameNode = screen.getByText("priya.rao");
    const topbarUser = usernameNode.closest(".topbar-user");
    // Before the fix, "priya.rao" was bare text directly inside
    // .topbar-user, so getByText resolved to .topbar-user itself -- there
    // was no separate element for the CSS rule to target.
    expect(usernameNode).not.toBe(topbarUser);
    expect(usernameNode.tagName).toBe("SPAN");
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

  it("clears the search box when the URL's ?q= is cleared elsewhere, e.g. a 'Clear search' link", async () => {
    // Found via a live browser walkthrough: after submitting a search then
    // clicking StyleListPage's own "Clear search" link (a plain <Link to="/styles">,
    // no relation to this component's input), the box kept showing the old
    // query text even though the list underneath it had reset -- TopBar
    // owned an independent copy of the query instead of reading the URL.
    tokenStore.set({ token: "t", role: "ie_engineer", username: "priya.rao" });
    vi.spyOn(api, "calibrationStatus").mockResolvedValue({
      n_symbols: 20,
      n_calibration_pending: 4,
    } as CalibrationStatus);

    render(
      <MemoryRouter initialEntries={["/styles?q=classic"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/styles"
              element={
                <>
                  <TopBar theme="light" onToggleTheme={vi.fn()} />
                  <Link to="/styles">Clear search</Link>
                </>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const input = await screen.findByRole("searchbox", { name: /search styles/i });
    expect(input).toHaveValue("classic");

    await userEvent.click(screen.getByRole("link", { name: /clear search/i }));

    expect(input).toHaveValue("");
  });
});
