import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { LibraryCatalog, OperationIn, OperationOut, StyleDetailOut } from "../api/types";
import { OperationsEditor } from "../components/OperationsEditor";
import { StyleTabs } from "../components/StyleTabs";
import { useAuth, canWrite } from "../auth/AuthContext";

// StyleEditorPage -- the style construction entry screen: pick garment
// type/variant/size (optionally seeding operations from the library), then
// add/edit/reorder/delete operations. Handles both "create new style" (no
// :id in the route) and "edit existing style" (persisted operations are
// diffed against the backend's per-operation CRUD endpoints on Save, since
// there is no bulk-replace endpoint).

const emptyOperations: OperationIn[] = [];

export function StyleEditorPage() {
  const { id } = useParams();
  const isNew = !id;
  const navigate = useNavigate();
  const { auth } = useAuth();
  const readOnly = !canWrite(auth?.role);

  const [catalog, setCatalog] = useState<LibraryCatalog | null>(null);
  const [name, setName] = useState("");
  const [variant, setVariant] = useState("CLASSIC");
  const [size, setSize] = useState("M");
  const [bundleSize, setBundleSize] = useState(20);
  const [notes, setNotes] = useState("");
  const [seedFromLibrary, setSeedFromLibrary] = useState(true);

  const [originalOps, setOriginalOps] = useState<OperationOut[]>([]);
  const [operations, setOperations] = useState<OperationIn[]>(emptyOperations);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    api.library().then(setCatalog).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (isNew || !id) return;
    setLoading(true);
    api
      .getStyle(id)
      .then((style: StyleDetailOut) => {
        setName(style.name);
        setVariant(style.variant);
        setSize(style.size);
        setBundleSize(style.bundle_size);
        setNotes(style.notes ?? "");
        setOriginalOps(style.operations);
        setOperations(
          style.operations.map((o) => ({
            id: o.id,
            name: o.name,
            sequence: o.sequence,
            bundle_size: o.bundle_size,
            steps: o.steps,
          })) as (OperationIn & { id?: string })[]
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load style"))
      .finally(() => setLoading(false));
  }, [id, isNew]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const style = await api.createStyle({
        name,
        variant,
        size,
        bundle_size: bundleSize,
        notes: notes || null,
        seed_from_library: seedFromLibrary,
      });
      navigate(`/styles/${style.id}/edit`, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to create style");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveExisting() {
    if (!id) return;
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      await api.updateStyle(id, {
        name,
        variant,
        size,
        bundle_size: bundleSize,
        notes: notes || null,
      });

      const currentIds = new Set(
        operations.filter((o) => (o as OperationIn & { id?: string }).id).map((o) => (o as OperationIn & { id?: string }).id)
      );
      for (const orig of originalOps) {
        if (!currentIds.has(orig.id)) {
          await api.deleteOperation(id, orig.id);
        }
      }
      const refreshed: OperationOut[] = [];
      for (const op of operations) {
        const withId = op as OperationIn & { id?: string };
        const payload: OperationIn = {
          name: op.name,
          sequence: op.sequence,
          bundle_size: op.bundle_size,
          steps: op.steps,
        };
        if (withId.id) {
          refreshed.push(await api.updateOperation(id, withId.id, payload));
        } else {
          refreshed.push(await api.addOperation(id, payload));
        }
      }
      setOriginalOps(refreshed);
      setOperations(
        refreshed.map((o) => ({ id: o.id, name: o.name, sequence: o.sequence, bundle_size: o.bundle_size, steps: o.steps })) as (OperationIn & {
          id?: string;
        })[]
      );
      setSavedMessage("Saved.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveAndCompute() {
    await handleSaveExisting();
    if (!id) return;
    try {
      await api.computeStyle(id, {});
      navigate(`/styles/${id}/bulletin`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to compute");
    }
  }

  if (loading) return <div className="page">Loading…</div>;

  if (isNew) {
    return (
      <div className="page">
        <h1>New style</h1>
        <form className="style-form" onSubmit={handleCreate}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </label>
          <label>
            Variant
            <select value={variant} onChange={(e) => setVariant(e.target.value)}>
              {(catalog?.variants ?? ["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"]).map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Size
            <select value={size} onChange={(e) => setSize(e.target.value)}>
              {(catalog?.sizes ?? ["S", "M", "L", "XL", "XXL"]).map((s) => (
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
          <label>
            Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={seedFromLibrary}
              onChange={(e) => setSeedFromLibrary(e.target.checked)}
            />
            Seed operations from the library for this variant/size
          </label>
          {error && <div className="form-error">{error}</div>}
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? "Creating…" : "Create style"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="page">
      {id && <StyleTabs styleId={id} styleName={name} />}
      <div className="page-header">
        <h1>Edit style</h1>
        <div className="page-header-actions">
          <button className="btn btn-secondary" onClick={handleSaveExisting} disabled={saving || readOnly}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="btn btn-primary" onClick={handleSaveAndCompute} disabled={saving || readOnly}>
            Save &amp; Compute
          </button>
        </div>
      </div>
      <div className="style-form style-form-inline">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={readOnly} />
        </label>
        <label>
          Variant
          <input value={variant} onChange={(e) => setVariant(e.target.value)} disabled={readOnly} />
        </label>
        <label>
          Size
          <input value={size} onChange={(e) => setSize(e.target.value)} disabled={readOnly} />
        </label>
        <label>
          Bundle size
          <input
            type="number"
            value={bundleSize}
            onChange={(e) => setBundleSize(Number(e.target.value))}
            disabled={readOnly}
          />
        </label>
        <label>
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} disabled={readOnly} />
        </label>
      </div>
      {error && <div className="form-error">{error}</div>}
      {savedMessage && <div className="form-success">{savedMessage}</div>}
      <h2>Operations</h2>
      <OperationsEditor operations={operations} onChange={(ops) => setOperations(ops)} readOnly={readOnly} />
    </div>
  );
}
