import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, tokenStore, type StoredAuth } from "../api/client";

interface AuthContextValue {
  auth: StoredAuth | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  forbiddenMessage: string | null;
  clearForbidden: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<StoredAuth | null>(tokenStore.getAuth());
  const [forbiddenMessage, setForbiddenMessage] = useState<string | null>(null);

  useEffect(() => {
    const unsubscribe = tokenStore.subscribe((event, detail) => {
      if (event === "unauthorized") {
        setAuth(null);
      } else if (event === "forbidden") {
        const detailObj = detail as { detail?: string } | undefined;
        setForbiddenMessage(
          detailObj?.detail || "You do not have permission to perform this action."
        );
      }
    });
    return unsubscribe;
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const token = await api.login(username, password);
    setAuth({ token: token.access_token, role: token.role, username: token.username });
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setAuth(null);
  }, []);

  const clearForbidden = useCallback(() => setForbiddenMessage(null), []);

  const value = useMemo(
    () => ({ auth, login, logout, forbiddenMessage, clearForbidden }),
    [auth, login, logout, forbiddenMessage, clearForbidden]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

export function canWrite(role: string | undefined): boolean {
  return role === "ie_engineer" || role === "administrator";
}

export function isAdmin(role: string | undefined): boolean {
  return role === "administrator";
}
