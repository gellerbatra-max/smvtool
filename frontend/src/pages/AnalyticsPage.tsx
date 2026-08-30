import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { LineBalanceOut, StyleDetailOut, WhatIfResult } from "../api/types";
import { RequireRole } from "../components/ProtectedRoute";
import { JsonTree } from "../components/JsonTree";

export function AnalyticsPage() {
  const { id } = useParams();
  const [style, setStyle] = useState<StyleDetailOut | null>(null);

  useEffect(() => {
    if (id) api.getStyle(id).then(setStyle).catch(() => undefined);
  }, [id]);

  if (!id) return null;

  return (
    <div className="page">
      <h1>Analytics {style ? `— ${style.name}` : ""}</h1>
      <LineBalanceSection styleId={id} />
      <RequireRole roles={["ie_engineer", "administrator"]}>
        <WhatIfSection styleId={id} operationNames={style?.operations.map((o) => o.name) ?? []} />
      </RequireRole>
    </div>
  );
}

function LineBalanceSection({ styleId }: { styleId: string }) {
  const [mode, setMode] = useState<"n_workstations" | "target_rate_per_hour">("n_workstations");
  const [value, setValue] = useState(10);
  const [result, setResult] = useState<LineBalanceOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const payload = mode === "n_workstations" ? { n_workstations: value } : { target_rate_per_hour: value };
      const res = await api.lineBalance(styleId, payload);
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "line balance failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="analytics-section">
      <h2>Line balance (RPW)</h2>
      <div className="analytics-controls">
        <label>
          <input
            type="radio"
            checked={mode === "n_workstations"}
            onChange={() => setMode("n_workstations")}
          />
          Fixed workstations
        </label>
        <label>
          <input
            type="radio"
            checked={mode === "target_rate_per_hour"}
            onChange={() => setMode("target_rate_per_hour")}
          />
          Target rate / hour
        </label>
        <input type="number" value={value} onChange={(e) => setValue(Number(e.target.value))} />
        <button className="btn btn-secondary" onClick={run} disabled={loading}>
          {loading ? "Running…" : "Run"}
        </button>
      </div>
      {error && <div className="form-error">{error}</div>}
      {result && (
        <div className="analytics-result">
          <div className="summary-strip">
            <span>
              Bottleneck workstation: <strong>{result.bottleneck_workstation}</strong>
            </span>
            <span>
              Bottleneck SMV: <strong>{result.bottleneck_smv_min.toFixed(4)} min</strong>
            </span>
            <span>
              Theoretical efficiency: <strong>{(result.theoretical_efficiency * 100).toFixed(1)}%</strong>
            </span>
            <span>
              Workstations used: <strong>{result.n_workstations_used ?? "—"}</strong>
            </span>
          </div>
          {result.workstations && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Workstation</th>
                  <th>Operations</th>
                  <th>Load (min)</th>
                  <th>Idle (min)</th>
                </tr>
              </thead>
              <tbody>
                {result.workstations.map((ws) => (
                  <tr key={ws.workstation}>
                    <td>{ws.workstation}</td>
                    <td>{ws.operations.join(", ") || "—"}</td>
                    <td>{ws.load_min.toFixed(4)}</td>
                    <td>{ws.idle_min.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}

function WhatIfSection({ styleId, operationNames }: { styleId: string; operationNames: string[] }) {
  const [operationName, setOperationName] = useState(operationNames[0] ?? "");
  const [machineClass, setMachineClass] = useState("");
  const [stepKind, setStepKind] = useState("seam");
  const [nWorkstations, setNWorkstations] = useState<number | "">("");
  const [labourRate, setLabourRate] = useState<number | "">("");
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!operationName && operationNames.length) setOperationName(operationNames[0]);
  }, [operationNames, operationName]);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.whatIf(styleId, {
        operation_name: operationName,
        changes: { machine_class: machineClass },
        step_kind: stepKind,
        n_workstations: nWorkstations === "" ? null : nWorkstations,
        labour_rate_per_hour: labourRate === "" ? null : labourRate,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "what-if failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="analytics-section">
      <h2>What-if scenario (method / machine swap)</h2>
      <div className="analytics-controls">
        <label>
          Operation
          <select value={operationName} onChange={(e) => setOperationName(e.target.value)}>
            {operationNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Step kind
          <select value={stepKind} onChange={(e) => setStepKind(e.target.value)}>
            <option value="seam">seam</option>
            <option value="cycle">cycle</option>
            <option value="handling">handling</option>
            <option value="bundle">bundle</option>
          </select>
        </label>
        <label>
          New machine_class
          <input value={machineClass} onChange={(e) => setMachineClass(e.target.value)} placeholder="e.g. OL-5T-SS" />
        </label>
        <label>
          Workstations (optional)
          <input
            type="number"
            value={nWorkstations}
            onChange={(e) => setNWorkstations(e.target.value === "" ? "" : Number(e.target.value))}
          />
        </label>
        <label>
          Labour rate/hr (optional)
          <input
            type="number"
            value={labourRate}
            onChange={(e) => setLabourRate(e.target.value === "" ? "" : Number(e.target.value))}
          />
        </label>
        <button className="btn btn-primary" onClick={run} disabled={loading || !operationName || !machineClass}>
          {loading ? "Comparing…" : "Compare"}
        </button>
      </div>
      {error && <div className="form-error">{error}</div>}
      {result && (
        <div className="analytics-result">
          <div className="summary-strip">
            <span>
              Style SMV delta: <strong>{result.style_smv_delta_min.toFixed(4)} min</strong> (
              {result.style_smv_delta_pct.toFixed(2)}%)
            </span>
            {result.cost_delta_per_garment !== undefined && (
              <span>
                Cost delta / garment: <strong>{result.cost_delta_per_garment.toFixed(4)}</strong>
              </span>
            )}
          </div>
          <details>
            <summary>Full comparison detail</summary>
            <JsonTree data={result} />
          </details>
        </div>
      )}
    </section>
  );
}
