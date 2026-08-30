import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { LibraryBulletin, LibraryCatalog } from "../api/types";
import { useAuth, canWrite } from "../auth/AuthContext";

export function LibraryPage() {
  const { auth } = useAuth();
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<LibraryCatalog | null>(null);
  const [variant, setVariant] = useState("CLASSIC");
  const [size, setSize] = useState("M");
  const [bundleSize, setBundleSize] = useState(20);
  const [bulletin, setBulletin] = useState<LibraryBulletin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  useEffect(() => {
    api.library().then((c) => {
      setCatalog(c);
      setSize(c.sizes.includes("M") ? "M" : c.sizes[0]);
    }).catch((e) => setError(e instanceof Error ? e.message : "failed to load library"));
  }, []);

  useEffect(() => {
    if (!catalog) return;
    setError(null);
    api
      .libraryBulletin({ size, variant, bundle_size: bundleSize })
      .then(setBulletin)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load bulletin"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, size, variant, bundleSize]);

  async function seedStyle() {
    setSeeding(true);
    setError(null);
    try {
      const style = await api.createStyle({
        name: `${variant} ${size}`,
        variant,
        size,
        bundle_size: bundleSize,
        seed_from_library: true,
      });
      navigate(`/styles/${style.id}/edit`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to seed style");
    } finally {
      setSeeding(false);
    }
  }

  if (!catalog) return <div className="page">Loading library…</div>;

  return (
    <div className="page">
      <h1>Library</h1>
      <p>Browse the seeded woven-shirt operation library. Numbers below are computed live by the engine.</p>
      <div className="library-controls">
        <label>
          Variant
          <select value={variant} onChange={(e) => setVariant(e.target.value)}>
            {catalog.variants.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Size
          <select value={size} onChange={(e) => setSize(e.target.value)}>
            {catalog.sizes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bundle size
          <input
            type="number"
            min={1}
            value={bundleSize}
            onChange={(e) => setBundleSize(Number(e.target.value))}
          />
        </label>
        {canWrite(auth?.role) && (
          <button className="btn btn-primary" onClick={seedStyle} disabled={seeding}>
            {seeding ? "Seeding…" : `Seed a new style from ${variant}/${size}`}
          </button>
        )}
      </div>
      {error && <div className="form-error">{error}</div>}
      {bulletin && (
        <>
          <div className="summary-strip">
            <span>
              <strong>{bulletin.operations.length}</strong> operations
            </span>
            <span>
              SMV: <strong>{bulletin.smv_min.toFixed(3)} min</strong>
            </span>
            <span>
              TMU: <strong>{bulletin.smv_tmu.toFixed(1)}</strong>
            </span>
            <span>
              Engine: <code>{bulletin.engine_version}</code>
            </span>
          </div>
          {bulletin.warnings.length > 0 && (
            <ul className="warnings-list">
              {bulletin.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Operation</th>
                <th>ST (min)</th>
                <th>ST (s)</th>
              </tr>
            </thead>
            <tbody>
              {bulletin.operations.map((op, i) => {
                const o = op as Record<string, unknown>;
                return (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{String(o.operation_name ?? o.name ?? "—")}</td>
                    <td>{typeof o.ST_op_min === "number" ? o.ST_op_min.toFixed(4) : "—"}</td>
                    <td>{typeof o.ST_op_s === "number" ? o.ST_op_s.toFixed(2) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
