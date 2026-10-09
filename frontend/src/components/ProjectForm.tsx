import { useState } from "react";
import type { Project, ProjectInput } from "../types/api";

interface ProjectFormProps {
  project?: Project;
  submitLabel: string;
  onSubmit: (values: ProjectInput) => Promise<unknown>;
  onCancel: () => void;
}

export function ProjectForm({ project, submitLabel, onSubmit, onCancel }: ProjectFormProps) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() || null });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The project could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
      <label className="block text-sm font-medium text-slate-700">Project name
        <input required maxLength={160} value={name} onChange={(event) => setName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100" />
      </label>
      <label className="block text-sm font-medium text-slate-700">Description <span className="font-normal text-slate-400">(optional)</span>
        <textarea maxLength={10000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} className="mt-1.5 w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-violet-600 focus:ring-2 focus:ring-violet-100" />
      </label>
      {error && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} disabled={saving} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button>
        <button disabled={saving} className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-800 disabled:opacity-60">{saving ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  );
}
