import { useState, useEffect } from "react";
import type { HealthResponse, Project } from "../types/api";
import { AnalyticsView } from "../components/dashboard/AnalyticsView";
import { ExecutionHistoryView } from "../components/dashboard/ExecutionHistoryView";
import { TestCasesView } from "../components/dashboard/TestCasesView";
import { TraceabilityView } from "../components/dashboard/TraceabilityView";
import { DefectsView } from "../components/dashboard/DefectsView";
import { ReportsView } from "../components/dashboard/ReportsView";
import { SelfHealingView } from "../components/dashboard/SelfHealingView";

export type DashboardTab =
  | "analytics"
  | "executions"
  | "test_cases"
  | "healing"
  | "traceability"
  | "defects"
  | "reports";

interface DashboardPageProps {
  health: HealthResponse | null;
  projects: Project[];
  isLoadingProjects: boolean;
  selectedProject: Project | null;
  onSelectProject: (project: Project) => void;
  onNavigateToProjects: () => void;
}

export function DashboardPage({
  health,
  projects,
  isLoadingProjects,
  selectedProject,
  onSelectProject,
  onNavigateToProjects,
}: DashboardPageProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("analytics");

  // Auto-select first project if none selected and projects are loaded
  useEffect(() => {
    queueMicrotask(() => {
      if (!selectedProject && projects.length > 0) {
        onSelectProject(projects[0]);
      }
    });
  }, [projects, selectedProject, onSelectProject]);

  if (isLoadingProjects) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-violet-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Loading workspace & projects…</p>
      </div>
    );
  }

  // If no projects exist in the database
  if (projects.length === 0) {
    return (
      <div className="space-y-8">
        <div>
          <p className="text-sm font-semibold text-violet-700">Workspace overview</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Welcome to TestMate AI
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
            Autonomous QA testing and bug analysis platform. To view analytics, execution history, and defect reports,
            create your first project.
          </p>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-xs">
          <span className="text-4xl">📁</span>
          <h3 className="mt-4 text-lg font-bold text-slate-900">No Projects Found</h3>
          <p className="mt-1 text-sm text-slate-500 max-w-md mx-auto">
            Get started by creating a project workspace with software requirements and target URLs.
          </p>
          <button
            onClick={onNavigateToProjects}
            className="mt-6 rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-violet-800 transition"
          >
            Create New Project →
          </button>
        </div>
      </div>
    );
  }

  const currentProject = selectedProject || projects[0];

  const tabs: { id: DashboardTab; label: string; icon: string }[] = [
    { id: "analytics", label: "Analytics", icon: "📊" },
    { id: "executions", label: "Executions", icon: "⚡" },
    { id: "test_cases", label: "Test Cases", icon: "🧪" },
    { id: "healing", label: "Self-Healing", icon: "🩺" },
    { id: "traceability", label: "Traceability", icon: "🔗" },
    { id: "defects", label: "Defects", icon: "🐞" },
    { id: "reports", label: "Executive Report", icon: "📋" },
  ];

  return (
    <div className="space-y-6">
      {/* Top Workspace Header & Project Selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live Database Connected
            </span>
            <span className="text-xs text-slate-400">
              {health?.database.status === "connected" ? "PostgreSQL active" : "Checking database…"}
            </span>
          </div>
          <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            {currentProject.name}
          </h1>
          <p className="text-xs text-slate-500 max-w-xl line-clamp-1">
            {currentProject.description || "QA Testing & Autonomous Verification Workspace"}
          </p>
        </div>

        {/* Project Selector Dropdown */}
        <div className="flex items-center gap-3">
          <label htmlFor="project-selector" className="text-xs font-bold text-slate-500">
            Project:
          </label>
          <select
            id="project-selector"
            value={currentProject.id}
            onChange={(e) => {
              const proj = projects.find((p) => p.id === e.target.value);
              if (proj) onSelectProject(proj);
            }}
            className="rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-800 shadow-2xs hover:border-slate-400 focus:border-violet-600 focus:outline-hidden"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <div className="flex overflow-x-auto border-b border-slate-200 pb-px scrollbar-none">
        <nav className="flex space-x-2" aria-label="Dashboard Tabs">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 whitespace-nowrap rounded-t-xl px-4 py-2.5 text-xs font-bold transition border-b-2 ${
                  isActive
                    ? "border-violet-700 bg-white text-violet-800 shadow-2xs"
                    : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
                }`}
              >
                <span>{tab.icon}</span>
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* View Container */}
      <div className="pt-2">
        {activeTab === "analytics" && (
          <AnalyticsView
            key={`analytics-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
            onNavigateToExecutions={() => setActiveTab("executions")}
            onNavigateToDefects={() => setActiveTab("defects")}
            onNavigateToTraceability={() => setActiveTab("traceability")}
          />
        )}

        {activeTab === "executions" && (
          <ExecutionHistoryView
            key={`executions-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
          />
        )}

        {activeTab === "test_cases" && (
          <TestCasesView
            key={`test_cases-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
            onNavigateToExecutions={() => setActiveTab("executions")}
          />
        )}

        {activeTab === "healing" && (
          <SelfHealingView
            key={`healing-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
          />
        )}

        {activeTab === "traceability" && (
          <TraceabilityView
            key={`traceability-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
            onNavigateToTestCases={() => setActiveTab("test_cases")}
          />
        )}

        {activeTab === "defects" && (
          <DefectsView
            key={`defects-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
          />
        )}

        {activeTab === "reports" && (
          <ReportsView
            key={`reports-${currentProject.id}`}
            projectId={currentProject.id}
            projectName={currentProject.name}
          />
        )}
      </div>
    </div>
  );
}
