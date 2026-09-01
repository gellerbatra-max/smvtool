import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AllowancePolicyPage } from "../src/pages/AllowancePolicyPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, ApiError, tokenStore } from "../src/api/client";
import type { AllowancePolicyOut } from "../src/api/types";

const POLICIES: AllowancePolicyOut[] = [
  { id: "p-1", policy_name: "WOVEN_TOPS_DECOMPOSED", version: 1, is_active: false, created_at: "2026-06-01T00:00:00Z" },
  { id: "p-2", policy_name: "WOVEN_TOPS_DECOMPOSED", version: 2, is_active: true, created_at: "2026-08-01T00:00:00Z" },
];

function renderPage() {
  tokenStore.set({ token: "t", role: "administrator", username: "admin" });
  return render(
    <MemoryRouter initialEntries={["/admin/allowance-policy"]}>
      <AuthProvider>
        <AllowancePolicyPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<AllowancePolicyPage />", () => {
  it("shows the active policy banner and lists every version", async () => {
    vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
    vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);

    renderPage();

    expect(await screen.findByText(/Active:/)).toBeInTheDocument();
    // 2 table rows + 1 mention inside the "Active: ..." banner
    expect(screen.getAllByText("WOVEN_TOPS_DECOMPOSED").length).toBe(3);
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("still renders the version list if the active-policy lookup fails (fails soft, not closed)", async () => {
    vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
    vi.spyOn(api, "activeAllowancePolicy").mockRejectedValue(new ApiError(404, "no active policy"));

    renderPage();

    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.queryByText(/Active:/)).not.toBeInTheDocument();
  });

  it("rejects invalid JSON in the document field before submitting", async () => {
    vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
    vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);
    const createSpy = vi.spyOn(api, "createAllowancePolicyVersion");

    renderPage();
    await screen.findByText(/Active:/);

    await userEvent.type(screen.getByLabelText(/policy name/i), "REF_FACTORY_A");
    const docField = screen.getByLabelText(/document/i);
    await userEvent.clear(docField);
    // userEvent.type treats `{`/`}` as special-key syntax -- `{{`/`}}` types
    // the literal character, per @testing-library/user-event's escaping rules.
    await userEvent.type(docField, "{{ not valid json");
    await userEvent.click(screen.getByRole("button", { name: /create new version/i }));

    expect(await screen.findByText(/must be valid json/i)).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("creates a new policy version with the parsed document", async () => {
    vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
    vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);
    const createSpy = vi.spyOn(api, "createAllowancePolicyVersion").mockResolvedValue({
      id: "p-3",
      policy_name: "REF_FACTORY_A",
      version: 1,
      is_active: false,
      created_at: "2026-09-01T00:00:00Z",
    });

    renderPage();
    await screen.findByText(/Active:/);

    await userEvent.type(screen.getByLabelText(/policy name/i), "REF_FACTORY_A");
    const docField = screen.getByLabelText(/document/i);
    await userEvent.clear(docField);
    // userEvent.type parses {}/[] as keyboard-descriptor syntax, which makes
    // typing raw JSON error-prone to escape correctly -- paste() inserts the
    // literal string with no such parsing.
    await userEvent.click(docField);
    await userEvent.paste('{"categories":[]}');
    await userEvent.click(screen.getByRole("button", { name: /create new version/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({
        policy_name: "REF_FACTORY_A",
        document: { categories: [] },
      })
    );
    expect(await screen.findByText(/created REF_FACTORY_A v1/i)).toBeInTheDocument();
  });
});
