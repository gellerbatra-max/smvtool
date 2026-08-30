// JsonTree -- generic renderer for arbitrary JSON (used for the audit_trail
// drill-down). Deliberately generic: the engine's per-step audit record
// shape is defined by smv_assembly.py and may grow new fields over time;
// summarising it into a fixed set of named columns would silently drop
// whatever the engine adds next, defeating the "don't summarize it away"
// transparency requirement. Arrays of uniform-shaped objects render as a
// table (the common case: a `steps` list); everything else renders as a
// nested key/value tree.

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function formatScalar(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

export function JsonTree({ data, depth = 0 }: { data: unknown; depth?: number }) {
  if (data === null || data === undefined || typeof data !== "object") {
    return <span className="json-scalar">{formatScalar(data)}</span>;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="json-scalar">[]</span>;
    const allObjects = data.every(isPlainObject);
    if (allObjects) {
      const columns = Array.from(new Set(data.flatMap((row) => Object.keys(row as object))));
      const simpleColumns = columns.filter((c) => data.every((row) => !isPlainObject((row as Record<string, unknown>)[c]) && !Array.isArray((row as Record<string, unknown>)[c])));
      const complexColumns = columns.filter((c) => !simpleColumns.includes(c));
      return (
        <table className="json-array-table">
          <thead>
            <tr>
              {simpleColumns.map((c) => (
                <th key={c}>{c}</th>
              ))}
              {complexColumns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i}>
                {simpleColumns.map((c) => (
                  <td key={c}>{formatScalar((row as Record<string, unknown>)[c])}</td>
                ))}
                {complexColumns.map((c) => (
                  <td key={c}>
                    <JsonTree data={(row as Record<string, unknown>)[c]} depth={depth + 1} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    }
    return (
      <ol className="json-array-list">
        {data.map((v, i) => (
          <li key={i}>
            <JsonTree data={v} depth={depth + 1} />
          </li>
        ))}
      </ol>
    );
  }

  const entries = Object.entries(data as Record<string, unknown>);
  return (
    <table className="json-kv-table">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>
              <JsonTree data={v} depth={depth + 1} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
