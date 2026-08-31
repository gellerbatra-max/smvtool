import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StyleEditorPage } from "../src/pages/StyleEditorPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { LibraryCatalog, StyleDetailOut } from "../src/api/types";

const CATALOG: LibraryCatalog = {
  variants: ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"],
  sizes: ["S", "M", "L", "XL", "XXL"],
  default_bundle_size: 20,
  seam_operations: [],
  cycle_operations: [],
};

const EXISTING_STYLE: StyleDetailOut = {
  id: "style-1",
  name: "Docker Compose Test",
  garment_type: "woven_shirt",
  variant: "CLASSIC",
  size: "M",
  bundle_size: 20,
  notes: null,
  created_at: "2026-08-31T08:18:45.619997",
  updated_at: "2026-08-31T08:18:45.619998",
  operations: [
    {
      id: "op-1",
      style_id: "style-1",
      name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      sequence: 0,
      bundle_size: 20,
      steps: [],
      created_at: "2026-08-31T08:18:45.619997",
      updated_at: "2026-08-31T08:18:45.619998",
    },
    {
      id: "op-2",
      style_id: "style-1",
      name: "collar: Topstitch/edge-stitch collar outer edge (size M)",
      sequence: 1,
      bundle_size: 20,
      steps: [],
      created_at: "2026-08-31T08:18:45.619997",
      updated_at: "2026-08-31T08:18:45.619998",
    },
  ],
};

function renderNew(role: "administrator" | "viewer" = "administrator") {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter initialEntries={["/styles/new"]}>
      <AuthProvider>
        <Routes>
          <Route path="/styles/new" element={<StyleEditorPage />} />
          <Route path="/styles/:id/edit" element={<div>Edit screen for {"{id}"}</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

function renderEdit(role: "administrator" | "viewer" = "administrator") {
  tokenStore.set({ token: "t", role, username: "u" });
  return render(
    <MemoryRouter initialEntries={["/styles/style-1/edit"]}>
      <AuthProvider>
        <Routes>
          <Route path="/styles/:id/edit" element={<StyleEditorPage />} />
          <Route path="/styles/:id/bulletin" element={<div>Bulletin screen</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<StyleEditorPage /> — new style", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a style with seed_from_library and navigates to its edit screen", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "createStyle").mockResolvedValue({ ...EXISTING_STYLE, id: "new-style-id" });

    renderNew();
    await userEvent.type(screen.getByLabelText(/^name$/i), "New Blouse S");
    await userEvent.click(screen.getByRole("button", { name: /create style/i }));

    expect(api.createStyle).toHaveBeenCalledWith({
      name: "New Blouse S",
      variant: "CLASSIC",
      size: "M",
      bundle_size: 20,
      notes: null,
      seed_from_library: true, // checked by default
    });
    expect(await screen.findByText(/edit screen for/i)).toBeInTheDocument();
  });

  it("does not seed from the library when the checkbox is unchecked", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "createStyle").mockResolvedValue({ ...EXISTING_STYLE, id: "new-style-id" });

    renderNew();
    await userEvent.type(screen.getByLabelText(/^name$/i), "Blank Style");
    await userEvent.click(screen.getByLabelText(/seed operations from the library/i));
    await userEvent.click(screen.getByRole("button", { name: /create style/i }));

    expect(api.createStyle).toHaveBeenCalledWith(
      expect.objectContaining({ seed_from_library: false })
    );
  });
});

describe("<StyleEditorPage /> — edit existing style", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the style's fields and operations from the real StyleDetailOut shape", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "getStyle").mockResolvedValue(EXISTING_STYLE);

    renderEdit();

    expect(await screen.findByDisplayValue("Docker Compose Test")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("collar: Run-stitch collar (close top+under collar, 3 sides) (size M)")
    ).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("collar: Topstitch/edge-stitch collar outer edge (size M)")
    ).toBeInTheDocument();
  });

  it("disables all fields and hides operation actions for a viewer", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "getStyle").mockResolvedValue(EXISTING_STYLE);

    renderEdit("viewer");

    await screen.findByDisplayValue("Docker Compose Test");
    expect(screen.getByDisplayValue("Docker Compose Test")).toBeDisabled();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /save & compute/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /\+ add operation/i })).not.toBeInTheDocument();
  });

  it("saves a renamed style and diffs a removed operation to a single deleteOperation call", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "getStyle").mockResolvedValue(EXISTING_STYLE);
    vi.spyOn(api, "updateStyle").mockResolvedValue({ ...EXISTING_STYLE, name: "Renamed Style" });
    const deleteOpSpy = vi.spyOn(api, "deleteOperation").mockResolvedValue(undefined);
    const updateOpSpy = vi.spyOn(api, "updateOperation").mockResolvedValue(EXISTING_STYLE.operations[0]);

    renderEdit();
    const nameInput = await screen.findByDisplayValue("Docker Compose Test");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Renamed Style");

    // Remove the second operation row via its "✕" delete button.
    const deleteButtons = screen.getAllByTitle("Delete");
    await userEvent.click(deleteButtons[1]);

    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(api.updateStyle).toHaveBeenCalledWith("style-1", {
      name: "Renamed Style",
      variant: "CLASSIC",
      size: "M",
      bundle_size: 20,
      notes: null,
    });
    expect(deleteOpSpy).toHaveBeenCalledExactlyOnceWith("style-1", "op-2");
    expect(updateOpSpy).toHaveBeenCalledExactlyOnceWith("style-1", "op-1", {
      name: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      sequence: 0,
      bundle_size: 20,
      steps: [],
    });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("Save & Compute saves, computes, and navigates to the bulletin", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "getStyle").mockResolvedValue(EXISTING_STYLE);
    vi.spyOn(api, "updateStyle").mockResolvedValue(EXISTING_STYLE);
    vi.spyOn(api, "updateOperation").mockImplementation(
      async (_styleId, opId) => EXISTING_STYLE.operations.find((o) => o.id === opId)!
    );
    const computeSpy = vi.spyOn(api, "computeStyle").mockResolvedValue({
      style_id: "style-1",
      smv_min: 12.57272025755471,
      smv_tmu: 20954.534181681858,
      bt_style_min: 11.9,
      allowance_profile: "WOVEN_TOPS_DECOMPOSED",
      engine_version: "smv_engine_bundle@handoff_v2",
      warnings: [],
      results: [],
    });

    renderEdit();
    await screen.findByDisplayValue("Docker Compose Test");
    await userEvent.click(screen.getByRole("button", { name: /save & compute/i }));

    expect(computeSpy).toHaveBeenCalledWith("style-1", {});
    expect(await screen.findByText("Bulletin screen")).toBeInTheDocument();
  });
});
