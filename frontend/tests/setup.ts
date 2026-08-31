import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Ensure each test starts from a clean DOM and clean localStorage --
// api/client.ts's TokenStore reads localStorage at module-load time, and
// several tests below assert on its behavior across a fresh login/logout.
afterEach(() => {
  cleanup();
  localStorage.clear();
});
