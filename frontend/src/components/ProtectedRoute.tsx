import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { auth } = useAuth();
  const location = useLocation();
  if (!auth) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}

/** Gate a route (or a section of one) to specific roles; renders a plain
 * permission-denied message inline rather than redirecting, since the user
 * IS authenticated -- they just can't do this particular thing. */
export function RequireRole({
  roles,
  children,
}: {
  roles: string[];
  children: ReactNode;
}) {
  const { auth } = useAuth();
  if (!auth || !roles.includes(auth.role)) {
    return (
      <div className="permission-denied" role="alert">
        Your role ({auth?.role ?? "unknown"}) does not have permission to view this.
      </div>
    );
  }
  return <>{children}</>;
}
