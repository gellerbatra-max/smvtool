import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AllowancePolicyPage } from "../src/pages/AllowancePolicyPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, ApiError, tokenStore } from "../src/api/client";
import type { AllowancePolicyDetailOut, AllowancePolicyOut } from "../src/api/types";

const POLICIES: AllowancePolicyOut[] = [
  { id: "p-1", policy_name: "WOVEN_TOPS_DECOMPOSED", version: 1, is_active: false, created_at: "2026-06-01T00:00:00Z" },
  { id: "p-2", policy_name: "WOVEN_TOPS_DECOMPOSED", version: 2, is_active: true, created_at: "2026-08-01T00:00:00Z" },
];

// Shaped like a real GET /allowance-policies/{id}: `profiles` is an ARRAY of
// {code, ...} records (not a dict keyed by code), as in the shipped policy.
const V2_DETAIL: AllowancePolicyDetailOut = {
  ...POLICIES[1],
  document: {
    spec: { id: "wt-allowance-policy", version: "0.1.1" },
    profiles: [{ code: "WOVEN_TOPS_DECOMPOSED", values_percent: { PERSONAL: 5.0, CONTINGENCY: 1.5 } }],
  },
};

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
  // Spies (and their accumulated call counts) otherwise leak across tests.
  beforeEach(() => {
    vi.restoreAllMocks();
  });

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

  describe("Use as starting point", () => {
    async function loadV2() {
      vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
      vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);
      const getSpy = vi.spyOn(api, "getAllowancePolicy").mockResolvedValue(V2_DETAIL);
      renderPage();
      await screen.findByText(/Active:/);
      // one button per row, in POLICIES order: buttons[0] = p-1 (v1), buttons[1] = p-2 (v2)
      const buttons = screen.getAllByRole("button", { name: /use as starting point/i });
      return { getSpy, buttons };
    }

    it("loads the chosen version's document, pretty-printed, and its policy name into the form", async () => {
      const { getSpy, buttons } = await loadV2();

      await userEvent.click(buttons[1]);

      expect(getSpy).toHaveBeenCalledWith("p-2");
      await waitFor(() =>
        expect(screen.getByLabelText(/policy name/i)).toHaveValue("WOVEN_TOPS_DECOMPOSED")
      );
      const docField = screen.getByLabelText(/document/i) as HTMLTextAreaElement;
      expect(JSON.parse(docField.value)).toEqual(V2_DETAIL.document);
      expect(docField.value).toContain("\n  "); // indented, not a single-line dump
    });

    it("says exactly what was loaded and what submitting will do", async () => {
      const { buttons } = await loadV2();

      await userEvent.click(buttons[1]);

      const notice = await screen.findByText(/loaded the document from/i);
      expect(notice).toHaveTextContent(/WOVEN_TOPS_DECOMPOSED v2/);
      expect(notice).toHaveTextContent(/never changes that version/i);
      expect(notice).toHaveTextContent(/active one/i);
    });

    it("submits the loaded document unchanged (round-trips) as a new version", async () => {
      const { buttons } = await loadV2();
      const createSpy = vi.spyOn(api, "createAllowancePolicyVersion").mockResolvedValue({
        id: "p-3", policy_name: "WOVEN_TOPS_DECOMPOSED", version: 3, is_active: true,
        created_at: "2026-09-01T00:00:00Z",
      });

      await userEvent.click(buttons[1]);
      await waitFor(() => expect(screen.getByLabelText(/policy name/i)).toHaveValue("WOVEN_TOPS_DECOMPOSED"));
      await userEvent.click(screen.getByRole("button", { name: /create new version/i }));

      await waitFor(() =>
        expect(createSpy).toHaveBeenCalledWith({
          policy_name: "WOVEN_TOPS_DECOMPOSED",
          document: V2_DETAIL.document,
        })
      );
      // the "loaded from" notice is cleared once it's been submitted
      expect(await screen.findByText(/created WOVEN_TOPS_DECOMPOSED v3/i)).toBeInTheDocument();
      expect(screen.queryByText(/loaded the document from/i)).not.toBeInTheDocument();
    });

    it("reports a fetch failure and leaves the form untouched", async () => {
      vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
      vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);
      vi.spyOn(api, "getAllowancePolicy").mockRejectedValue(new ApiError(404, "allowance policy not found"));
      renderPage();
      await screen.findByText(/Active:/);

      await userEvent.click(screen.getAllByRole("button", { name: /use as starting point/i })[0]);

      expect(await screen.findByText(/allowance policy not found/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/policy name/i)).toHaveValue("");
      expect(screen.queryByText(/loaded the document from/i)).not.toBeInTheDocument();
    });

    it("no longer claims the backend can't return an existing document", async () => {
      vi.spyOn(api, "listAllowancePolicies").mockResolvedValue(POLICIES);
      vi.spyOn(api, "activeAllowancePolicy").mockResolvedValue(POLICIES[1]);
      renderPage();
      await screen.findByText(/Active:/);

      expect(screen.queryByText(/can't be pre-filled/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/return only policy metadata/i)).not.toBeInTheDocument();
    });
  });
});
