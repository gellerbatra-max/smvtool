import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Sidebar } from "../src/components/Sidebar";
import { AuthProvider } from "../src/auth/AuthContext";
import { tokenStore } from "../src/api/client";
import type { Role } from "../src/api/types";

function renderSidebar(role: Role) {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Sidebar />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<Sidebar />", () => {
  it("always shows Styles and Library to any authenticated role", () => {
    renderSidebar("viewer");
    expect(screen.getByRole("link", { name: "Styles" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Library" })).toBeInTheDocument();
  });

  it("hides '+ New style' and the Admin section from a viewer", () => {
    renderSidebar("viewer");
    expect(screen.queryByRole("link", { name: /new style/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("shows '+ New style' but not the Admin section to an ie_engineer", () => {
    renderSidebar("ie_engineer");
    expect(screen.getByRole("link", { name: /new style/i })).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("shows the Admin section (Users, Allowance policy) to an administrator", () => {
    renderSidebar("administrator");
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Allowance policy" })).toBeInTheDocument();
  });
});
