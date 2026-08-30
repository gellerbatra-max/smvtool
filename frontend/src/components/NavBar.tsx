import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { CalibrationBadge } from "./CalibrationBadge";

export function NavBar() {
  const { auth, logout } = useAuth();
  if (!auth) return null;

  return (
    <header className="navbar">
      <div className="navbar-brand">SMV Engine</div>
      <nav className="navbar-links">
        <NavLink to="/styles" className={navClass}>
          Styles
        </NavLink>
        <NavLink to="/library" className={navClass}>
          Library
        </NavLink>
        <NavLink to="/styles/new" className={navClass}>
          New Style
        </NavLink>
      </nav>
      <div className="navbar-right">
        <CalibrationBadge />
        <span className="navbar-user">
          {auth.username} <span className="role-pill">{auth.role}</span>
        </span>
        <button className="btn btn-ghost" onClick={logout}>
          Log out
        </button>
      </div>
    </header>
  );
}

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}
