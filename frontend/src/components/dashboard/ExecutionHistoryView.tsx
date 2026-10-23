import { useCallback, useEffect, useState } from "react";
import { api } from "../../services/api";
import type { ExecutionDetailResponse, ExecutionStatus, TestExecution, HealingProposal } from "../../types/api";

interface ExecutionHistoryViewProps {
  projectId: string;
  projectName: string;
}

export function ExecutionHistoryView({ projectId, projectName }: ExecutionHistoryViewProps) {
  const [executions, setExecutions] = useState<TestExecution[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(15);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Modal state
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null);
  const [execDetail, setExecDetail] = useState<ExecutionDetailResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [zoomScreenshotUrl, setZoomScreenshotUrl] = useState<string | null>(null);
  const [healingProposals, setHealingProposals] = useState<HealingProposal[]>([]);

  const loadExecutions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const statusParam = statusFilter === "all" ? undefined : (statusFilter as ExecutionStatus);
      const res = await api.getExecutions(projectId, undefined, limit, offset);
      // Client-side status filter if API doesn't filter directly on getExecutions, or filter in place
      let filtered = res.items;
      if (statusParam) {
        filtered = filtered.filter((e) => e.status === statusParam);
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter(
          (e) =>
            e.id.toLowerCase().includes(q) ||
            e.test_case_id.toLowerCase().includes(q) ||
            (e.executor && e.executor.toLowerCase().includes(q))
        );
      }
      setExecutions(filtered);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load execution history.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId, limit, offset, statusFilter, searchQuery]);

  useEffect(() => {
    queueMicrotask(() => void loadExecutions());
  }, [loadExecutions]);

  async function openExecutionDetail(execId: string) {
    setSelectedExecId(execId);
    setIsLoadingDetail(true);
    try {
      const [detail, healingRes] = await Promise.all([
        api.getExecutionDetail(projectId, execId),
        api.getExecutionHealingProposals(projectId, execId).catch(() => ({ items: [], total: 0, limit: 10, offset: 0 })),
      ]);
      setExecDetail(detail);
      setHealingProposals(healingRes.items || []);
    } catch (err) {
      console.error("Failed to load execution detail", err);
    } finally {
      setIsLoadingDetail(false);
    }
  }

  function closeDetailModal() {
    setSelectedExecId(null);
    setExecDetail(null);
    setZoomScreenshotUrl(null);
    setHealingProposals([]);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-violet-700">
            <span>Execution Audit Log</span>
            <span>•</span>
            <span className="text-slate-500">{projectName}</span>
          </div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">Test Execution History</h2>
          <p className="mt-1 text-xs text-slate-500">
            Chronological record of autonomous browser and API test runs with captured evidence.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadExecutions()}
          className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        {/* Status Filters */}
        <div className="flex flex-wrap items-center gap-1.5">
          {["all", "passed", "failed", "error"].map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => {
                setStatusFilter(st);
                setOffset(0);
              }}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition ${
                statusFilter === st
                  ? "bg-violet-700 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative min-w-[240px]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ID or executor…"
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

      {/* Execution Table */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-500">
          <span className="text-2xl animate-spin text-violet-600 mb-2">🌀</span>
          <p className="text-xs">Loading execution records…</p>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
          <p className="font-bold">Error loading executions</p>
          <p className="mt-1">{error}</p>
        </div>
      ) : executions.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-xs text-slate-500 shadow-xs">
          <p className="text-sm font-semibold text-slate-800 mb-1">No execution history found</p>
          <p>
            {statusFilter !== "all"
              ? `No executions match status '${statusFilter}'.`
              : "Execute test cases to populate the historical audit log."}
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider font-semibold text-[11px]">
                <tr>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Execution ID</th>
                  <th className="px-4 py-3">Test Case ID</th>
                  <th className="px-4 py-3">Executor</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3">Executed At</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {executions.map((exec) => (
                  <tr key={exec.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          exec.status === "passed"
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            : exec.status === "failed"
                            ? "bg-rose-100 text-rose-800 border border-rose-200"
                            : "bg-amber-100 text-amber-800 border border-amber-200"
                        }`}
                      >
                        {exec.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold text-slate-900">
                      {exec.id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 truncate max-w-[160px]">
                      {exec.test_case_id}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px]">
                        {exec.executor || "Playwright"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-500">
                      {exec.summary?.duration_ms
                        ? `${(exec.summary.duration_ms / 1000).toFixed(2)}s`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {new Date(exec.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void openExecutionDetail(exec.id)}
                        className="rounded-lg bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700 hover:bg-violet-100 transition"
                      >
                        Inspect Details →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
            <span>
              Showing {executions.length} of {total} records
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

      {/* Execution Inspection Modal */}
      {selectedExecId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4"
          onClick={closeDetailModal}
        >
          <div
            className="relative max-w-4xl w-full max-h-[90vh] bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-bold text-slate-900">
                  Execution: {selectedExecId}
                </span>
                {execDetail && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      execDetail.status === "passed"
                        ? "bg-emerald-100 text-emerald-800"
                        : execDetail.status === "failed"
                        ? "bg-rose-100 text-rose-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {execDetail.status.toUpperCase()}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={closeDetailModal}
                className="h-7 w-7 rounded-lg bg-slate-200 text-slate-600 hover:bg-slate-300 flex items-center justify-center text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto space-y-6 text-xs">
              {isLoadingDetail || !execDetail ? (
                <div className="flex items-center justify-center py-12 text-slate-500 gap-2">
                  <span className="animate-spin text-violet-600">🌀</span>
                  <span>Loading full execution details, steps, and evidence…</span>
                </div>
              ) : (
                <>
                  {/* Summary Bar */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Total Steps</span>
                      <p className="text-base font-bold text-slate-900">{execDetail.summary?.total_steps ?? "—"}</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Steps Passed</span>
                      <p className="text-base font-bold text-emerald-600">{execDetail.summary?.passed_steps ?? "—"}</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Steps Failed</span>
                      <p className="text-base font-bold text-rose-600">{execDetail.summary?.failed_steps ?? "—"}</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Duration</span>
                      <p className="text-base font-mono font-bold text-slate-900">
                        {execDetail.summary?.duration_ms
                          ? `${(execDetail.summary.duration_ms / 1000).toFixed(2)}s`
                          : "—"}
                      </p>
                    </div>
                  </div>

                  {/* Failure Reason */}
                  {execDetail.error_message && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-rose-900 font-mono">
                      <p className="font-bold text-[11px] uppercase tracking-wider text-rose-700">Failure Diagnostics</p>
                      <p className="mt-1 text-xs">{execDetail.error_message}</p>
                    </div>
                  )}

                  {/* Self-Healing Proposals */}
                  {healingProposals.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="font-bold text-slate-900 text-sm">Self-Healing Diagnostic Proposals ({healingProposals.length})</h4>
                      {healingProposals.map((hp) => (
                        <div key={hp.id} className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-amber-900">🩺 Self-Healing: Step {hp.failed_step_index + 1}</span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-200 text-amber-900">
                                {hp.status}
                              </span>
                            </div>
                            <p className="text-[11px] text-amber-800 mt-1">
                              Proposed: <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">{hp.proposed_selector ? JSON.stringify(hp.proposed_selector) : "None"}</code> (Confidence: {hp.confidence_score}%)
                            </p>
                          </div>
                          <span className="text-xs text-amber-900 font-semibold">
                            {hp.status === "healed" ? "✓ Repaired" : hp.status === "awaiting_approval" ? "Review Pending" : hp.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Step-by-Step Traces */}
                  <div>
                    <h4 className="font-bold text-slate-900 text-sm mb-2">Executed Steps</h4>
                    {execDetail.step_results?.length === 0 ? (
                      <p className="text-slate-400 italic">No structured step records captured.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {execDetail.step_results?.map((step, idx) => (
                          <div
                            key={idx}
                            className={`rounded-lg p-2.5 border ${
                              step.status === "passed"
                                ? "bg-white border-emerald-200"
                                : step.status === "failed"
                                ? "bg-rose-50 border-rose-200"
                                : "bg-amber-50 border-amber-200"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-slate-400 font-bold text-[10px]">#{idx + 1}</span>
                                <span className="rounded bg-slate-800 text-white px-1.5 py-0.5 text-[10px] font-mono uppercase">
                                  {step.action}
                                </span>
                                <span
                                  className={`font-semibold ${
                                    step.status === "passed" ? "text-emerald-700" : "text-rose-700"
                                  }`}
                                >
                                  {step.status.toUpperCase()}
                                </span>
                              </div>
                              {step.duration_ms !== undefined && (
                                <span className="text-[10px] font-mono text-slate-500">{step.duration_ms}ms</span>
                              )}
                            </div>
                            {step.expected && (
                              <div className="mt-1 text-[11px] text-slate-600">
                                <span className="font-semibold text-slate-500">Expected:</span> {step.expected}
                              </div>
                            )}
                            {step.actual && (
                              <div className="text-[11px] text-slate-600">
                                <span className="font-semibold text-slate-500">Actual:</span> {step.actual}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Captured Evidence Gallery */}
                  <div>
                    <h4 className="font-bold text-slate-900 text-sm mb-2">
                      Captured Evidence ({execDetail.evidence?.length ?? 0})
                    </h4>
                    {execDetail.evidence?.length === 0 ? (
                      <p className="text-slate-400 italic">No artifacts stored for this run.</p>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {execDetail.evidence?.map((ev) => {
                          const isImage =
                            ev.evidence_type === "screenshot" ||
                            ev.uri.endsWith(".png") ||
                            ev.uri.endsWith(".jpg");
                          const downloadUrl = api.getEvidenceDownloadUrl(projectId, selectedExecId, ev.id);

                          if (isImage) {
                            return (
                              <div
                                key={ev.id}
                                className="group rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs hover:border-violet-400 transition cursor-pointer"
                                onClick={() => setZoomScreenshotUrl(downloadUrl)}
                              >
                                <div className="h-36 bg-slate-900 flex items-center justify-center overflow-hidden">
                                  <img
                                    src={downloadUrl}
                                    alt={ev.label || "Screenshot"}
                                    className="h-full w-full object-cover group-hover:scale-105 transition-transform"
                                    loading="lazy"
                                  />
                                </div>
                                <div className="p-2.5 flex items-center justify-between bg-white border-t border-slate-100">
                                  <span className="font-medium text-slate-800 truncate">{ev.label || "Screenshot"}</span>
                                  <span className="text-violet-600 text-[11px] font-semibold">Click to zoom</span>
                                </div>
                              </div>
                            );
                          }

                          return (
                            <div key={ev.id} className="rounded-xl border border-slate-200 bg-white p-3 shadow-xs">
                              <p className="font-semibold text-slate-800">📄 {ev.label || ev.evidence_type}</p>
                              <p className="mt-1 font-mono text-[10px] text-slate-500 truncate">{ev.uri}</p>
                              <a
                                href={downloadUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="mt-2 inline-block text-violet-600 hover:text-violet-800 font-semibold underline"
                              >
                                Download Artifact →
                              </a>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Screenshot Zoom Modal */}
      {zoomScreenshotUrl && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4"
          onClick={() => setZoomScreenshotUrl(null)}
        >
          <div className="relative max-w-5xl w-full max-h-[90vh] bg-slate-900 rounded-2xl overflow-hidden flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 bg-slate-800 text-white text-xs font-semibold">
              <span>📷 Execution Screenshot</span>
              <button
                type="button"
                onClick={() => setZoomScreenshotUrl(null)}
                className="h-6 w-6 rounded bg-rose-600 text-white flex items-center justify-center text-xs"
              >
                ✕
              </button>
            </div>
            <div className="p-4 flex items-center justify-center overflow-auto">
              <img
                src={zoomScreenshotUrl}
                alt="High Res"
                className="max-h-[75vh] w-auto rounded border border-slate-700"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
