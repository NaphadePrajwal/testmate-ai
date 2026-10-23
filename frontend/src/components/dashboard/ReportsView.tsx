import { useEffect, useState, useCallback } from "react";
import { api } from "../../services/api";
import type { ProjectReportResponse } from "../../types/api";

interface ReportsViewProps {
  projectId: string;
  projectName: string;
}

export function ReportsView({ projectId, projectName }: ReportsViewProps) {
  const [report, setReport] = useState<ProjectReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = useCallback(() => {
    setIsLoading(true);
    setError(null);
    api
      .getProjectReport(projectId)
      .then((res) => setReport(res))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load project report."))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadReport());
  }, [loadReport]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-violet-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Generating executive QA & quality report for {projectName}…</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <h4 className="font-bold text-base text-rose-900">Report Generation Failed</h4>
        <p className="mt-1">{error || "Could not generate project report."}</p>
        <button
          onClick={loadReport}
          className="mt-4 rounded-xl bg-rose-700 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-800"
        >
          Retry
        </button>
      </div>
    );
  }

  const { analytics, traceability_summary, quality_score } = report;
  const passRate = Math.round(analytics.execution_pass_rate);
  const coverageRate = Math.round(analytics.requirement_coverage_rate);

  // Determine quality tier
  const getQualityTier = (score: number) => {
    if (score >= 80) return { label: "Production Ready", color: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200" };
    if (score >= 60) return { label: "Stable / Release Candidate", color: "text-violet-700", bg: "bg-violet-50", border: "border-violet-200" };
    if (score >= 40) return { label: "Needs Hardening", color: "text-amber-700", bg: "bg-amber-50", border: "border-amber-200" };
    return { label: "High Risk / Critical Bugs", color: "text-rose-700", bg: "bg-rose-50", border: "border-rose-200" };
  };

  const qualityTier = getQualityTier(quality_score);

  return (
    <div className="space-y-8 print:p-0 print:space-y-6">
      {/* Action Bar (hidden when printing) */}
      <div className="flex flex-wrap items-center justify-between gap-4 print:hidden">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Project Quality & Executive Report</h2>
          <p className="text-sm text-slate-500">
            Comprehensive audit report covering testing velocity, requirement traceability, and defect severity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadReport}
            className="rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition"
          >
            🔄 Refresh Report
          </button>
          <button
            onClick={() => window.print()}
            className="rounded-xl bg-violet-700 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-violet-800 transition flex items-center gap-1.5"
          >
            <span>🖨️</span> Print / Export PDF
          </button>
        </div>
      </div>

      {/* Printable Report Header */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs print:border-none print:p-0 print:shadow-none">
        <div className="flex flex-wrap items-start justify-between gap-6 border-b border-slate-100 pb-6">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-violet-700 px-2.5 py-1 text-xs font-extrabold uppercase tracking-widest text-white">
                TestMate AI
              </span>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Executive Report</span>
            </div>
            <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900">{report.project_name}</h1>
            <p className="mt-1 text-sm text-slate-600 max-w-2xl">
              {report.project_description || "Autonomous QA test generation, browser execution, and bug triage audit."}
            </p>
          </div>

          <div className="text-right text-xs text-slate-500">
            <p>
              Report Generated:{" "}
              <strong className="text-slate-800">
                {new Date().toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </strong>
            </p>
            <p className="mt-1 font-mono text-[11px] text-slate-400">Project ID: {report.project_id}</p>
          </div>
        </div>

        {/* Quality Score Hero Gauge & Key Stats */}
        <div className="mt-8 grid gap-6 md:grid-cols-3">
          {/* Quality Score Box */}
          <div className={`flex flex-col items-center justify-center rounded-2xl border p-6 text-center ${qualityTier.bg} ${qualityTier.border}`}>
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Software Quality Score</p>
            <div className="relative mt-4 flex items-center justify-center">
              <div className="text-5xl font-black text-slate-900">{quality_score}</div>
              <span className="text-xl font-bold text-slate-400">/100</span>
            </div>
            <div className={`mt-3 inline-block rounded-full px-3 py-1 text-xs font-extrabold uppercase tracking-wider ${qualityTier.color} bg-white shadow-2xs`}>
              {qualityTier.label}
            </div>
            <p className="mt-3 text-[11px] text-slate-600 max-w-[200px]">
              Computed from pass rate ({passRate}%), requirement coverage ({coverageRate}%), and open defect penalty.
            </p>
          </div>

          {/* Test Execution Summary */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-6">
            <h3 className="font-bold text-sm text-slate-900">Execution Velocity & Health</h3>
            <div className="mt-4 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Total Browser Executions:</span>
                <span className="font-bold text-slate-900">{analytics.total_test_executions}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Pass Rate:</span>
                <span className="font-bold text-emerald-700">{passRate}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Passed Runs:</span>
                <span className="font-semibold text-emerald-600">{analytics.passed_executions}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Failed Runs:</span>
                <span className="font-semibold text-rose-600">{analytics.failed_executions}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Execution Errors:</span>
                <span className="font-semibold text-amber-600">{analytics.error_executions}</span>
              </div>
            </div>
          </div>

          {/* Traceability & Defect Summary */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-6">
            <h3 className="font-bold text-sm text-slate-900">Traceability & Defect Exposure</h3>
            <div className="mt-4 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Total Requirements:</span>
                <span className="font-bold text-slate-900">{analytics.total_requirements}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Requirement Coverage:</span>
                <span className="font-bold text-violet-700">{coverageRate}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Total Test Cases:</span>
                <span className="font-bold text-slate-900">{analytics.total_test_cases}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Open Defects:</span>
                <span className={`font-bold ${analytics.open_defects > 0 ? "text-rose-600" : "text-emerald-600"}`}>
                  {analytics.open_defects}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Critical / High Severity:</span>
                <span className={`font-bold ${analytics.critical_defects > 0 ? "text-rose-700" : "text-slate-900"}`}>
                  {analytics.critical_defects + analytics.high_defects}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Traceability Matrix Summary Section */}
        <div className="mt-8">
          <h3 className="text-base font-bold text-slate-900 border-b border-slate-200 pb-2">
            Requirement Coverage & Traceability Audit
          </h3>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-semibold text-slate-500">Covered Requirements</p>
              <p className="mt-1 text-2xl font-bold text-emerald-600">{traceability_summary.covered_requirements}</p>
              <p className="text-[10px] text-slate-400">Has validated tests</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-semibold text-slate-500">Uncovered Requirements</p>
              <p className="mt-1 text-2xl font-bold text-amber-600">{traceability_summary.uncovered_requirements}</p>
              <p className="text-[10px] text-slate-400">Zero test cases linked</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-semibold text-slate-500">Requirements Without Cases</p>
              <p className="mt-1 text-2xl font-bold text-slate-800">{traceability_summary.requirements_without_cases}</p>
              <p className="text-[10px] text-slate-400">Needs generation</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-[11px] font-semibold text-slate-500">Unexecuted Test Cases</p>
              <p className="mt-1 text-2xl font-bold text-violet-700">{traceability_summary.cases_without_executions}</p>
              <p className="text-[10px] text-slate-400">Awaiting execution</p>
            </div>
          </div>
        </div>

        {/* Defect Severity & Status Breakdown */}
        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          {/* Defect by Severity */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h4 className="font-bold text-sm text-slate-900 mb-3">Defects by Severity</h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between rounded-lg bg-rose-50 px-3 py-2 text-rose-900 font-semibold">
                <span>Critical Severity (Blockers)</span>
                <span>{analytics.critical_defects}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-orange-50 px-3 py-2 text-orange-900 font-semibold">
                <span>High Severity</span>
                <span>{analytics.high_defects}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-amber-50 px-3 py-2 text-amber-900 font-semibold">
                <span>Medium Severity</span>
                <span>{analytics.medium_defects}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-slate-700 font-semibold">
                <span>Low Severity</span>
                <span>{analytics.low_defects}</span>
              </div>
            </div>
          </div>

          {/* Defect by Status */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h4 className="font-bold text-sm text-slate-900 mb-3">Defects by Lifecycle Status</h4>
            <div className="space-y-2 text-xs">
              {Object.entries(analytics.defects_by_status).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-slate-800">
                  <span className="font-semibold capitalize">{status}</span>
                  <span className="font-bold">{count}</span>
                </div>
              ))}
              {Object.keys(analytics.defects_by_status).length === 0 && (
                <p className="text-slate-400 italic">No defects recorded.</p>
              )}
            </div>
          </div>
        </div>

        {/* Sign-off & Audit Stamp */}
        <div className="mt-12 rounded-2xl border border-slate-200 bg-slate-50 p-6 text-xs text-slate-500">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="font-bold text-slate-800">Automated Quality Assurance Assurance Sign-Off</p>
              <p className="mt-0.5">
                Verified by TestMate AI Multi-Agent Orchestration & Playwright Autonomous Engine.
              </p>
            </div>
            <div className="text-right">
              <span className="font-mono text-[10px] text-slate-400">TESTMATE-PHASE-11-AUDIT-VERIFIED</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
