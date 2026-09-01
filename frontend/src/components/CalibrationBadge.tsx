import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CalibrationStatus } from "../api/types";

/** Small, always-visible data-quality disclosure: how many of the engine's
 * coefficients are calibration-pending shipped defaults vs literature-
 * grounded/fitted, per GET /calibration/status. Clicking it expands the
 * full per-symbol table -- this is deliberately not hidden behind a
 * settings page, per the project brief's transparency requirement. */
export function CalibrationBadge() {
  const [status, setStatus] = useState<CalibrationStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .calibrationStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return null;
  if (!status) return <span className="calibration-badge calibration-badge-loading">calibration…</span>;

  const pendingShare = status.n_symbols > 0 ? status.n_calibration_pending / status.n_symbols : 0;
  const level = pendingShare === 0 ? "ok" : pendingShare < 0.5 ? "warn" : "danger";

  return (
    <div className="calibration-badge-wrap">
      <button
        className={`calibration-badge calibration-badge-${level}`}
        onClick={() => setOpen((o) => !o)}
        title="Click to see which engine coefficients are calibration-pending vs literature-grounded"
      >
        {status.n_calibration_pending}/{status.n_symbols} coefficients calibration-pending
      </button>
      {open && (
        <div className="calibration-popover" role="dialog" aria-label="Calibration status">
          <div className="calibration-popover-header">
            <strong>Calibration status</strong>
            <button className="btn btn-ghost" onClick={() => setOpen(false)}>
              ×
            </button>
          </div>
          <p className="calibration-note">{status.note}</p>
          <p>
            Engine version <code>{status.engine_version}</code>, taxonomy{" "}
            <code>{status.taxonomy_version}</code>. Real factory calibration has{" "}
            {status.real_factory_calibration_run ? "" : "NOT "}been run.
          </p>
          <div className="table-scroll">
          <table className="calibration-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Scope</th>
                <th>Name</th>
                <th>Default</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {status.symbols.map((s) => (
                <tr key={`${s.scope}-${s.symbol}`}>
                  <td>
                    <code>{s.symbol}</code>
                  </td>
                  <td>{s.scope}</td>
                  <td>{s.name ?? "—"}</td>
                  <td>{s.default === undefined || s.default === null ? "—" : String(s.default)}</td>
                  <td>
                    <span
                      className={
                        s.status === "calibration-pending"
                          ? "status-pill status-pending"
                          : "status-pill status-grounded"
                      }
                    >
                      {s.status ?? "unknown"}
                    </span>
                  </td>
                  <td>{s.source ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
