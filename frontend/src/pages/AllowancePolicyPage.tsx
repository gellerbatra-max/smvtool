import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AllowancePolicyOut } from "../api/types";

export function AllowancePolicyPage() {
  const [policies, setPolicies] = useState<AllowancePolicyOut[]>([]);
  const [active, setActive] = useState<AllowancePolicyOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [policyName, setPolicyName] = useState("");
  const [documentText, setDocumentText] = useState("{\n  \n}");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([api.listAllowancePolicies(), api.activeAllowancePolicy().catch(() => null)])
      .then(([list, activePolicy]) => {
        setPolicies(list);
        setActive(activePolicy);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load allowance policies"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setJsonError(null);
    setError(null);
    setSuccess(null);
    let document: Record<string, unknown>;
    try {
      document = JSON.parse(documentText);
    } catch {
      setJsonError("Document must be valid JSON.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await api.createAllowancePolicyVersion({ policy_name: policyName, document });
      setSuccess(`Created ${created.policy_name} v${created.version}.`);
      setPolicyName("");
      setDocumentText("{\n  \n}");
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to create policy version");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Allowance policy</h1>
      </div>
      <p className="style-subtitle">
        Every SMV calculation resolves against exactly one active allowance policy version. Creating
        a new version never edits an existing one in place -- older SMV results stay reproducible
        against the policy document that produced them.
      </p>

      {active && (
        <div className="form-success" role="status">
          Active: <strong>{active.policy_name}</strong> v{active.version} (created{" "}
          {new Date(active.created_at).toLocaleDateString()})
        </div>
      )}

      {error && <div className="form-error">{error}</div>}
      {success && <div className="form-success">{success}</div>}

      <h2>Policy versions</h2>
      {loading ? (
        <p>Loading policies…</p>
      ) : policies.length === 0 ? (
        <p className="empty-state">No allowance policy has been seeded yet.</p>
      ) : (
        <table className="data-table responsive-table">
          <thead>
            <tr>
              <th>Policy name</th>
              <th>Version</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.id}>
                <td data-label="Policy name">{p.policy_name}</td>
                <td data-label="Version">{p.version}</td>
                <td data-label="Status">
                  {p.is_active ? <span className="status-pill status-grounded">active</span> : "—"}
                </td>
                <td data-label="Created">{new Date(p.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form className="style-form-inline" onSubmit={handleCreate}>
        <h2>Create a new policy version</h2>
        <p className="style-subtitle" style={{ margin: "0 0 12px" }}>
          Note: the backend's <code>GET /allowance-policies</code> endpoints currently return only
          policy metadata (name, version, active flag) -- not the document content -- so an existing
          version's document can't be pre-filled here for editing. Compose the full document from
          scratch, or coordinate with whoever has the source JSON used for the last version.
        </p>
        <label htmlFor="policy-name">Policy name</label>
        <input
          id="policy-name"
          value={policyName}
          onChange={(e) => setPolicyName(e.target.value)}
          placeholder="e.g. REF_FACTORY_A"
          required
        />
        <label htmlFor="policy-document">Document (JSON)</label>
        <textarea
          id="policy-document"
          className="raw-json-editor"
          rows={10}
          value={documentText}
          onChange={(e) => setDocumentText(e.target.value)}
          required
        />
        {jsonError && <div className="form-error">{jsonError}</div>}
        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create new version"}
        </button>
      </form>
    </div>
  );
}
