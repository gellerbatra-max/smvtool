import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ProtectedRoute, RequireRole } from "../src/components/ProtectedRoute";
import { useAuth } from "../src/auth/AuthContext";
import type { StoredAuth } from "../src/api/client";

vi.mock("../src/auth/AuthContext", async () => {
  const actual = await vi.importActual<typeof import("../src/auth/AuthContext")>(
    "../src/auth/AuthContext"
  );
  return { ...actual, useAuth: vi.fn() };
});

function mockAuth(auth: StoredAuth | null) {
  (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    auth,
    login: vi.fn(),
    logout: vi.fn(),
    forbiddenMessage: null,
    clearForbidden: vi.fn(),
  });
}

describe("<ProtectedRoute />", () => {
  it("redirects to /login when there is no authenticated user", () => {
    mockAuth(null);
    render(
      <MemoryRouter initialEntries={["/styles"]}>
        <Routes>
          <Route path="/login" element={<div>Login screen</div>} />
          <Route
            path="/styles"
            element={
              <ProtectedRoute>
                <div>Styles screen</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Styles screen")).not.toBeInTheDocument();
  });

  it("renders the protected children when a user is authenticated", () => {
    mockAuth({ token: "t", role: "viewer", username: "priya" });
    render(
      <MemoryRouter initialEntries={["/styles"]}>
        <Routes>
          <Route path="/login" element={<div>Login screen</div>} />
          <Route
            path="/styles"
            element={
              <ProtectedRoute>
                <div>Styles screen</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Styles screen")).toBeInTheDocument();
  });
});

describe("<RequireRole />", () => {
  it("renders a permission-denied message (not a redirect) for an authenticated user lacking the role", () => {
    mockAuth({ token: "t", role: "viewer", username: "priya" });
    render(
      <RequireRole roles={["ie_engineer", "administrator"]}>
        <div>Admin-only content</div>
      </RequireRole>
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/role \(viewer\) does not have permission/i);
    expect(screen.queryByText("Admin-only content")).not.toBeInTheDocument();
  });

  it("renders the gated content when the user's role is included", () => {
    mockAuth({ token: "t", role: "administrator", username: "priya" });
    render(
      <RequireRole roles={["ie_engineer", "administrator"]}>
        <div>Admin-only content</div>
      </RequireRole>
    );
    expect(screen.getByText("Admin-only content")).toBeInTheDocument();
  });
});
