import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { UsersPage } from "../src/pages/UsersPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, ApiError, tokenStore } from "../src/api/client";
import type { UserOut } from "../src/api/types";

const USERS: UserOut[] = [
  {
    id: "u-1",
    username: "priya.rao",
    full_name: "Priya Rao",
    role: "ie_engineer",
    is_active: true,
    created_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "u-2",
    username: "admin",
    full_name: "Factory Admin",
    role: "administrator",
    is_active: true,
    created_at: "2026-07-01T00:00:00Z",
  },
];

function renderUsersPage() {
  tokenStore.set({ token: "t", role: "administrator", username: "admin" });
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <AuthProvider>
        <UsersPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<UsersPage />", () => {
  it("lists existing users with their role pill", async () => {
    vi.spyOn(api, "listUsers").mockResolvedValue(USERS);
    renderUsersPage();

    expect(await screen.findByText("priya.rao")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getAllByText("ie_engineer").length).toBeGreaterThan(0);
  });

  it("creates a new user and refreshes the list", async () => {
    vi.spyOn(api, "listUsers").mockResolvedValue(USERS);
    const createSpy = vi.spyOn(api, "createUser").mockResolvedValue({
      id: "u-3",
      username: "new.viewer",
      full_name: "New Viewer",
      role: "viewer",
      is_active: true,
      created_at: "2026-09-01T00:00:00Z",
    });

    renderUsersPage();
    await screen.findByText("priya.rao");

    await userEvent.type(screen.getByLabelText(/username/i), "new.viewer");
    await userEvent.type(screen.getByLabelText(/full name/i), "New Viewer");
    await userEvent.type(screen.getByLabelText(/temporary password/i), "hunter22222");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({
        username: "new.viewer",
        full_name: "New Viewer",
        role: "viewer",
        password: "hunter22222",
      })
    );
    expect(await screen.findByText(/user "new\.viewer" created/i)).toBeInTheDocument();
  });

  it("surfaces the API error message when creation fails (e.g. duplicate username)", async () => {
    vi.spyOn(api, "listUsers").mockResolvedValue(USERS);
    vi.spyOn(api, "createUser").mockRejectedValue(new ApiError(400, "username already exists"));

    renderUsersPage();
    await screen.findByText("priya.rao");

    await userEvent.type(screen.getByLabelText(/username/i), "priya.rao");
    await userEvent.type(screen.getByLabelText(/full name/i), "Dup");
    await userEvent.type(screen.getByLabelText(/temporary password/i), "hunter22222");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));

    expect(await screen.findByText("username already exists")).toBeInTheDocument();
  });
});
