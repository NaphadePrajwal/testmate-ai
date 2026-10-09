import { useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { PaginationControls } from "../components/PaginationControls";
import { ProjectForm } from "../components/ProjectForm";
import type { Project, ProjectInput, ProjectListResponse } from "../types/api";

interface ProjectsPageProps {
  projects: ProjectListResponse | null;
  error: string | null;
  isLoading: boolean;
  onRetry: () => void;
  onCreate: (values: ProjectInput) => Promise<Project>;
  onOpen: (project: Project) => void;
  onPageChange: (offset: number) => void;
}

export function ProjectsPage({ projects, error, isLoading, onRetry, onCreate, onOpen, onPageChange }: ProjectsPageProps) {
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function createProject(values: ProjectInput) {
    const project = await onCreate(values);
    setCreating(false);
    setNotice(`Project “${project.name}” created.`);
    return project;
  }

  return <div className="space-y-8">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold text-violet-700">Testing workspaces</p><h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">Projects</h1><p className="mt-2 text-sm text-slate-500">Organize requirements, test cases, executions and findings by project.</p></div><button type="button" onClick={() => { setNotice(null); setCreating(true); }} className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-800">New project</button></div>
    {notice && <p role="status" className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</p>}
    {creating && <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-bold text-slate-900">Create project</h2><p className="mt-1 text-sm text-slate-500">Start a scoped workspace for requirements and future testing activity.</p><div className="mt-5"><ProjectForm submitLabel="Create project" onSubmit={createProject} onCancel={() => setCreating(false)} /></div></section>}
    {isLoading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-sm">Loading projects…</div>}
    {!isLoading && error && <ErrorPanel title="Projects could not be loaded" detail={error} onRetry={onRetry} />}
    {!isLoading && !error && projects?.items.length === 0 && <EmptyState title="No projects yet" detail="Create a project to begin organizing requirements." />}
    {!isLoading && !error && projects && projects.items.length > 0 && <><div className="grid gap-4 md:grid-cols-2">{projects.items.map((project) => <button type="button" key={project.id} onClick={() => onOpen(project)} className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-violet-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-violet-500"><h2 className="font-semibold text-slate-900">{project.name}</h2><p className="mt-2 text-sm leading-6 text-slate-500">{project.description || "No description provided."}</p><p className="mt-4 text-xs text-slate-400">Created {new Date(project.created_at).toLocaleDateString()} · Open project →</p></button>)}</div><PaginationControls total={projects.total} limit={projects.limit} offset={projects.offset} onChange={onPageChange} /></>}
  </div>;
}

export function ErrorPanel({ title, detail, onRetry }: { title: string; detail: string; onRetry: () => void }) {
  return <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-6"><h2 className="font-semibold text-rose-900">{title}</h2><p className="mt-2 text-sm text-rose-700">{detail}</p><button type="button" onClick={onRetry} className="mt-4 rounded-lg bg-rose-700 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-800">Try again</button></div>;
}
