import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { ProjectAnalyticsResponse } from "../../types/api";

interface AnalyticsViewProps {
  projectId: string;
  projectName: string;
  onNavigateToExecutions?: () => void;
  onNavigateToDefects?: () => void;
  onNavigateToTraceability?: () => void;
}

export function AnalyticsView({
  projectId,
  projectName,
  onNavigateToExecutions,
  onNavigateToDefects,
  onNavigateToTraceability,
}: AnalyticsViewProps) {
  const [analytics, setAnalytics] = useState<ProjectAnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;
    queueMicrotask(() => {
      if (!isCurrent) return;
      setIsLoading(true);
      setError(null);

      api
        .getProjectAnalytics(projectId)
        .then((data) => {
          if (isCurrent) setAnalytics(data);
        })
        .catch((err) => {
          if (isCurrent) {
            setError(err instanceof Error ? err.message : "Failed to load project analytics.");
          }
        })
        .finally(() => {
          if (isCurrent) setIsLoading(false);
        });
    });

    return () => {
      isCurrent = false;
    };
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-violet-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Aggregating real-time testing analytics for {projectName}…</p>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <h4 className="font-bold text-base text-rose-900">Analytics Unavailable</h4>
        <p className="mt-1">{error || "Could not retrieve analytics data."}</p>
        <button
          type="button"
          onClick={() => {
            setIsLoading(true);
            setError(null);
            api.getProjectAnalytics(projectId).then(setAnalytics).catch((e) => setError(String(e))).finally(() => setIsLoading(false));
          }}
          className="mt-4 rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // Calculate chart max for trends
  const maxTrendTotal = Math.max(1, ...analytics.execution_trends.map((t) => t.total));

  return (
    <div className="space-y-8">
      {/* Top Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-violet-700">
          <span>Project Analytics & Metrics</span>
          <span>•</span>
          <span className="text-slate-500">{projectName}</span>
        </div>
        <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Testing Health & Performance Overview
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          Real-time aggregations calculated from persisted PostgreSQL execution records.
        </p>
      </div>

      {/* KPI Metrics Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Requirements</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{analytics.total_requirements}</p>
          <p className="mt-1 text-[11px] text-slate-400">Total specifications</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Test Cases</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{analytics.total_test_cases}</p>
          <p className="mt-1 text-[11px] text-slate-400">Authored & AI synthesized</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Total Executions</p>
          <p className="mt-2 text-2xl font-bold text-violet-700">{analytics.total_test_executions}</p>
          <p className="mt-1 text-[11px] text-slate-400">
            {analytics.passed_executions} passed / {analytics.failed_executions} failed
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Pass Rate</p>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span
              className={`text-2xl font-bold ${
                analytics.execution_pass_rate >= 80
                  ? "text-emerald-600"
                  : analytics.execution_pass_rate >= 50
                  ? "text-amber-600"
                  : "text-rose-600"
              }`}
            >
              {analytics.execution_pass_rate}%
            </span>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">Of completed executions</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Requirement Coverage</p>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span
              className={`text-2xl font-bold ${
                analytics.requirement_coverage_rate >= 80
                  ? "text-emerald-600"
                  : analytics.requirement_coverage_rate >= 50
                  ? "text-amber-600"
                  : "text-rose-600"
              }`}
            >
              {analytics.requirement_coverage_rate}%
            </span>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">Linked to ≥1 test case</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-slate-500">Open Defects</p>
          <p className="mt-2 text-2xl font-bold text-rose-600">{analytics.open_defects}</p>
          <p className="mt-1 text-[11px] text-rose-500 font-medium">
            {analytics.critical_defects} crit • {analytics.high_defects} high
          </p>
        </div>
      </div>

      {/* Visual Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 14-Day Execution Trends Bar/Line Chart */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-slate-900 text-sm">Execution Activity (Last 14 Days)</h3>
              <p className="text-xs text-slate-500">Chronological daily volume of test executions</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-700 font-medium">
                <span className="h-2.5 w-2.5 rounded-xs bg-emerald-500" /> Passed
              </span>
              <span className="flex items-center gap-1.5 text-rose-700 font-medium">
                <span className="h-2.5 w-2.5 rounded-xs bg-rose-500" /> Failed
              </span>
            </div>
          </div>

          {analytics.total_test_executions === 0 ? (
            <div className="h-48 flex items-center justify-center text-xs text-slate-400 italic">
              No executions recorded in the last 14 days.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="h-48 flex items-end gap-1.5 pt-6 pb-2 border-b border-slate-100">
                {analytics.execution_trends.map((trend) => {
                  const passedHeight = (trend.passed / maxTrendTotal) * 100;
                  const failedHeight = (trend.failed / maxTrendTotal) * 100;
                  const dateLabel = trend.date.slice(5); // MM-DD

                  return (
                    <div
                      key={trend.date}
                      className="flex-1 flex flex-col items-center justify-end h-full group relative"
                    >
                      {/* Tooltip on hover */}
                      <div className="absolute -top-10 hidden group-hover:flex flex-col items-center z-10 pointer-events-none">
                        <div className="bg-slate-900 text-white text-[10px] px-2 py-1 rounded shadow-lg whitespace-nowrap">
                          {trend.date}: {trend.total} runs ({trend.passed} passed, {trend.failed} failed)
                        </div>
                      </div>

                      {/* Stacked bars */}
                      <div className="w-full flex flex-col justify-end items-center max-w-[20px] rounded-t overflow-hidden bg-slate-100 h-full">
                        <div
                          style={{ height: `${failedHeight}%` }}
                          className="w-full bg-rose-500 transition-all duration-300"
                        />
                        <div
                          style={{ height: `${passedHeight}%` }}
                          className="w-full bg-emerald-500 transition-all duration-300"
                        />
                      </div>
                      <span className="mt-1 text-[9px] text-slate-400 tracking-tighter truncate w-full text-center">
                        {dateLabel}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Execution Distribution & Defect Severity Breakdown */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs flex flex-col justify-between">
          <h3 className="font-bold text-slate-900 text-sm mb-4">Execution Status & Defect Severity</h3>

          <div className="grid grid-cols-2 gap-6">
            {/* Status Breakdown Meter */}
            <div className="space-y-3">
              <p className="text-xs font-semibold text-slate-600">Executions Status</p>
              {analytics.total_test_executions === 0 ? (
                <p className="text-xs text-slate-400 italic">No executions logged.</p>
              ) : (
                <div className="space-y-2 text-xs">
                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-emerald-700 font-semibold">Passed</span>
                      <span className="text-slate-600 font-mono">{analytics.passed_executions}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.passed_executions / analytics.total_test_executions) * 100}%`,
                        }}
                        className="h-full bg-emerald-500"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-rose-700 font-semibold">Failed</span>
                      <span className="text-slate-600 font-mono">{analytics.failed_executions}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.failed_executions / analytics.total_test_executions) * 100}%`,
                        }}
                        className="h-full bg-rose-500"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-amber-700 font-semibold">Errors / Infra</span>
                      <span className="text-slate-600 font-mono">{analytics.error_executions}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.error_executions / analytics.total_test_executions) * 100}%`,
                        }}
                        className="h-full bg-amber-500"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Defect Severity Breakdown */}
            <div className="space-y-3">
              <p className="text-xs font-semibold text-slate-600">Defect Severities</p>
              {analytics.total_defects === 0 ? (
                <p className="text-xs text-slate-400 italic">No open defects recorded.</p>
              ) : (
                <div className="space-y-2 text-xs">
                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-rose-800 font-semibold">Critical</span>
                      <span className="text-slate-600 font-mono">{analytics.critical_defects}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.critical_defects / Math.max(1, analytics.total_defects)) * 100}%`,
                        }}
                        className="h-full bg-rose-700"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-rose-600 font-semibold">High</span>
                      <span className="text-slate-600 font-mono">{analytics.high_defects}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.high_defects / Math.max(1, analytics.total_defects)) * 100}%`,
                        }}
                        className="h-full bg-rose-500"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-amber-600 font-semibold">Medium</span>
                      <span className="text-slate-600 font-mono">{analytics.medium_defects}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        style={{
                          width: `${(analytics.medium_defects / Math.max(1, analytics.total_defects)) * 100}%`,
                        }}
                        className="h-full bg-amber-500"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <button
              type="button"
              onClick={onNavigateToTraceability}
              className="text-violet-600 hover:text-violet-800 font-medium"
            >
              Inspect Traceability Matrix →
            </button>
            <button
              type="button"
              onClick={onNavigateToDefects}
              className="text-rose-600 hover:text-rose-800 font-medium"
            >
              View All Defects ({analytics.total_defects}) →
            </button>
          </div>
        </div>
      </div>

      {/* Recent Execution Activity */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-bold text-slate-900 text-sm">Recent Test Executions</h3>
            <p className="text-xs text-slate-500">Latest executed test cases in this project</p>
          </div>
          {onNavigateToExecutions && (
            <button
              type="button"
              onClick={onNavigateToExecutions}
              className="text-xs font-semibold text-violet-700 hover:text-violet-900"
            >
              View Execution History →
            </button>
          )}
        </div>

        {analytics.recent_executions.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-4">No recent executions recorded for this project.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {analytics.recent_executions.map((item) => (
              <div key={item.id} className="py-3 flex items-center justify-between text-xs">
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      item.status === "passed"
                        ? "bg-emerald-100 text-emerald-800"
                        : item.status === "failed"
                        ? "bg-rose-100 text-rose-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {item.status.toUpperCase()}
                  </span>
                  <div>
                    <span className="font-semibold text-slate-900">{item.test_case_title}</span>
                    <span className="ml-2 font-mono text-[10px] text-slate-400">ID: {item.id.slice(0, 8)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-slate-500 text-[11px]">
                  {item.duration_ms != null && <span>{(item.duration_ms / 1000).toFixed(2)}s</span>}
                  <span>{new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
