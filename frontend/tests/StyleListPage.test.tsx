import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StyleListPage } from "../src/pages/StyleListPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { StyleOut } from "../src/api/types";

const STYLES: StyleOut[] = [
  {
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
];

function renderAsRole(role: "administrator" | "viewer") {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter initialEntries={["/styles"]}>
      <AuthProvider>
        <StyleListPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<StyleListPage />", () => {
  // Without this, spies (and their accumulated call counts) leak across
  // tests in this file -- `vi.spyOn` re-wraps the same underlying mock
  // rather than creating a fresh one, so an un-restored mock's call history
  // from an earlier test silently pollutes a later test's assertions.
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lists styles from the real StyleOut shape, linking the name to its bulletin", async () => {
    vi.spyOn(api, "listStyles").mockResolvedValue(STYLES);

    renderAsRole("administrator");

    const link = await screen.findByRole("link", { name: "Docker Compose Test" });
    expect(link).toHaveAttribute("href", "/styles/style-1/bulletin");
    expect(screen.getByText("woven_shirt")).toBeInTheDocument();
    expect(screen.getByText("CLASSIC")).toBeInTheDocument();
  });

  it("shows the empty state with a create/seed hint when there are no styles yet", async () => {
    vi.spyOn(api, "listStyles").mockResolvedValue([]);

    renderAsRole("administrator");

    expect(await screen.findByText(/no styles yet/i)).toBeInTheDocument();
    expect(screen.getByText(/create one, or seed one from the library/i)).toBeInTheDocument();
  });

  it("hides + New style and Delete for a viewer, who cannot write", async () => {
    vi.spyOn(api, "listStyles").mockResolvedValue(STYLES);

    renderAsRole("viewer");

    await screen.findByRole("link", { name: "Docker Compose Test" });
    expect(screen.queryByRole("link", { name: /new style/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("deletes a style after confirmation and removes it from the list", async () => {
    vi.spyOn(api, "listStyles").mockResolvedValue(STYLES);
    const deleteSpy = vi.spyOn(api, "deleteStyle").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderAsRole("administrator");
    await screen.findByRole("link", { name: "Docker Compose Test" });

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));

    expect(deleteSpy).toHaveBeenCalledWith("style-1");
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Docker Compose Test" })).not.toBeInTheDocument()
    );
  });

  it("does not delete when the confirmation dialog is dismissed", async () => {
    vi.spyOn(api, "listStyles").mockResolvedValue(STYLES);
    const deleteSpy = vi.spyOn(api, "deleteStyle").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderAsRole("administrator");
    await screen.findByRole("link", { name: "Docker Compose Test" });

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));

    expect(deleteSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Docker Compose Test" })).toBeInTheDocument();
  });
});
