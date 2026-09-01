import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { StyleTabs } from "../src/components/StyleTabs";

function renderTabs(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/styles/:id/bulletin"
          element={<StyleTabs styleId="style-1" styleName="Docker Compose Test" />}
        />
        <Route
          path="/styles/:id/edit"
          element={<StyleTabs styleId="style-1" styleName="Docker Compose Test" />}
        />
        <Route
          path="/styles/:id/analytics"
          element={<StyleTabs styleId="style-1" styleName="Docker Compose Test" />}
        />
        <Route path="/styles" element={<div>Styles list page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("<StyleTabs />", () => {
  it("shows the breadcrumb with the style name and a link back to Styles", () => {
    renderTabs("/styles/style-1/bulletin");
    expect(screen.getByText("Docker Compose Test")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Styles" })).toHaveAttribute("href", "/styles");
  });

  it("falls back to a placeholder when styleName hasn't loaded yet", () => {
    render(
      <MemoryRouter initialEntries={["/x"]}>
        <StyleTabs styleId="style-1" />
      </MemoryRouter>
    );
    expect(screen.getByText("…")).toBeInTheDocument();
  });

  it("marks the Bulletin tab active on the bulletin route", () => {
    renderTabs("/styles/style-1/bulletin");
    expect(screen.getByRole("link", { name: "Bulletin" })).toHaveClass("style-tab-active");
    expect(screen.getByRole("link", { name: "Operations" })).not.toHaveClass("style-tab-active");
  });

  it("marks the Operations tab active on the edit route", () => {
    renderTabs("/styles/style-1/edit");
    expect(screen.getByRole("link", { name: "Operations" })).toHaveClass("style-tab-active");
  });

  it("marks the Analytics tab active on the analytics route", () => {
    renderTabs("/styles/style-1/analytics");
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveClass("style-tab-active");
  });

  it("links each tab to the correct style-scoped route", () => {
    renderTabs("/styles/style-1/bulletin");
    expect(screen.getByRole("link", { name: "Bulletin" })).toHaveAttribute(
      "href",
      "/styles/style-1/bulletin"
    );
    expect(screen.getByRole("link", { name: "Operations" })).toHaveAttribute(
      "href",
      "/styles/style-1/edit"
    );
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute(
      "href",
      "/styles/style-1/analytics"
    );
  });
});
