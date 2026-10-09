import { useCallback, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { PaginationControls } from "../components/PaginationControls";
import { ProjectForm } from "../components/ProjectForm";
import { RequirementForm } from "../components/RequirementForm";
import { useApiResource } from "../hooks/useApiResource";
import { api } from "../services/api";
import type { Project, ProjectInput, Requirement, RequirementInput } from "../types/api";
import { ErrorPanel } from "./ProjectsPage";

interface ProjectDetailsPageProps {
  project: Project;
  onBack: () => void;
  onProjectUpdated: (project: Project) => void;
}

export function ProjectDetailsPage({ project, onBack, onProjectUpdated }: ProjectDetailsPageProps) {
  const [requirementOffset, setRequirementOffset] = useState(0);
  const requirements = useApiResource(useCallback(() => api.getRequirements(project.id, 20, requirementOffset), [project.id, requirementOffset]));
  const [editingProject, setEditingProject] = useState(false);
  const [creatingRequirement, setCreatingRequirement] = useState(false);
  const [editingRequirement, setEditingRequirement] = useState<Requirement | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function updateProject(values: ProjectInput) {
    const updated = await api.updateProject(project.id, values);
    onProjectUpdated(updated);
    setEditingProject(false);
    setNotice("Project details updated.");
  }

  async function createRequirement(values: RequirementInput) {
    const requirement = await api.createRequirement(project.id, values);
    await requirements.reload();
    setCreatingRequirement(false);
    setNotice(`Requirement “${requirement.title}” created.`);
  }

  async function updateRequirement(values: RequirementInput) {
    if (!editingRequirement) return;
    const requirement = await api.updateRequirement(project.id, editingRequirement.id, values);
    await requirements.reload();
    setEditingRequirement(null);
    setNotice(`Requirement “${requirement.title}” updated.`);
  }

  async function deleteRequirement(requirement: Requirement) {
    if (!window.confirm(`Delete “${requirement.title}”? This cannot be undone.`)) return;
    setActionError(null);
    try {
      await api.deleteRequirement(project.id, requirement.id);
      await requirements.reload();
      setNotice(`Requirement “${requirement.title}” deleted.`);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "The requirement could not be deleted.");
    }
  }

  return <div className="space-y-8">
    <button type="button" onClick={onBack} className="text-sm font-semibold text-violet-700 hover:text-violet-900">← All projects</button>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-violet-700">Project workspace</p><h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">{project.name}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{project.description || "No project description provided."}</p></div><button type="button" onClick={() => { setNotice(null); setEditingProject(true); }} className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50">Edit project</button></div>
    {notice && <p role="status" className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p>}
    {actionError && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{actionError}</p>}
    {editingProject && <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-bold text-slate-900">Edit project</h2><div className="mt-5"><ProjectForm project={project} submitLabel="Save project" onSubmit={updateProject} onCancel={() => setEditingProject(false)} /></div></section>}
    <section className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-bold text-slate-900">Requirements</h2><p className="mt-1 text-sm text-slate-500">Requirements are always scoped to this project.</p></div><button type="button" onClick={() => { setNotice(null); setCreatingRequirement(true); }} className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-800">New requirement</button></div>
      {creatingRequirement && <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h3 className="text-lg font-bold text-slate-900">Create requirement</h3><div className="mt-5"><RequirementForm submitLabel="Create requirement" onSubmit={createRequirement} onCancel={() => setCreatingRequirement(false)} /></div></section>}
      {editingRequirement && <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h3 className="text-lg font-bold text-slate-900">Edit requirement</h3><div className="mt-5"><RequirementForm requirement={editingRequirement} submitLabel="Save requirement" onSubmit={updateRequirement} onCancel={() => setEditingRequirement(null)} /></div></section>}
      {requirements.isLoading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-sm">Loading requirements…</div>}
      {!requirements.isLoading && requirements.error && <ErrorPanel title="Requirements could not be loaded" detail={requirements.error} onRetry={() => void requirements.reload()} />}
      {!requirements.isLoading && !requirements.error && requirements.data?.items.length === 0 && <EmptyState title="No requirements yet" detail="Add the first requirement for this project." />}
      {!requirements.isLoading && !requirements.error && requirements.data && requirements.data.items.length > 0 && <><div className="space-y-3">{requirements.data.items.map((requirement) => <article key={requirement.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold text-slate-900">{requirement.title}</h3><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{requirement.description}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${requirement.status === "approved" ? "bg-emerald-100 text-emerald-700" : requirement.status === "obsolete" ? "bg-slate-200 text-slate-600" : "bg-amber-100 text-amber-800"}`}>{requirement.status}</span></div>{requirement.acceptance_criteria.length > 0 && <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-500">{requirement.acceptance_criteria.map((criterion, index) => <li key={`${requirement.id}-${index}`}>{criterion}</li>)}</ul>}<div className="mt-5 flex gap-3"><button type="button" onClick={() => { setActionError(null); setEditingRequirement(requirement); }} className="text-sm font-semibold text-violet-700 hover:text-violet-900">Edit</button><button type="button" onClick={() => void deleteRequirement(requirement)} className="text-sm font-semibold text-rose-700 hover:text-rose-900">Delete</button></div></article>)}</div><PaginationControls total={requirements.data.total} limit={requirements.data.limit} offset={requirements.data.offset} onChange={setRequirementOffset} /></>}
    </section>
  </div>;
}
