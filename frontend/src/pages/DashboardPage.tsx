import type { HealthResponse } from "../types/api";

interface DashboardPageProps {
  health: HealthResponse | null;
  projectCount: number | null;
  isLoadingProjects: boolean;
}

export function DashboardPage({ health, projectCount, isLoadingProjects }: DashboardPageProps) {
  const databaseConnected = health?.database.status === "connected";
  const cards = [
    { label: "Projects", value: isLoadingProjects ? "…" : projectCount ?? "—", note: "Testing workspaces" },
    { label: "API service", value: health?.status === "ok" ? "Online" : "Offline", note: "FastAPI connection" },
    { label: "PostgreSQL", value: databaseConnected ? "Connected" : "Pending", note: "Data persistence" }
  ];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold text-violet-700">Workspace overview</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Build reliable software with confidence.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">TestMate AI is ready for its requirement analysis, test generation and execution capabilities. Start by connecting PostgreSQL and creating a testing project.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <article key={card.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">{card.label}</p>
            <p className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{card.value}</p>
            <p className="mt-1 text-xs text-slate-400">{card.note}</p>
          </article>
        ))}
      </div>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900">Foundation readiness</h2>
        <div className="mt-5 space-y-4">
          <ReadinessRow label="FastAPI service and OpenAPI documentation" complete={health?.status === "ok"} />
          <ReadinessRow label="PostgreSQL database connection" complete={databaseConnected} />
          <ReadinessRow label="Projects API and dashboard integration" complete={health?.status === "ok"} />
        </div>
      </section>
    </div>
  );
}

function ReadinessRow({ label, complete }: { label: string; complete: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-50 px-4 py-3">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${complete ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{complete ? "Ready" : "Needs setup"}</span>
    </div>
  );
}
