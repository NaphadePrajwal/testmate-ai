import { useEffect, useState, useMemo, useCallback } from "react";
import { api } from "../../services/api";
import type { ProjectTraceabilityResponse } from "../../types/api";

interface TraceabilityViewProps {
  projectId: string;
  projectName: string;
  onNavigateToTestCases?: () => void;
}

export function TraceabilityView({
  projectId,
  projectName,
  onNavigateToTestCases,
}: TraceabilityViewProps) {
  const [data, setData] = useState<ProjectTraceabilityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [coverageFilter, setCoverageFilter] = useState<"all" | "covered" | "uncovered">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedReqId, setExpandedReqId] = useState<string | null>(null);

  const loadData = useCallback(() => {
    setIsLoading(true);
    setError(null);
    api
      .getProjectTraceability(projectId)
      .then((res) => setData(res))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load traceability matrix."))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadData());
  }, [loadData]);

  const filteredItems = useMemo(() => {
    if (!data) return [];
    return data.items.filter((item) => {
      if (coverageFilter === "covered" && item.coverage_status !== "covered") return false;
      if (coverageFilter === "uncovered" && item.coverage_status !== "uncovered") return false;
      if (
        searchQuery.trim() &&
        !item.requirement_title.toLowerCase().includes(searchQuery.toLowerCase().trim()) &&
        !item.test_cases.some((tc) => tc.title.toLowerCase().includes(searchQuery.toLowerCase().trim()))
      ) {
        return false;
      }
      return true;
    });
  }, [data, coverageFilter, searchQuery]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-violet-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Building requirement-to-test traceability matrix for {projectName}…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <h4 className="font-bold text-base text-rose-900">Traceability Matrix Unavailable</h4>
        <p className="mt-1">{error || "Could not load requirement-to-test traceability data."}</p>
        <button
          onClick={loadData}
          className="mt-4 rounded-xl bg-rose-700 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-800"
        >
          Retry
        </button>
      </div>
    );
  }

  const coveragePercent = Math.round(data.coverage_rate);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            Requirement-to-Test Traceability Matrix
          </h2>
          <p className="text-sm text-slate-500">
            Full end-to-end verification mapping requirements to test cases, executions, and defect intelligence.
          </p>
        </div>
        <button
          onClick={loadData}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition"
        >
          🔄 Refresh Matrix
        </button>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Coverage Rate</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">{coveragePercent}%</span>
            <span className={`text-xs font-bold ${coveragePercent >= 80 ? "text-emerald-600" : coveragePercent >= 50 ? "text-amber-600" : "text-rose-600"}`}>
              {coveragePercent >= 80 ? "Optimal" : coveragePercent >= 50 ? "Moderate" : "Low"}
            </span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full transition-all duration-500 ${
                coveragePercent >= 80 ? "bg-emerald-500" : coveragePercent >= 50 ? "bg-amber-500" : "bg-rose-500"
              }`}
              style={{ width: `${coveragePercent}%` }}
            />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Requirements</p>
          <p className="mt-2 text-3xl font-extrabold text-slate-900">{data.total_requirements}</p>
          <p className="mt-1 text-xs text-slate-400">Scoped to {projectName}</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Covered Requirements</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-emerald-600">{data.covered_requirements}</span>
            <span className="text-xs text-slate-400">/ {data.total_requirements}</span>
          </div>
          <p className="mt-1 text-xs text-emerald-700">Has ≥1 test case</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Uncovered Requirements</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className={`text-3xl font-extrabold ${data.uncovered_requirements > 0 ? "text-amber-600" : "text-slate-900"}`}>
              {data.uncovered_requirements}
            </span>
          </div>
          <p className="mt-1 text-xs text-amber-700">Zero test cases linked</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Unexecuted Test Cases</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className={`text-3xl font-extrabold ${data.cases_without_executions > 0 ? "text-violet-600" : "text-slate-900"}`}>
              {data.cases_without_executions}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">Never executed yet</p>
        </div>
      </div>

      {/* Advisory Banner if uncovered requirements exist */}
      {data.uncovered_requirements > 0 && (
        <div className="flex items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <p className="font-bold">
                {data.uncovered_requirements} requirement{data.uncovered_requirements > 1 ? "s" : ""} have no test coverage.
              </p>
              <p className="text-xs text-amber-700">
                Generate test cases using AI analysis or multi-agent workflows to achieve full requirement coverage.
              </p>
            </div>
          </div>
          {onNavigateToTestCases && (
            <button
              onClick={onNavigateToTestCases}
              className="shrink-0 rounded-xl bg-amber-700 px-3.5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-amber-800 transition"
            >
              Generate Tests
            </button>
          )}
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mr-2">Filter:</span>
          {(["all", "covered", "uncovered"] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setCoverageFilter(filter)}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold capitalize transition ${
                coverageFilter === filter
                  ? "bg-violet-700 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {filter} {filter === "all" ? `(${data.items.length})` : filter === "covered" ? `(${data.covered_requirements})` : `(${data.uncovered_requirements})`}
            </button>
          ))}
        </div>

        <div className="relative min-w-[260px]">
          <input
            type="text"
            placeholder="Search requirements or test cases…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-violet-600 focus:bg-white focus:outline-hidden"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1.5 text-xs text-slate-400 hover:text-slate-600"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Traceability Matrix Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
        {filteredItems.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <span className="text-3xl">🔍</span>
            <p className="mt-2 text-sm font-semibold text-slate-700">No matching requirements</p>
            <p className="text-xs text-slate-500">Try adjusting your coverage filter or search terms.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 font-bold uppercase tracking-wider text-slate-500">
                  <th className="py-3.5 px-4">Requirement</th>
                  <th className="py-3.5 px-4">Req Status</th>
                  <th className="py-3.5 px-4">Coverage Status</th>
                  <th className="py-3.5 px-4">Linked Test Cases</th>
                  <th className="py-3.5 px-4 text-center">Defects</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredItems.map((item) => {
                  const isExpanded = expandedReqId === item.requirement_id;
                  const isCovered = item.coverage_status === "covered";

                  return (
                    <tr key={item.requirement_id} className="hover:bg-slate-50/70 transition">
                      {/* Requirement Name */}
                      <td className="py-3.5 px-4">
                        <div className="max-w-md">
                          <p className="font-bold text-slate-900">{item.requirement_title}</p>
                          <p className="font-mono text-[10px] text-slate-400 mt-0.5">ID: {item.requirement_id.slice(0, 8)}…</p>
                        </div>
                      </td>

                      {/* Requirement Status */}
                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                            item.requirement_status === "approved"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : item.requirement_status === "obsolete"
                              ? "bg-slate-100 text-slate-600 border border-slate-200"
                              : "bg-amber-50 text-amber-700 border border-amber-200"
                          }`}
                        >
                          {item.requirement_status}
                        </span>
                      </td>

                      {/* Coverage Status */}
                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                            isCovered
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          <span>{isCovered ? "✓" : "!"}</span>
                          {isCovered ? "Covered" : "Uncovered"}
                        </span>
                      </td>

                      {/* Test Cases Count & Badges */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-bold text-slate-800">
                            {item.test_cases_count} case{item.test_cases_count !== 1 ? "s" : ""}
                          </span>
                          {item.test_cases.slice(0, 2).map((tc) => (
                            <span
                              key={tc.id}
                              className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium border ${
                                tc.latest_execution_status === "passed"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : tc.latest_execution_status === "failed"
                                  ? "bg-rose-50 text-rose-700 border-rose-200"
                                  : "bg-slate-50 text-slate-600 border-slate-200"
                              }`}
                            >
                              {tc.title.length > 24 ? tc.title.slice(0, 24) + "…" : tc.title}
                            </span>
                          ))}
                          {item.test_cases.length > 2 && (
                            <span className="text-[10px] text-slate-400 font-semibold">
                              +{item.test_cases.length - 2} more
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Defect Count */}
                      <td className="py-3.5 px-4 text-center">
                        {item.defect_count > 0 ? (
                          <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                            🐞 {item.defect_count}
                          </span>
                        ) : (
                          <span className="text-slate-400 font-mono text-[11px]">0</span>
                        )}
                      </td>

                      {/* Action to Expand / Inspect */}
                      <td className="py-3.5 px-4 text-right">
                        {item.test_cases_count > 0 ? (
                          <button
                            onClick={() => setExpandedReqId(isExpanded ? null : item.requirement_id)}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:bg-slate-50 font-semibold text-[11px] transition"
                          >
                            {isExpanded ? "Hide Cases ▲" : "View Cases ▼"}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-400 italic">No cases</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Expanded Requirement Test Cases Details Drawer/List if selected */}
      {expandedReqId && (() => {
        const item = data.items.find((r) => r.requirement_id === expandedReqId);
        if (!item || item.test_cases.length === 0) return null;

        return (
          <div className="rounded-2xl border border-violet-200 bg-violet-50/40 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h4 className="font-bold text-sm text-slate-900">
                  Linked Test Cases for “{item.requirement_title}”
                </h4>
                <p className="text-xs text-slate-500">
                  {item.test_cases.length} test case{item.test_cases.length !== 1 ? "s" : ""} verifying this requirement.
                </p>
              </div>
              <button
                onClick={() => setExpandedReqId(null)}
                className="text-xs font-semibold text-slate-500 hover:text-slate-800"
              >
                ✕ Close
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {item.test_cases.map((tc) => (
                <div
                  key={tc.id}
                  className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs hover:border-violet-300 transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-xs text-slate-900 line-clamp-2">{tc.title}</p>
                    <span
                      className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                        tc.latest_execution_status === "passed"
                          ? "bg-emerald-100 text-emerald-800"
                          : tc.latest_execution_status === "failed"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {tc.latest_execution_status || "Not Run"}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-slate-400">
                    <span className="font-mono">Type: {tc.test_type}</span>
                    <span className="font-medium text-slate-600 capitalize">Review: {tc.review_status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
