// client.ts -- typed fetch wrapper for the SMV backend API.
//
// - Base URL comes from VITE_API_BASE_URL (see .env.example / README).
// - The JWT is kept in memory for the life of the tab and mirrored to
//   localStorage so a page refresh doesn't force a re-login; on load we
//   seed the in-memory token from localStorage.
// - 401 (invalid/expired token) and 403 (role not permitted) are handled
//   globally here via a subscribable listener, rather than per-screen --
//   screens just call `api.xxx()` and let ApiError bubble/be caught by the
//   nearest boundary; App.tsx subscribes once to redirect-on-401 /
//   toast-on-403.
import type {
  AllowancePolicyOut,
  BulletinOut,
  ComputeRequest,
  ComputeResponse,
  CostingReport,
  CostingRequest,
  LibraryBulletin,
  LibraryCatalog,
  LineBalanceOut,
  LineBalanceRequest,
  OperationIn,
  OperationOut,
  StyleCreate,
  StyleDetailOut,
  StyleOut,
  StyleUpdate,
  Token,
  UserCreate,
  UserOut,
  WhatIfRequest,
  WhatIfResult,
  CalibrationStatus,
  ChangeLogOut,
} from "./types";

const API_BASE_URL: string =
  (import.meta as unknown as { env: Record<string, string | undefined> }).env
    ?.VITE_API_BASE_URL || "http://localhost:8000";

const TOKEN_STORAGE_KEY = "smv_access_token";
const AUTH_STORAGE_KEY = "smv_auth";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface StoredAuth {
  token: string;
  role: Token["role"];
  username: string;
}

type AuthListener = (event: "unauthorized" | "forbidden", detail?: unknown) => void;

class TokenStore {
  private token: string | null = null;
  private auth: StoredAuth | null = null;
  private listeners: AuthListener[] = [];

  constructor() {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (raw) {
      try {
        this.auth = JSON.parse(raw) as StoredAuth;
        this.token = this.auth.token;
      } catch {
        this.auth = null;
      }
    }
    // Backwards-compat with a bare-token-only storage shape.
    if (!this.token) {
      this.token = localStorage.getItem(TOKEN_STORAGE_KEY);
    }
  }

  get(): string | null {
    return this.token;
  }

  getAuth(): StoredAuth | null {
    return this.auth;
  }

  set(auth: StoredAuth) {
    this.token = auth.token;
    this.auth = auth;
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  }

  clear() {
    this.token = null;
    this.auth = null;
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }

  subscribe(fn: AuthListener): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== fn);
    };
  }

  emit(event: "unauthorized" | "forbidden", detail?: unknown) {
    for (const l of this.listeners) l(event, detail);
  }
}

export const tokenStore = new TokenStore();

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  form?: Record<string, string>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (opts.form) {
    body = new URLSearchParams(opts.form);
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method || "GET",
    headers,
    body,
  });

  if (res.status === 401) {
    tokenStore.clear();
    tokenStore.emit("unauthorized");
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      /* no body */
    }
    throw new ApiError(401, "Not authenticated", detail);
  }

  if (res.status === 403) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      /* no body */
    }
    tokenStore.emit("forbidden", detail);
    throw new ApiError(403, "Permission denied", detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await res.json().catch(() => undefined) : await res.text();

  if (!res.ok) {
    const message =
      (isJson && payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail?: unknown }).detail)
        : undefined) || `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message, payload);
  }

  return payload as T;
}

export const api = {
  // -------------------------------------------------------------- auth --
  async login(username: string, password: string): Promise<Token> {
    const token = await request<Token>("/auth/login", {
      method: "POST",
      form: { username, password },
    });
    tokenStore.set({ token: token.access_token, role: token.role, username: token.username });
    return token;
  },
  logout() {
    tokenStore.clear();
  },
  me: () => request<UserOut>("/auth/me"),

  // ------------------------------------------------------------- users --
  createUser: (payload: UserCreate) =>
    request<UserOut>("/users", { method: "POST", body: payload }),
  listUsers: () => request<UserOut[]>("/users"),

  // ------------------------------------------------------------ library --
  library: () => request<LibraryCatalog>("/library"),
  libraryBulletin: (params: {
    size?: string;
    variant?: string;
    bundle_size?: number;
    allowance_profile?: string;
  }) => request<LibraryBulletin>("/library/bulletin", { query: params }),

  // ------------------------------------------------------------- styles --
  listStyles: () => request<StyleOut[]>("/styles"),
  createStyle: (payload: StyleCreate) =>
    request<StyleDetailOut>("/styles", { method: "POST", body: payload }),
  getStyle: (styleId: string) => request<StyleDetailOut>(`/styles/${styleId}`),
  updateStyle: (styleId: string, payload: StyleUpdate) =>
    request<StyleDetailOut>(`/styles/${styleId}`, { method: "PUT", body: payload }),
  deleteStyle: (styleId: string) =>
    request<void>(`/styles/${styleId}`, { method: "DELETE" }),

  addOperation: (styleId: string, payload: OperationIn) =>
    request<OperationOut>(`/styles/${styleId}/operations`, { method: "POST", body: payload }),
  updateOperation: (styleId: string, operationId: string, payload: OperationIn) =>
    request<OperationOut>(`/styles/${styleId}/operations/${operationId}`, {
      method: "PUT",
      body: payload,
    }),
  deleteOperation: (styleId: string, operationId: string) =>
    request<void>(`/styles/${styleId}/operations/${operationId}`, { method: "DELETE" }),

  computeStyle: (styleId: string, payload: ComputeRequest = {}) =>
    request<ComputeResponse>(`/styles/${styleId}/compute`, { method: "POST", body: payload }),
  getBulletin: (styleId: string) => request<BulletinOut>(`/styles/${styleId}/bulletin`),
  getChangeLog: (styleId: string) =>
    request<ChangeLogOut[]>(`/styles/${styleId}/change-log`),

  // -------------------------------------------------------- calibration --
  calibrationStatus: () => request<CalibrationStatus>("/calibration/status"),

  // --------------------------------------------------------- allowance --
  listAllowancePolicies: () => request<AllowancePolicyOut[]>("/allowance-policies"),
  activeAllowancePolicy: () => request<AllowancePolicyOut>("/allowance-policies/active"),

  // ------------------------------------------------------------ analytics --
  lineBalance: (styleId: string, payload: LineBalanceRequest) =>
    request<LineBalanceOut>(`/styles/${styleId}/line-balance`, { method: "POST", body: payload }),
  costing: (styleId: string, payload: CostingRequest) =>
    request<CostingReport>(`/styles/${styleId}/costing`, { method: "POST", body: payload }),
  whatIf: (styleId: string, payload: WhatIfRequest) =>
    request<WhatIfResult>(`/styles/${styleId}/what-if`, { method: "POST", body: payload }),
};

export { API_BASE_URL };
