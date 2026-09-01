import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { CalibrationBadge } from "./CalibrationBadge";
import type { Theme } from "../theme/useTheme";

const ROLE_LABEL: Record<string, string> = {
  viewer: "Viewer",
  ie_engineer: "IE Engineer",
  administrator: "Administrator",
};

export function TopBar({ theme, onToggleTheme }: { theme: Theme; onToggleTheme: () => void }) {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);

  // Keep the search box in sync with the URL's own ?q= (the source of
  // truth StyleListPage reads from) rather than owning an independent copy
  // -- otherwise "Clear search", the back button, or a direct link to
  // /styles?q=... leaves stale text sitting in the box that no longer
  // matches what's on screen.
  useEffect(() => {
    setQuery(new URLSearchParams(location.search).get("q") ?? "");
  }, [location.search]);

  if (!auth) return null;

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMobileSearchOpen(false);
    navigate(query.trim() ? `/styles?q=${encodeURIComponent(query.trim())}` : "/styles");
  }

  return (
    <header className="topbar">
      <div className="topbar-brand">SMV Engine</div>
      <form className="topbar-search" onSubmit={handleSearchSubmit} role="search">
        <input
          type="search"
          placeholder="Search styles…"
          aria-label="Search styles"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>
      {/* <768px: the form above is hidden (see app.css); this button opens a
          full-width overlay version of the same input instead. */}
      <button
        type="button"
        className="topbar-search-toggle"
        onClick={() => setMobileSearchOpen(true)}
        aria-label="Search styles"
      >
        🔎
      </button>
      {mobileSearchOpen && (
        <form className="topbar-search-overlay" onSubmit={handleSearchSubmit} role="search">
          <input
            type="search"
            placeholder="Search styles…"
            aria-label="Search styles"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setMobileSearchOpen(false)}
            aria-label="Close search"
          >
            ×
          </button>
        </form>
      )}
      <div className="topbar-right">
        <CalibrationBadge />
        <button
          type="button"
          className="theme-toggle"
          onClick={onToggleTheme}
          role="switch"
          aria-checked={theme === "dark"}
          aria-label="Toggle dark mode"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? "🌙" : "☀️"}
        </button>
        <span className="topbar-user">
          {/* Own <span>, not bare text: app.css's
              ".topbar-user span:not(.role-pill)" (hides the plain username
              at <768px, keeping only the role pill) can only ever match an
              actual element -- bare text was invisible to that selector,
              so the username never actually hid on mobile, which is what
              overflowed the topbar in the first place. */}
          <span>{auth.username}</span>
          <span className={`role-pill role-pill-${auth.role}`}>
            {ROLE_LABEL[auth.role] ?? auth.role}
          </span>
        </span>
        <button className="btn btn-ghost" onClick={logout}>
          Log out
        </button>
      </div>
    </header>
  );
}
