import { Fragment, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { OperationIn } from "../api/types";
import { StepsEditor } from "./StepsEditor";

// OperationsEditor -- the screen an IE engineer lives in all day. Optimised
// for fast keyboard entry: Enter in the "name" field of the LAST row adds a
// new blank operation and focuses its name field; Enter elsewhere moves
// focus to the next field in the row (native Tab order handles that, Enter
// is wired the same way for engineers who don't want to leave the
// keyboard's home row). Steps are edited in an inline expand-below-row
// panel (no modal round-trip) toggled per row.

export function OperationsEditor({
  operations,
  onChange,
  readOnly = false,
}: {
  operations: OperationIn[];
  onChange: (ops: OperationIn[]) => void;
  readOnly?: boolean;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const nameRefs = useRef<Array<HTMLInputElement | null>>([]);

  function resequence(ops: OperationIn[]): OperationIn[] {
    return ops.map((o, i) => ({ ...o, sequence: i }));
  }

  function addOperation(focus = true) {
    const next = resequence([
      ...operations,
      { name: "", sequence: operations.length, bundle_size: operations[0]?.bundle_size ?? 20, steps: [] },
    ]);
    onChange(next);
    if (focus) {
      requestAnimationFrame(() => nameRefs.current[next.length - 1]?.focus());
    }
  }

  function updateOperation(idx: number, patch: Partial<OperationIn>) {
    const copy = operations.slice();
    copy[idx] = { ...copy[idx], ...patch };
    onChange(copy);
  }

  function removeOperation(idx: number) {
    onChange(resequence(operations.filter((_, i) => i !== idx)));
    setExpanded(null);
  }

  function moveOperation(idx: number, dir: -1 | 1) {
    const target = idx + dir;
    if (target < 0 || target >= operations.length) return;
    const copy = operations.slice();
    [copy[idx], copy[target]] = [copy[target], copy[idx]];
    onChange(resequence(copy));
  }

  function duplicateOperation(idx: number) {
    const copy = operations.slice();
    const clone = JSON.parse(JSON.stringify(copy[idx])) as OperationIn;
    clone.name = `${clone.name} (copy)`;
    copy.splice(idx + 1, 0, clone);
    onChange(resequence(copy));
  }

  function handleNameKeyDown(e: KeyboardEvent<HTMLInputElement>, idx: number) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (idx === operations.length - 1) {
        addOperation();
      } else {
        nameRefs.current[idx + 1]?.focus();
      }
    }
  }

  return (
    <div className="operations-editor">
      <table className="operations-table">
        <thead>
          <tr>
            <th style={{ width: 32 }}>#</th>
            <th>Operation name</th>
            <th style={{ width: 100 }}>Bundle size</th>
            <th style={{ width: 90 }}>Steps</th>
            <th style={{ width: 200 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {operations.map((op, idx) => (
            <Fragment key={idx}>
              <tr className={expanded === idx ? "op-row-expanded" : undefined}>
                <td>{idx + 1}</td>
                <td>
                  <input
                    ref={(el) => {
                      nameRefs.current[idx] = el;
                    }}
                    value={op.name}
                    disabled={readOnly}
                    placeholder="e.g. Attach collar to body"
                    onChange={(e) => updateOperation(idx, { name: e.target.value })}
                    onKeyDown={(e) => handleNameKeyDown(e, idx)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    value={op.bundle_size}
                    disabled={readOnly}
                    onChange={(e) => updateOperation(idx, { bundle_size: Number(e.target.value) })}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setExpanded(expanded === idx ? null : idx)}
                  >
                    {op.steps.length} step{op.steps.length === 1 ? "" : "s"} {expanded === idx ? "▲" : "▼"}
                  </button>
                </td>
                <td className="op-actions">
                  {!readOnly && (
                    <>
                      <button type="button" className="btn btn-ghost" onClick={() => moveOperation(idx, -1)} title="Move up">
                        ↑
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={() => moveOperation(idx, 1)} title="Move down">
                        ↓
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={() => duplicateOperation(idx)} title="Duplicate">
                        ⧉
                      </button>
                      <button type="button" className="btn btn-danger-ghost" onClick={() => removeOperation(idx)} title="Delete">
                        ✕
                      </button>
                    </>
                  )}
                </td>
              </tr>
              {expanded === idx && (
                <tr>
                  <td colSpan={5} className="steps-cell">
                    <StepsEditor
                      steps={op.steps}
                      onChange={(steps) => updateOperation(idx, { steps })}
                    />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      {!readOnly && (
        <button type="button" className="btn btn-secondary" onClick={() => addOperation()}>
          + Add operation (Enter)
        </button>
      )}
    </div>
  );
}
