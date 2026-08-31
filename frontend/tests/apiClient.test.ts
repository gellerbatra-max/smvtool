import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, tokenStore } from "../src/api/client";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client / TokenStore", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.clear();
    vi.restoreAllMocks();
  });

  it("login() stores the token, role, and username from the real Token shape", async () => {
    // Matches backend/app/schemas.py::Token exactly (access_token, token_type,
    // role, username) -- not a guessed shape.
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse(200, {
        access_token: "abc.def.ghi",
        token_type: "bearer",
        role: "ie_engineer",
        username: "priya",
      })
    );

    const token = await api.login("priya", "hunter2");

    expect(token.access_token).toBe("abc.def.ghi");
    expect(tokenStore.get()).toBe("abc.def.ghi");
    expect(tokenStore.getAuth()).toEqual({
      token: "abc.def.ghi",
      role: "ie_engineer",
      username: "priya",
    });
    // Persisted so a page refresh doesn't force a re-login.
    expect(JSON.parse(localStorage.getItem("smv_auth")!)).toEqual({
      token: "abc.def.ghi",
      role: "ie_engineer",
      username: "priya",
    });
  });

  it("login() sends credentials as a form-encoded body (OAuth2PasswordRequestForm), not JSON", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse(200, { access_token: "t", token_type: "bearer", role: "viewer", username: "u" }));

    await api.login("u", "p");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ "Content-Type": "application/x-www-form-urlencoded" });
    expect(String(init.body)).toBe("username=u&password=p");
  });

  it("a 401 response clears the token store and emits 'unauthorized' to subscribers", async () => {
    tokenStore.set({ token: "stale-token", role: "viewer", username: "u" });
    vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse(401, { detail: "Not authenticated" }));

    const events: string[] = [];
    tokenStore.subscribe((event) => events.push(event));

    await expect(api.me()).rejects.toThrow(ApiError);
    expect(tokenStore.get()).toBeNull();
    expect(events).toContain("unauthorized");
  });

  it("a 403 response emits 'forbidden' with the server's detail message but keeps the token", async () => {
    tokenStore.set({ token: "still-valid", role: "viewer", username: "u" });
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse(403, { detail: "viewer role cannot delete styles" })
    );

    let forbiddenDetail: unknown;
    tokenStore.subscribe((event, detail) => {
      if (event === "forbidden") forbiddenDetail = detail;
    });

    await expect(api.deleteStyle("style-1")).rejects.toThrow(ApiError);
    expect(tokenStore.get()).toBe("still-valid"); // 403 != logged out
    expect(forbiddenDetail).toEqual({ detail: "viewer role cannot delete styles" });
  });

  it("a 204 response resolves to undefined instead of trying to parse an empty body", async () => {
    tokenStore.set({ token: "t", role: "administrator", username: "u" });
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    const result = await api.deleteStyle("style-1");
    expect(result).toBeUndefined();
  });

  it("a 422 with a Pydantic-shaped detail array renders a readable message, not '[object Object]'", async () => {
    // Found via an actual browser walkthrough against a live backend, not a
    // mocked test: FastAPI/Pydantic 422s send `detail` as an array of
    // {type, loc, msg, input} objects. String(thatArray) previously produced
    // the literal text "[object Object],[object Object]".
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse(422, {
        detail: [
          { type: "missing", loc: ["body", "username"], msg: "Field required", input: null },
          { type: "missing", loc: ["body", "password"], msg: "Field required", input: null },
        ],
      })
    );

    await expect(api.login("", "")).rejects.toThrow(
      "username: Field required; password: Field required"
    );
  });

  it("attaches the stored bearer token as an Authorization header on authenticated calls", async () => {
    tokenStore.set({ token: "my-jwt", role: "ie_engineer", username: "u" });
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse(200, []));

    await api.listStyles();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ Authorization: "Bearer my-jwt" });
  });
});
