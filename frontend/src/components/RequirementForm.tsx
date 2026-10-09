import { useState } from "react";
import type { Requirement, RequirementInput, RequirementStatus } from "../types/api";

interface RequirementFormProps {
  requirement?: Requirement;
  submitLabel: string;
  onSubmit: (values: RequirementInput) => Promise<void>;
  onCancel: () => void;
}

export function RequirementForm({ requirement, submitLabel, onSubmit, onCancel }: RequirementFormProps) {
  const [title, setTitle] = useState(requirement?.title ?? "");
  const [description, setDescription] = useState(requirement?.description ?? "");
  const [status, setStatus] = useState<RequirementStatus>(requirement?.status ?? "draft");
  const [criteria, setCriteria] = useState(requirement?.acceptance_criteria.join("\n") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({ title: title.trim(), description: description.trim(), status, acceptance_criteria: criteria.split("\n").map((item) => item.trim()).filter(Boolean) });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The requirement could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
      <label className="block text-sm font-medium text-slate-700">Requirement title
        <input required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100" />
      </label>
      <label className="block text-sm font-medium text-slate-700">Description
        <textarea required maxLength={50000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} className="mt-1.5 w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100" />
      </label>
      <label className="block text-sm font-medium text-slate-700">Status
        <select value={status} onChange={(event) => setStatus(event.target.value as RequirementStatus)} className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100">
          <option value="draft">Draft</option><option value="approved">Approved</option><option value="obsolete">Obsolete</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-slate-700">Acceptance criteria <span className="font-normal text-slate-400">(one per line)</span>
        <textarea maxLength={50000} rows={4} value={criteria} onChange={(event) => setCriteria(event.target.value)} className="mt-1.5 w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100" />
      </label>
      {error && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex justify-end gap-3"><button type="button" onClick={onCancel} disabled={saving} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button><button disabled={saving} className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-800 disabled:opacity-60">{saving ? "Saving…" : submitLabel}</button></div>
    </form>
  );
}
