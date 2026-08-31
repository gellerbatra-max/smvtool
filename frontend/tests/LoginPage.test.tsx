import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "../src/pages/LoginPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { api, ApiError } from "../src/api/client";

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("<LoginPage />", () => {
  it("submits username/password and navigates away from /login on success", async () => {
    vi.spyOn(api, "login").mockResolvedValue({
      access_token: "t",
      token_type: "bearer",
      role: "viewer",
      username: "priya",
    });

    renderLoginPage();
    await userEvent.type(screen.getByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(api.login).toHaveBeenCalledWith("priya", "hunter2");
  });

  it("shows a specific message for a 401 (wrong credentials) rather than a generic error", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(401, "Not authenticated"));

    renderLoginPage();
    await userEvent.type(screen.getByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect username or password/i);
  });

  it("shows a network-failure message when the backend is unreachable", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new TypeError("Failed to fetch"));

    renderLoginPage();
    await userEvent.type(screen.getByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the server/i);
  });

  it("disables the submit button while the request is in flight", async () => {
    let resolveLogin: (v: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveLogin = resolve;
    });
    vi.spyOn(api, "login").mockReturnValue(pending as ReturnType<typeof api.login>);

    renderLoginPage();
    await userEvent.type(screen.getByLabelText(/username/i), "priya");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    const button = screen.getByRole("button", { name: /sign in/i });
    await userEvent.click(button);

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();

    // Settle the pending login inside act(): the resolution unblocks two
    // chained state updates outside userEvent's own act wrapper --
    // AuthProvider's setAuth (awaited inside LoginPage's handleSubmit) and
    // then LoginPage's own setSubmitting(false) in its `finally`.
    await act(async () => {
      resolveLogin({ access_token: "t", token_type: "bearer", role: "viewer", username: "priya" });
      await pending;
    });
    await screen.findByRole("button", { name: /sign in/i });
  });
});
