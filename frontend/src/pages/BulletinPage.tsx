import { Fragment, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { BulletinOut, CostingReport } from "../api/types";
import { JsonTree } from "../components/JsonTree";
import { StyleTabs } from "../components/StyleTabs";
import { exportBulletinToExcel, exportBulletinToPdf } from "../lib/exports";
import { useAuth, canWrite } from "../auth/AuthContext";

export function BulletinPage() {
  const { id } = useParams();
  const { auth } = useAuth();
  const [bulletin, setBulletin] = useState<BulletinOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [expandedOp, setExpandedOp] = useState<string | null>(null);

  const [labourRate, setLabourRate] = useState(3.2);
  const [efficiency, setEfficiency] = useState(0.85);
  const [costing, setCosting] = useState<CostingReport | null>(null);
  const [costingError, setCostingError] = useState<string | null>(null);

  function load() {
    if (!id) return;
    setLoading(true);
    api
      .getBulletin(id)
      .then(setBulletin)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load bulletin"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id]);

  async function handleCompute() {
    if (!id) return;
    setComputing(true);
    setError(null);
    try {
      await api.computeStyle(id, {});
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "compute failed");
    } finally {
      setComputing(false);
    }
  }

  async function handleRunCosting() {
    if (!id) return;
    setCostingError(null);
    try {
      const report = await api.costing(id, { labour_rate_per_hour: labourRate, efficiency });
      setCosting(report);
    } catch (e) {
      setCostingError(e instanceof ApiError ? e.message : "costing failed");
    }
  }

  if (loading) return <div className="page">Loading bulletin…</div>;
  if (!bulletin) return <div className="page">{error || "Not found"}</div>;

  let runningTotal = 0;

  return (
    <div className="page">
      {id && <StyleTabs styleId={id} styleName={bulletin.style.name} />}
      <div className="page-header">
        <div>
          <h1>{bulletin.style.name}</h1>
          <p className="style-subtitle">
            {bulletin.style.garment_type} / {bulletin.style.variant} / {bulletin.style.size} · bundle{" "}
            {bulletin.style.bundle_size}
          </p>
        </div>
        <div className="page-header-actions">
          {canWrite(auth?.role) && (
            <button className="btn btn-secondary" onClick={handleCompute} disabled={computing}>
              {computing ? "Computing…" : "Recompute"}
            </button>
          )}
          <button
            className="btn btn-ghost"
            onClick={() => exportBulletinToExcel(bulletin, costing)}
            disabled={!bulletin.smv_min}
          >
            Export .xlsx
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => exportBulletinToPdf(bulletin, costing)}
            disabled={!bulletin.smv_min}
          >
            Export .pdf
          </button>
        </div>
      </div>

      {error && <div className="form-error">{error}</div>}

      {bulletin.smv_min == null ? (
        <p className="empty-state">
          Not computed yet.{" "}
          {canWrite(auth?.role) ? "Click Recompute above to run the engine." : "Ask an IE engineer to compute this style."}
        </p>
      ) : (
        <div className="summary-strip">
          <span>
            Style SMV: <strong>{bulletin.smv_min.toFixed(4)} min</strong>
          </span>
          <span>
            TMU: <strong>{bulletin.smv_tmu?.toFixed(1)}</strong>
          </span>
        </div>
      )}

      <div className="table-scroll">
      <table className="data-table bulletin-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Operation</th>
            <th>Bundle</th>
            <th>SMV (min)</th>
            <th>SMV (s)</th>
            <th>Running total (min)</th>
            <th>Engine</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {bulletin.operations.map((op) => {
            const st = op.latest_result?.st_op_min;
            if (st) runningTotal += st;
            const isExpanded = expandedOp === op.operation_id;
            return (
              <Fragment key={op.operation_id}>
                <tr>
                  <td>{op.sequence + 1}</td>
                  <td>{op.name}</td>
                  <td>{op.bundle_size}</td>
                  <td>{st != null ? st.toFixed(4) : "—"}</td>
                  <td>{op.latest_result ? op.latest_result.st_op_s.toFixed(2) : "—"}</td>
                  <td>{st != null ? runningTotal.toFixed(4) : "—"}</td>
                  <td>{op.latest_result?.engine_version ?? "—"}</td>
                  <td>
                    {op.latest_result && (
                      <button
                        className="btn btn-ghost"
                        onClick={() => setExpandedOp(isExpanded ? null : op.operation_id)}
                      >
                        {isExpanded ? "Hide audit trail ▲" : "Audit trail ▼"}
                      </button>
                    )}
                  </td>
                </tr>
                {isExpanded && op.latest_result && (
                  <tr>
                    <td colSpan={8} className="audit-trail-cell">
                      <div className="audit-trail-header">
                        <strong>Full audit trail</strong> — element-by-element breakdown from the
                        engine, computed at {new Date(op.latest_result.computed_at).toLocaleString()}{" "}
                        under allowance profile <code>{op.latest_result.allowance_profile}</code>.
                      </div>
                      <JsonTree data={op.latest_result.audit_trail} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>

      <section className="costing-panel">
        <h2>Costing summary</h2>
        <div className="costing-controls">
          <label>
            Labour rate / hour
            <input
              type="number"
              step="0.01"
              value={labourRate}
              onChange={(e) => setLabourRate(Number(e.target.value))}
            />
          </label>
          <label>
            Efficiency
            <input
              type="number"
              step="0.01"
              min={0.01}
              max={1}
              value={efficiency}
              onChange={(e) => setEfficiency(Number(e.target.value))}
            />
          </label>
          <button className="btn btn-secondary" onClick={handleRunCosting} disabled={!bulletin.smv_min}>
            Run costing
          </button>
        </div>
        {costingError && <div className="form-error">{costingError}</div>}
        {costing && (
          <div className="costing-footer">
            <span>
              SMV: <strong>{costing.smv_min.toFixed(4)} min</strong>
            </span>
            <span>
              Cost / garment: <strong>{costing.cost_per_garment.toFixed(4)}</strong>
            </span>
            <span>
              Efficiency: <strong>{(costing.efficiency * 100).toFixed(1)}%</strong>
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
