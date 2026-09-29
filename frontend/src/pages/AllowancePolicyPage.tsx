import { useEffect, useRef, useState } from "react";
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
  // Which existing version's document (if any) is currently loaded into the
  // form, and which row's fetch is in flight.
  const [loadedFrom, setLoadedFrom] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

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

  async function handleUseAsStartingPoint(policy: AllowancePolicyOut) {
    setLoadingId(policy.id);
    setError(null);
    setSuccess(null);
    setJsonError(null);
    try {
      const detail = await api.getAllowancePolicy(policy.id);
      setPolicyName(detail.policy_name);
      setDocumentText(JSON.stringify(detail.document, null, 2));
      setLoadedFrom(`${detail.policy_name} v${detail.version}`);
      // The form sits below the version table; without this the click looks
      // like it did nothing. (Optional-called: jsdom doesn't implement it.)
      formRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to load policy document");
    } finally {
      setLoadingId(null);
    }
  }

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
      setLoadedFrom(null);
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
              <th></th>
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
                <td className="row-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleUseAsStartingPoint(p)}
                    disabled={loadingId !== null}
                  >
                    {loadingId === p.id ? "Loading…" : "Use as starting point"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form className="style-form-inline" onSubmit={handleCreate} ref={formRef}>
        <h2>Create a new policy version</h2>
        <p className="style-subtitle" style={{ margin: "0 0 12px" }}>
          Click <strong>Use as starting point</strong> on any version above to load its full
          document here and edit it, or compose one from scratch.
        </p>
        {loadedFrom && (
          <div className="form-success" role="status">
            Loaded the document from <strong>{loadedFrom}</strong>. Editing it here never changes
            that version. Submitting creates the next version under the policy name below and makes
            it the active one.
          </div>
        )}
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
