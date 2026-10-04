import { EmptyState } from "../components/EmptyState";
import type { Project } from "../types/api";

interface ProjectsPageProps {
  projects: Project[] | null;
  error: string | null;
  isLoading: boolean;
  onRetry: () => void;
}

export function ProjectsPage({ projects, error, isLoading, onRetry }: ProjectsPageProps) {
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-violet-700">Testing workspaces</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">Projects</h1>
          <p className="mt-2 text-sm text-slate-500">Projects will organize requirements, generated tests, executions and findings.</p>
        </div>
        <button type="button" disabled className="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white opacity-50" title="Project creation is intentionally planned for a later phase">New project</button>
      </div>
      {isLoading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-sm">Loading projects…</div>}
      {!isLoading && error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6">
          <h2 className="font-semibold text-rose-900">Projects could not be loaded</h2>
          <p className="mt-2 text-sm text-rose-700">{error}</p>
          <button onClick={onRetry} className="mt-4 rounded-lg bg-rose-700 px-3 py-2 text-sm font-semibold text-white">Try again</button>
        </div>
      )}
      {!isLoading && !error && projects?.length === 0 && <EmptyState title="No projects yet" detail="Apply the PostgreSQL migration, then project creation can be introduced with the next functional workflow." />}
      {!isLoading && !error && projects && projects.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <article key={project.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold text-slate-900">{project.name}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">{project.description || "No description provided."}</p>
              <p className="mt-4 text-xs text-slate-400">Created {new Date(project.created_at).toLocaleDateString()}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
