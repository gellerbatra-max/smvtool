import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Role, UserOut } from "../api/types";

const ROLES: Role[] = ["viewer", "ie_engineer", "administrator"];

export function UsersPage() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    setLoading(true);
    api
      .listUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load users"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await api.createUser({ username, full_name: fullName, role, password });
      setSuccess(`User "${username}" created.`);
      setUsername("");
      setFullName("");
      setPassword("");
      setRole("viewer");
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to create user");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Users</h1>
      </div>
      <p className="style-subtitle">
        Manage factory accounts and their roles. New accounts default to <code>viewer</code>{" "}
        (read-only) unless a different role is chosen below.
      </p>

      {error && <div className="form-error">{error}</div>}
      {success && <div className="form-success">{success}</div>}

      <form className="style-form-inline" onSubmit={handleCreate}>
        <h2>Add a user</h2>
        <label htmlFor="new-username">Username</label>
        <input
          id="new-username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <label htmlFor="new-fullname">Full name</label>
        <input
          id="new-fullname"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
        <label htmlFor="new-role">Role</label>
        <select id="new-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <label htmlFor="new-password">Temporary password</label>
        <input
          id="new-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create user"}
        </button>
      </form>

      <h2>Existing users</h2>
      {loading ? (
        <p>Loading users…</p>
      ) : users.length === 0 ? (
        <p className="empty-state">No users yet.</p>
      ) : (
        <table className="data-table responsive-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Full name</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td data-label="Username">{u.username}</td>
                <td data-label="Full name">{u.full_name}</td>
                <td data-label="Role">
                  <span className={`role-pill role-pill-${u.role}`}>{u.role}</span>
                </td>
                <td data-label="Status">{u.is_active ? "Active" : "Disabled"}</td>
                <td data-label="Created">{new Date(u.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
