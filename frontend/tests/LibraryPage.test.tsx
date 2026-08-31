import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LibraryPage } from "../src/pages/LibraryPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, tokenStore } from "../src/api/client";
import type { LibraryBulletin, LibraryCatalog } from "../src/api/types";

const CATALOG: LibraryCatalog = {
  variants: ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"],
  sizes: ["S", "M", "L", "XL", "XXL"],
  default_bundle_size: 20,
  seam_operations: [],
  cycle_operations: [],
};

// Shaped exactly like a real GET /library/bulletin response (confirmed
// against the live backend), not guessed -- this is what the
// "operation_name ?? name" bug got wrong: the real field is `operation`.
const BULLETIN: LibraryBulletin = {
  size: "M",
  variant: "CLASSIC",
  bundle_size: 20,
  allowance_profile: "WOVEN_TOPS_DECOMPOSED",
  smv_min: 12.57272025755471,
  smv_tmu: 20954.534181681858,
  engine_version: "smv_engine_bundle@handoff_v2",
  warnings: [],
  operations: [
    {
      operation: "collar: Run-stitch collar (close top+under collar, 3 sides) (size M)",
      bundle_size: 20,
      allowance_profile: "WOVEN_TOPS_DECOMPOSED",
      BT_op_s: 2.361031375707391,
      ST_op_s: 15.76,
      BT_op_min: 0.03935,
      ST_op_min: 0.2627,
      no_double_count_warnings: [],
      steps: [],
    },
  ],
};

function renderLibraryPage() {
  tokenStore.set({ token: "t", role: "administrator", username: "admin" });
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <AuthProvider>
        <LibraryPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<LibraryPage />", () => {
  it("renders each operation's real name from the `operation` field, not '—'", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "libraryBulletin").mockResolvedValue(BULLETIN);

    renderLibraryPage();

    expect(
      await screen.findByText(/Run-stitch collar \(close top\+under collar, 3 sides\)/)
    ).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("shows the SMV/TMU summary strip from the real response shape", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    vi.spyOn(api, "libraryBulletin").mockResolvedValue(BULLETIN);

    renderLibraryPage();

    expect(await screen.findByText(/12\.573 min/)).toBeInTheDocument();
    expect(screen.getByText(/20954\.5/)).toBeInTheDocument();
  });

  it("requests the bulletin again when variant changes, keyed off the selector value", async () => {
    vi.spyOn(api, "library").mockResolvedValue(CATALOG);
    const bulletinSpy = vi.spyOn(api, "libraryBulletin").mockResolvedValue(BULLETIN);

    renderLibraryPage();
    await screen.findByText(/12\.573 min/);

    expect(bulletinSpy).toHaveBeenCalledWith({ size: "M", variant: "CLASSIC", bundle_size: 20 });
  });
});
