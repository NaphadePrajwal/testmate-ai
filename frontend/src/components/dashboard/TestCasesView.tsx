import { useCallback, useEffect, useState } from "react";
import { api } from "../../services/api";
import type { ReviewStatus, TestCase, TestExecution, HealingProposal } from "../../types/api";

interface TestCasesViewProps {
  projectId: string;
  projectName: string;
  onNavigateToExecutions?: () => void;
}

export function TestCasesView({ projectId, projectName, onNavigateToExecutions }: TestCasesViewProps) {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(20);
  const [reviewFilter, setReviewFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Modal State
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [history, setHistory] = useState<TestExecution[]>([]);
  const [healingHistory, setHealingHistory] = useState<HealingProposal[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [execMessage, setExecMessage] = useState<string | null>(null);

  const loadTestCases = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getRequirementTestCases(
        projectId,
        "", // Note: we can list project test cases via direct request or filter
        limit,
        offset,
        reviewFilter === "all" ? undefined : (reviewFilter as ReviewStatus)
      );
      let items = res.items;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        items = items.filter(
          (tc) =>
            tc.title.toLowerCase().includes(q) ||
            (tc.description || "").toLowerCase().includes(q) ||
            tc.id.toLowerCase().includes(q)
        );
      }
      setTestCases(items);
      setTotal(res.total);
    } catch {
      // Fallback: list test cases from test-cases router directly
      try {
        const directRes = await fetch(
          `http://localhost:8000/api/v1/projects/${projectId}/test-cases?limit=${limit}&offset=${offset}${
            reviewFilter !== "all" ? `&review_status=${reviewFilter}` : ""
          }`
        );
        const data = await directRes.json();
        let items = data.items || [];
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          items = items.filter(
            (tc: TestCase) =>
              tc.title.toLowerCase().includes(q) ||
              (tc.description || "").toLowerCase().includes(q) ||
              tc.id.toLowerCase().includes(q)
          );
        }
        setTestCases(items);
        setTotal(data.total || 0);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load test cases.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [projectId, limit, offset, reviewFilter, searchQuery]);

  useEffect(() => {
    queueMicrotask(() => void loadTestCases());
  }, [loadTestCases]);

  async function openTestCaseDetail(tc: TestCase) {
    setSelectedTestCase(tc);
    setIsLoadingHistory(true);
    setExecMessage(null);
    try {
      const [hist, healRes] = await Promise.all([
        api.getTestCaseHistory(projectId, tc.id, 10, 0),
        api.getTestCaseHealingHistory(projectId, tc.id).catch(() => ({ items: [], total: 0, limit: 10, offset: 0 })),
      ]);
      setHistory(hist.items);
      setHealingHistory(healRes.items || []);
    } catch (e) {
      console.error("Failed to load test case execution history", e);
    } finally {
      setIsLoadingHistory(false);
    }
  }

  async function handleExecuteTestCase(tc: TestCase) {
    setIsExecuting(true);
    setExecMessage(null);
    try {
      const result = await api.executeTestCase(projectId, tc.id, {
        executor: tc.test_type === "web" ? "playwright" : "httpx",
      });
      setExecMessage(`Execution completed: ${result.status.toUpperCase()}`);
      // Refresh history
      const hist = await api.getTestCaseHistory(projectId, tc.id, 10, 0);
      setHistory(hist.items);
    } catch (err) {
      setExecMessage(err instanceof Error ? err.message : "Execution failed.");
    } finally {
      setIsExecuting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-violet-700">
            <span>Test Specifications</span>
            <span>•</span>
            <span className="text-slate-500">{projectName}</span>
          </div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">Project Test Cases</h2>
          <p className="mt-1 text-xs text-slate-500">
            Structured manual, API, and autonomous browser test specifications.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadTestCases()}
          className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex items-center gap-1.5">
          {["all", "approved", "pending", "rejected"].map((rev) => (
            <button
              key={rev}
              type="button"
              onClick={() => {
                setReviewFilter(rev);
                setOffset(0);
              }}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition ${
                reviewFilter === rev
                  ? "bg-violet-700 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {rev}
            </button>
          ))}
        </div>

        <div className="relative min-w-[240px]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search test cases…"
            className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3.5 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-violet-600 focus:bg-white focus:outline-hidden"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1.5 text-xs text-slate-400 hover:text-slate-600"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Test Cases Table */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-500">
          <span className="text-2xl animate-spin text-violet-600 mb-2">🌀</span>
          <p className="text-xs">Loading test cases…</p>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
          <p className="font-bold">Error loading test cases</p>
          <p className="mt-1">{error}</p>
        </div>
      ) : testCases.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-xs text-slate-500 shadow-xs">
          <p className="text-sm font-semibold text-slate-800 mb-1">No test cases found</p>
          <p>
            {reviewFilter !== "all"
              ? `No test cases match review status '${reviewFilter}'.`
              : "Generate or author test cases from requirements to populate this catalog."}
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider font-semibold text-[11px]">
                <tr>
                  <th className="px-4 py-3">Review Status</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {testCases.map((tc) => (
                  <tr key={tc.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          tc.review_status === "approved"
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            : tc.review_status === "rejected"
                            ? "bg-rose-100 text-rose-800 border border-rose-200"
                            : "bg-amber-100 text-amber-800 border border-amber-200"
                        }`}
                      >
                        {tc.review_status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-900 max-w-[280px] truncate">
                      {tc.title}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-700">
                        {tc.test_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`font-semibold ${
                          tc.priority === "critical" || tc.priority === "high"
                            ? "text-rose-600"
                            : "text-slate-600"
                        }`}
                      >
                        {tc.priority.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-500">v{tc.version}</td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {new Date(tc.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void openTestCaseDetail(tc)}
                        className="rounded-lg bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700 hover:bg-violet-100 transition"
                      >
                        View Details →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
            <span>
              Showing {testCases.length} of {total} test cases
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Test Case Detail Slide-over / Modal */}
      {selectedTestCase && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4"
          onClick={() => setSelectedTestCase(null)}
        >
          <div
            className="relative max-w-3xl w-full max-h-[90vh] bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div>
                <span className="font-mono text-[10px] text-slate-500">ID: {selectedTestCase.id}</span>
                <h3 className="font-bold text-base text-slate-900">{selectedTestCase.title}</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedTestCase(null)}
                className="h-7 w-7 rounded-lg bg-slate-200 text-slate-600 hover:bg-slate-300 flex items-center justify-center text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {/* Content */}
            <div className="p-6 overflow-y-auto space-y-5 text-xs">
              {/* Metadata Badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-violet-100 text-violet-800 px-2.5 py-0.5 font-bold uppercase text-[10px]">
                  {selectedTestCase.test_type}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 font-bold uppercase text-[10px] ${
                    selectedTestCase.review_status === "approved"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {selectedTestCase.review_status}
                </span>
                <span className="rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 font-mono text-[10px]">
                  Priority: {selectedTestCase.priority.toUpperCase()}
                </span>
              </div>

              {/* Description */}
              <div>
                <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[11px] mb-1">Description</h4>
                <p className="text-slate-600 leading-relaxed">{selectedTestCase.description}</p>
              </div>

              {/* Preconditions */}
              {selectedTestCase.preconditions.length > 0 && (
                <div>
                  <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[11px] mb-1">Preconditions</h4>
                  <ul className="list-disc pl-5 space-y-1 text-slate-600">
                    {selectedTestCase.preconditions.map((pre, i) => (
                      <li key={i}>{pre}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Steps */}
              <div>
                <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[11px] mb-2">
                  Test Steps ({selectedTestCase.steps.length})
                </h4>
                <div className="space-y-1.5">
                  {selectedTestCase.steps.map((st, i) => (
                    <div key={i} className="flex items-start gap-2.5 p-2 rounded-lg bg-slate-50 border border-slate-100">
                      <span className="font-mono text-slate-400 font-bold text-[10px]">#{i + 1}</span>
                      <div className="flex-1">
                        <span className="font-semibold text-slate-800">{st.action}</span>
                        {st.expected_result && (
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            <span className="font-medium text-slate-400">Expects:</span> {st.expected_result}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Expected Result */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <span className="font-bold text-[11px] uppercase tracking-wider text-slate-700">Overall Expected Outcome</span>
                <p className="mt-1 text-slate-700">{selectedTestCase.expected_result}</p>
              </div>

              {/* Action Bar (Trigger Execution if Approved) */}
              <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                <div>
                  {execMessage && (
                    <p className="text-xs font-semibold text-violet-700 animate-pulse">{execMessage}</p>
                  )}
                </div>
                {selectedTestCase.review_status === "approved" && (
                  <button
                    type="button"
                    onClick={() => void handleExecuteTestCase(selectedTestCase)}
                    disabled={isExecuting}
                    className="rounded-xl bg-violet-700 px-4 py-2 text-xs font-bold text-white hover:bg-violet-800 disabled:opacity-50"
                  >
                    {isExecuting ? "Executing in Playwright…" : "▶ Execute Test Case"}
                  </button>
                )}
              </div>

              {/* Historical Executions */}
              <div className="pt-4 border-t border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-bold text-slate-900 text-sm">Historical Executions</h4>
                  {onNavigateToExecutions && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedTestCase(null);
                        onNavigateToExecutions();
                      }}
                      className="text-xs font-semibold text-violet-700 hover:text-violet-900 transition"
                    >
                      View All in Executions Tab →
                    </button>
                  )}
                </div>
                {isLoadingHistory ? (
                  <p className="text-slate-400 italic">Loading run history…</p>
                ) : history.length === 0 ? (
                  <p className="text-slate-400 italic">No executions have been run for this test case yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {history.map((h) => (
                      <div
                        key={h.id}
                        className="flex items-center justify-between p-2 rounded-lg border border-slate-100 bg-slate-50"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`rounded px-1.5 py-0.5 font-bold text-[9px] uppercase ${
                              h.status === "passed"
                                ? "bg-emerald-100 text-emerald-800"
                                : h.status === "failed"
                                ? "bg-rose-100 text-rose-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {h.status}
                          </span>
                          <span className="font-mono text-slate-600 text-[10px]">{h.id.slice(0, 8)}…</span>
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {new Date(h.created_at).toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Self-Healing History */}
              {healingHistory.length > 0 && (
                <div className="pt-4 border-t border-slate-200">
                  <h4 className="font-bold text-slate-900 text-sm mb-2 flex items-center gap-1.5">
                    <span>🩺</span> Self-Healing History ({healingHistory.length})
                  </h4>
                  <div className="space-y-1.5">
                    {healingHistory.map((hh) => (
                      <div
                        key={hh.id}
                        className="flex items-center justify-between p-2 rounded-lg border border-slate-200 bg-slate-50 text-[11px]"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`rounded px-1.5 py-0.5 font-bold text-[9px] uppercase ${
                              hh.status === "healed"
                                ? "bg-emerald-100 text-emerald-800"
                                : hh.status === "failed"
                                ? "bg-rose-100 text-rose-800"
                                : hh.status === "awaiting_approval"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {hh.status}
                          </span>
                          <span className="text-slate-700">Step {hh.failed_step_index + 1} locator repair</span>
                        </div>
                        <span className="font-mono text-slate-400 text-[10px]">
                          {new Date(hh.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
