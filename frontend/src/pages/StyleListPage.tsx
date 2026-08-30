import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { StyleOut } from "../api/types";
import { useAuth, canWrite } from "../auth/AuthContext";

export function StyleListPage() {
  const { auth } = useAuth();
  const [styles, setStyles] = useState<StyleOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listStyles()
      .then(setStyles)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load styles"))
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this style? This cannot be undone.")) return;
    try {
      await api.deleteStyle(id);
      setStyles((s) => s.filter((st) => st.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to delete");
    }
  }

  if (loading) return <div className="page">Loading styles…</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Styles</h1>
        {canWrite(auth?.role) && (
          <Link className="btn btn-primary" to="/styles/new">
            + New style
          </Link>
        )}
      </div>
      {error && <div className="form-error">{error}</div>}
      {styles.length === 0 ? (
        <p className="empty-state">
          No styles yet. {canWrite(auth?.role) ? "Create one, or seed one from the library." : ""}
        </p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Garment type</th>
              <th>Variant</th>
              <th>Size</th>
              <th>Bundle size</th>
              <th>Updated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {styles.map((s) => (
              <tr key={s.id}>
                <td>
                  <Link to={`/styles/${s.id}/bulletin`}>{s.name}</Link>
                </td>
                <td>{s.garment_type}</td>
                <td>{s.variant}</td>
                <td>{s.size}</td>
                <td>{s.bundle_size}</td>
                <td>{new Date(s.updated_at).toLocaleString()}</td>
                <td className="row-actions">
                  <Link className="btn btn-ghost" to={`/styles/${s.id}/edit`}>
                    Edit
                  </Link>
                  <Link className="btn btn-ghost" to={`/styles/${s.id}/bulletin`}>
                    Bulletin
                  </Link>
                  <Link className="btn btn-ghost" to={`/styles/${s.id}/analytics`}>
                    Analytics
                  </Link>
                  {canWrite(auth?.role) && (
                    <button className="btn btn-danger-ghost" onClick={() => handleDelete(s.id)}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
