import { useState } from "react";
import type { StepDict, StepKind } from "../api/types";

// StepsEditor -- edits the raw step list for one operation, in exactly the
// engine's smv_assembly.py step-dict grammar (see that module's docstring):
//   {"kind": "handling", "element": ..., "params": {...}}
//   {"kind": "bundle",   "element": ..., "params": {...}}
//   {"kind": "seam", "machine_class": ..., "path_length_mm": ..., "spi": ...,
//    "curvature_class": ..., "guidance_class": ..., "plies": ..., "pivots": ...,
//    "attachment": ..., "guided_by": ..., "fabric_class": ..., "count": ...}
//   {"kind": "cycle", "machine_class": ..., "stitches": ..., "count": ...}
// Nothing here computes a time or looks up a constant -- these are pure
// geometry/element-selection INPUTS that get sent to the engine on compute.
// Element codes and machine classes are free-text (not hardcoded selects):
// the taxonomy/machine catalog live only in the vendored engine, and this
// app has no endpoint that enumerates them exhaustively, so constraining
// input to a hardcoded list would risk silently rejecting valid engine
// vocabulary as the taxonomy evolves.

const KINDS: StepKind[] = ["handling", "bundle", "seam", "cycle"];

function emptyStep(kind: StepKind): StepDict {
  if (kind === "handling" || kind === "bundle") {
    return { kind, element: "", params: {} };
  }
  if (kind === "seam") {
    return {
      kind,
      machine_class: "",
      path_length_mm: 0,
      spi: 10,
      curvature_class: "straight",
      guidance_class: "seam_hidden",
      plies: 2,
      pivots: 0,
      attachment: null,
    };
  }
  return { kind: "cycle", machine_class: "", stitches: 0, count: 1 };
}

export function StepsEditor({
  steps,
  onChange,
}: {
  steps: StepDict[];
  onChange: (steps: StepDict[]) => void;
}) {
  const [rawMode, setRawMode] = useState<Record<number, boolean>>({});
  const [rawText, setRawText] = useState<Record<number, string>>({});

  function updateStep(idx: number, next: StepDict) {
    const copy = steps.slice();
    copy[idx] = next;
    onChange(copy);
  }

  function removeStep(idx: number) {
    onChange(steps.filter((_, i) => i !== idx));
  }

  function moveStep(idx: number, dir: -1 | 1) {
    const target = idx + dir;
    if (target < 0 || target >= steps.length) return;
    const copy = steps.slice();
    [copy[idx], copy[target]] = [copy[target], copy[idx]];
    onChange(copy);
  }

  function addStep() {
    onChange([...steps, emptyStep("handling")]);
  }

  return (
    <div className="steps-editor">
      <div className="table-scroll">
      <table className="steps-table">
        <thead>
          <tr>
            <th style={{ width: 32 }}>#</th>
            <th style={{ width: 120 }}>Kind</th>
            <th>Fields</th>
            <th style={{ width: 140 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step, idx) => (
            <tr key={idx}>
              <td>{idx + 1}</td>
              <td>
                <select
                  value={step.kind}
                  onChange={(e) => updateStep(idx, emptyStep(e.target.value as StepKind))}
                  aria-label={`step ${idx + 1} kind`}
                >
                  {KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                {rawMode[idx] ? (
                  <textarea
                    className="raw-json-editor"
                    rows={4}
                    value={rawText[idx] ?? JSON.stringify(step, null, 2)}
                    onChange={(e) => setRawText((r) => ({ ...r, [idx]: e.target.value }))}
                    onBlur={() => {
                      try {
                        const parsed = JSON.parse(rawText[idx] ?? "{}");
                        updateStep(idx, parsed);
                      } catch {
                        /* leave text as-is; user is still typing/fixing JSON */
                      }
                    }}
                  />
                ) : (
                  <StepFields step={step} onChange={(s) => updateStep(idx, s)} />
                )}
              </td>
              <td className="step-actions">
                <button type="button" className="btn btn-ghost" onClick={() => moveStep(idx, -1)} title="Move up">
                  ↑
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => moveStep(idx, 1)} title="Move down">
                  ↓
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() =>
                    setRawMode((r) => ({ ...r, [idx]: !r[idx] }))
                  }
                  title="Toggle raw JSON editing"
                >
                  {"{ }"}
                </button>
                <button type="button" className="btn btn-danger-ghost" onClick={() => removeStep(idx)} title="Delete step">
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <button type="button" className="btn btn-secondary" onClick={addStep}>
        + Add step
      </button>
    </div>
  );
}

function ParamsEditor({
  params,
  onChange,
}: {
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const entries = Object.entries(params ?? {});
  function setEntry(key: string, value: string) {
    const next = { ...params };
    const num = Number(value);
    next[key] = value !== "" && !Number.isNaN(num) && /^-?\d+(\.\d+)?$/.test(value) ? num : value;
    onChange(next);
  }
  function removeEntry(key: string) {
    const next = { ...params };
    delete next[key];
    onChange(next);
  }
  function addEntry() {
    const key = window.prompt("Param name (e.g. distance_cm, precision_class, mass_g)");
    if (!key) return;
    onChange({ ...params, [key]: "" });
  }
  return (
    <div className="params-editor">
      {entries.map(([k, v]) => (
        <span className="param-chip" key={k}>
          <label>{k}=</label>
          <input
            value={String(v)}
            onChange={(e) => setEntry(k, e.target.value)}
            style={{ width: 64 }}
          />
          <button type="button" className="btn btn-ghost" onClick={() => removeEntry(k)}>
            ✕
          </button>
        </span>
      ))}
      <button type="button" className="btn btn-ghost" onClick={addEntry}>
        + param
      </button>
    </div>
  );
}

function StepFields({ step, onChange }: { step: StepDict; onChange: (s: StepDict) => void }) {
  if (step.kind === "handling" || step.kind === "bundle") {
    return (
      <div className="step-fields">
        <label>
          element
          <input
            value={step.element ?? ""}
            placeholder="e.g. HAG, HDS, HBO"
            onChange={(e) => onChange({ ...step, element: e.target.value })}
          />
        </label>
        <ParamsEditor
          params={(step.params as Record<string, unknown>) ?? {}}
          onChange={(params) => onChange({ ...step, params })}
        />
      </div>
    );
  }
  if (step.kind === "seam") {
    return (
      <div className="step-fields">
        <label>
          machine_class
          <input
            value={(step.machine_class as string) ?? ""}
            placeholder="e.g. SNLS-UBT"
            onChange={(e) => onChange({ ...step, machine_class: e.target.value })}
          />
        </label>
        <label>
          path_length_mm
          <input
            type="number"
            value={(step.path_length_mm as number) ?? 0}
            onChange={(e) => onChange({ ...step, path_length_mm: Number(e.target.value) })}
          />
        </label>
        <label>
          spi
          <input
            type="number"
            value={(step.spi as number) ?? 0}
            onChange={(e) => onChange({ ...step, spi: Number(e.target.value) })}
          />
        </label>
        <label>
          curvature_class
          <input
            value={(step.curvature_class as string) ?? ""}
            placeholder="straight/moderate/tight"
            onChange={(e) => onChange({ ...step, curvature_class: e.target.value })}
          />
        </label>
        <label>
          guidance_class
          <input
            value={(step.guidance_class as string) ?? ""}
            placeholder="seam_hidden/seam_visible"
            onChange={(e) => onChange({ ...step, guidance_class: e.target.value })}
          />
        </label>
        <label>
          plies
          <input
            type="number"
            value={(step.plies as number) ?? 0}
            onChange={(e) => onChange({ ...step, plies: Number(e.target.value) })}
          />
        </label>
        <label>
          pivots
          <input
            type="number"
            value={(step.pivots as number) ?? 0}
            onChange={(e) => onChange({ ...step, pivots: Number(e.target.value) })}
          />
        </label>
        <label>
          attachment
          <input
            value={(step.attachment as string) ?? ""}
            placeholder="optional, e.g. ATT-EG"
            onChange={(e) => onChange({ ...step, attachment: e.target.value || null })}
          />
        </label>
      </div>
    );
  }
  // cycle
  return (
    <div className="step-fields">
      <label>
        machine_class
        <input
          value={(step.machine_class as string) ?? ""}
          placeholder="e.g. BH-LS"
          onChange={(e) => onChange({ ...step, machine_class: e.target.value })}
        />
      </label>
      <label>
        stitches
        <input
          type="number"
          value={(step.stitches as number) ?? 0}
          onChange={(e) => onChange({ ...step, stitches: Number(e.target.value) })}
        />
      </label>
      <label>
        count
        <input
          type="number"
          value={(step.count as number) ?? 1}
          onChange={(e) => onChange({ ...step, count: Number(e.target.value) })}
        />
      </label>
    </div>
  );
}
