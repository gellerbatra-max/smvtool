import { NavLink } from "react-router-dom";
import { useAuth, canWrite, isAdmin } from "../auth/AuthContext";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "sidebar-link sidebar-link-active" : "sidebar-link";
}

function adminNavClass({ isActive }: { isActive: boolean }) {
  return isActive ? "sidebar-link sidebar-link-admin-active" : "sidebar-link";
}

export function Sidebar() {
  const { auth } = useAuth();
  if (!auth) return null;

  return (
    <nav className="sidebar" aria-label="Main navigation">
      <NavLink to="/styles" className={navClass}>
        Styles
      </NavLink>
      <NavLink to="/library" className={navClass}>
        Library
      </NavLink>

      {canWrite(auth.role) && (
        <NavLink to="/styles/new" className="btn btn-primary sidebar-new-style">
          + New style
        </NavLink>
      )}

      {isAdmin(auth.role) && (
        <div className="sidebar-admin-section">
          <div className="sidebar-section-label">Admin</div>
          <NavLink to="/admin/users" className={adminNavClass}>
            Users
          </NavLink>
          <NavLink to="/admin/allowance-policy" className={adminNavClass}>
            Allowance policy
          </NavLink>
        </div>
      )}
    </nav>
  );
}
