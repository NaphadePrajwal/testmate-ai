import { useEffect, useState, useMemo, useCallback } from "react";
import { api } from "../../services/api";
import type {
  Defect,
  DefectStatus,
  ExecutionDetailResponse,
  FailureAnalysis,
  ExecutionEvidence,
} from "../../types/api";

interface DefectsViewProps {
  projectId: string;
  projectName: string;
}

export function DefectsView({ projectId, projectName }: DefectsViewProps) {
  const [defects, setDefects] = useState<Defect[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspect Modal State
  const [selectedDefect, setSelectedDefect] = useState<Defect | null>(null);
  const [executionDetail, setExecutionDetail] = useState<ExecutionDetailResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [failureAnalysis, setFailureAnalysis] = useState<FailureAnalysis | null>(null);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState<string | null>(null);
  const [newStatus, setNewStatus] = useState<DefectStatus>("new");
  const [resolutionNotes, setResolutionNotes] = useState<string>("");

  // Zoomed image modal
  const [zoomedImage, setZoomedImage] = useState<string | null>(null);

  const loadDefects = useCallback(() => {
    setIsLoading(true);
    setError(null);
    api
      .getDefects(projectId, 100, 0)
      .then((res) => setDefects(res.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load defects."))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadDefects());
  }, [loadDefects]);

  // When selectedDefect changes, load linked execution detail & failure analysis
  useEffect(() => {
    queueMicrotask(() => {
      if (!selectedDefect) {
        setExecutionDetail(null);
        setFailureAnalysis(null);
        setUpdateSuccess(null);
        return;
      }

      setNewStatus(selectedDefect.status);
      setResolutionNotes(selectedDefect.resolution_notes || "");
      setUpdateSuccess(null);

      // Fetch execution detail
      setIsLoadingDetail(true);
      api
        .getExecutionDetail(projectId, selectedDefect.execution_id)
        .then((detail) => setExecutionDetail(detail))
        .catch(() => setExecutionDetail(null))
        .finally(() => setIsLoadingDetail(false));

      // Fetch failure analysis
      setIsLoadingAnalysis(true);
      api
        .getExecutionFailureAnalysis(projectId, selectedDefect.execution_id)
        .then((analysis) => setFailureAnalysis(analysis))
        .catch(() => setFailureAnalysis(null))
        .finally(() => setIsLoadingAnalysis(false));
    });
  }, [selectedDefect, projectId]);

  const handleUpdateDefect = async () => {
    if (!selectedDefect) return;
    setIsUpdatingStatus(true);
    setUpdateSuccess(null);
    try {
      const updated = await api.updateDefect(projectId, selectedDefect.id, {
        status: newStatus,
        resolution_notes: resolutionNotes || undefined,
      });
      setSelectedDefect(updated);
      setDefects((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setUpdateSuccess("Defect status updated successfully.");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update defect status.");
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleTriggerAnalysis = async () => {
    if (!selectedDefect) return;
    setIsLoadingAnalysis(true);
    try {
      const res = await api.requestExecutionFailureAnalysis(projectId, selectedDefect.execution_id, true);
      setFailureAnalysis(res);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to trigger AI failure analysis.");
    } finally {
      setIsLoadingAnalysis(false);
    }
  };

  // Aggregated KPI counts
  const counts = useMemo(() => {
    const total = defects.length;
    const open = defects.filter((d) => d.status === "new" || d.status === "triaged" || d.status === "in_progress").length;
    const critical = defects.filter((d) => d.severity === "critical").length;
    const high = defects.filter((d) => d.severity === "high").length;
    const medium = defects.filter((d) => d.severity === "medium").length;
    const low = defects.filter((d) => d.severity === "low").length;
    const resolved = defects.filter((d) => d.status === "resolved" || d.status === "closed").length;
    return { total, open, critical, high, medium, low, resolved };
  }, [defects]);

  // Filtered defects
  const filteredDefects = useMemo(() => {
    return defects.filter((d) => {
      if (statusFilter !== "all" && d.status !== statusFilter) return false;
      if (severityFilter !== "all" && d.severity !== severityFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matchesTitle = d.title.toLowerCase().includes(query);
        const matchesDesc = (d.description || "").toLowerCase().includes(query);
        const matchesFingerprint = (d.fingerprint || "").toLowerCase().includes(query);
        if (!matchesTitle && !matchesDesc && !matchesFingerprint) return false;
      }
      return true;
    });
  }, [defects, statusFilter, severityFilter, searchQuery]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-rose-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Retrieving defects & failure evidence for {projectName}…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <h4 className="font-bold text-base text-rose-900">Defects Unavailable</h4>
        <p className="mt-1">{error}</p>
        <button
          onClick={loadDefects}
          className="mt-4 rounded-xl bg-rose-700 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-800"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Defects & Failure Intelligence</h2>
          <p className="text-sm text-slate-500">
            Track, triage, inspect AI root causes, and verify resolutions across all browser test runs.
          </p>
        </div>
        <button
          onClick={loadDefects}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition"
        >
          🔄 Refresh Defects
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Defects</p>
          <p className="mt-2 text-2xl font-extrabold text-slate-900">{counts.total}</p>
          <p className="mt-1 text-[11px] text-slate-400">All recorded</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-rose-600">Open Defects</p>
          <p className="mt-2 text-2xl font-extrabold text-rose-600">{counts.open}</p>
          <p className="mt-1 text-[11px] text-rose-700">Needs attention</p>
        </div>

        <div className="rounded-2xl border border-rose-100 bg-rose-50/50 p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-rose-700">Critical</p>
          <p className="mt-2 text-2xl font-extrabold text-rose-700">{counts.critical}</p>
          <p className="mt-1 text-[11px] text-rose-600">Blockers</p>
        </div>

        <div className="rounded-2xl border border-amber-100 bg-amber-50/50 p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-700">High</p>
          <p className="mt-2 text-2xl font-extrabold text-amber-700">{counts.high}</p>
          <p className="mt-1 text-[11px] text-amber-600">Major impact</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Medium / Low</p>
          <p className="mt-2 text-2xl font-extrabold text-slate-700">{counts.medium + counts.low}</p>
          <p className="mt-1 text-[11px] text-slate-400">Minor issues</p>
        </div>

        <div className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">Resolved</p>
          <p className="mt-2 text-2xl font-extrabold text-emerald-700">{counts.resolved}</p>
          <p className="mt-1 text-[11px] text-emerald-600">Fixed or closed</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        {/* Status Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mr-1">Status:</span>
          {(["all", "new", "triaged", "resolved", "closed"] as const).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold capitalize transition ${
                statusFilter === status
                  ? "bg-violet-700 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {status}
            </button>
          ))}
        </div>

        {/* Severity Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mr-1">Severity:</span>
          {(["all", "critical", "high", "medium", "low"] as const).map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`rounded-xl px-2.5 py-1 text-xs font-semibold capitalize transition ${
                severityFilter === sev
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative min-w-[220px]">
          <input
            type="text"
            placeholder="Search defects by title, desc…"
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

      {/* Defects Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
        {filteredDefects.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <span className="text-3xl">🎉</span>
            <p className="mt-2 text-sm font-semibold text-slate-700">No defects match your criteria</p>
            <p className="text-xs text-slate-500">Either no defects have been filed or your filters are too restrictive.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 font-bold uppercase tracking-wider text-slate-500">
                  <th className="py-3.5 px-4">Defect Details</th>
                  <th className="py-3.5 px-4">Severity</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4">Linked Execution</th>
                  <th className="py-3.5 px-4">Reported</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDefects.map((defect) => (
                  <tr key={defect.id} className="hover:bg-slate-50/70 transition">
                    {/* Defect Title & Description */}
                    <td className="py-3.5 px-4">
                      <div className="max-w-md">
                        <p className="font-bold text-slate-900 line-clamp-1">{defect.title}</p>
                        <p className="mt-0.5 text-[11px] text-slate-500 line-clamp-2">
                          {defect.description || "No description provided."}
                        </p>
                        {defect.fingerprint && (
                          <span className="mt-1 inline-block font-mono text-[9px] text-slate-400 bg-slate-100 px-1 rounded">
                            fp: {defect.fingerprint.slice(0, 12)}…
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Severity */}
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                          defect.severity === "critical"
                            ? "bg-rose-100 text-rose-800 border border-rose-300"
                            : defect.severity === "high"
                            ? "bg-orange-100 text-orange-800 border border-orange-300"
                            : defect.severity === "medium"
                            ? "bg-amber-100 text-amber-800 border border-amber-300"
                            : "bg-slate-100 text-slate-700 border border-slate-300"
                        }`}
                      >
                        {defect.severity}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                          defect.status === "new"
                            ? "bg-blue-100 text-blue-800"
                            : defect.status === "triaged"
                            ? "bg-violet-100 text-violet-800"
                            : defect.status === "resolved"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {defect.status}
                      </span>
                    </td>

                    {/* Linked Execution */}
                    <td className="py-3.5 px-4">
                      <span className="font-mono text-[11px] text-slate-600">
                        {defect.execution_id.slice(0, 8)}…
                      </span>
                    </td>

                    {/* Reported At */}
                    <td className="py-3.5 px-4 text-slate-500">
                      {new Date(defect.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => setSelectedDefect(defect)}
                        className="rounded-lg bg-violet-700 px-3 py-1 font-semibold text-white shadow-2xs hover:bg-violet-800 transition"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Inspect Defect Modal / Slide-over */}
      {selectedDefect && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="relative max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl sm:p-8">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-200 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      selectedDefect.severity === "critical"
                        ? "bg-rose-100 text-rose-800"
                        : selectedDefect.severity === "high"
                        ? "bg-orange-100 text-orange-800"
                        : selectedDefect.severity === "medium"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {selectedDefect.severity}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">
                    ID: {selectedDefect.id.slice(0, 8)}
                  </span>
                </div>
                <h3 className="mt-2 text-xl font-bold text-slate-900">{selectedDefect.title}</h3>
              </div>
              <button
                onClick={() => setSelectedDefect(null)}
                className="rounded-xl border border-slate-200 bg-slate-50 p-2 text-slate-500 hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="mt-6 space-y-6 text-xs">
              {/* Description */}
              <div>
                <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Description & Reproduction</h4>
                <p className="mt-1 text-slate-600 bg-slate-50 p-3 rounded-xl whitespace-pre-wrap leading-relaxed">
                  {selectedDefect.description || "No description provided."}
                </p>
              </div>

              {/* Status Update & Resolution Form */}
              <div className="rounded-2xl border border-violet-100 bg-violet-50/40 p-4">
                <h4 className="font-bold text-violet-950 uppercase tracking-wider text-[11px] mb-3">
                  Triage & Resolution Workflow
                </h4>
                {updateSuccess && (
                  <p className="mb-3 rounded-lg bg-emerald-100 px-3 py-1.5 text-emerald-800 font-semibold">
                    ✓ {updateSuccess}
                  </p>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">Defect Status</label>
                    <select
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value as DefectStatus)}
                      className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 focus:border-violet-600 focus:outline-hidden"
                    >
                      <option value="new">NEW (Unreviewed)</option>
                      <option value="triaged">TRIAGED (Confirmed)</option>
                      <option value="in_progress">IN PROGRESS (Fix underway)</option>
                      <option value="resolved">RESOLVED (Fix deployed)</option>
                      <option value="closed">CLOSED (Verified)</option>
                      <option value="rejected">REJECTED (Not a bug)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">Resolution Notes</label>
                    <input
                      type="text"
                      placeholder="e.g. Fixed CSS selector, patched API handler"
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                      className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-800 focus:border-violet-600 focus:outline-hidden"
                    />
                  </div>
                </div>
                <div className="mt-3 flex justify-end">
                  <button
                    onClick={handleUpdateDefect}
                    disabled={isUpdatingStatus}
                    className="rounded-xl bg-violet-700 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-violet-800 disabled:opacity-50 transition"
                  >
                    {isUpdatingStatus ? "Updating…" : "Save Defect Changes"}
                  </button>
                </div>
              </div>

              {/* Linked Execution Details */}
              <div>
                <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  Linked Execution Context
                </h4>
                {isLoadingDetail ? (
                  <p className="mt-2 text-slate-400">Loading linked execution details…</p>
                ) : executionDetail ? (
                  <div className="mt-2 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
                      <div>
                        <p className="font-bold text-slate-900 text-xs">
                          {executionDetail.test_case_snapshot?.title || "Test Case"}
                        </p>
                        <p className="text-[10px] text-slate-400">
                          Executor: {executionDetail.executor || "Playwright"} • ID: {executionDetail.id.slice(0, 8)}
                        </p>
                      </div>
                      <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-[10px] font-bold text-rose-800">
                        {executionDetail.status.toUpperCase()}
                      </span>
                    </div>

                    {executionDetail.error_message && (
                      <div className="rounded-xl bg-rose-50 p-3 text-rose-900 font-mono text-[11px]">
                        {executionDetail.error_message}
                      </div>
                    )}

                    {/* Step Results */}
                    {executionDetail.step_results && executionDetail.step_results.length > 0 && (
                      <div>
                        <p className="font-semibold text-slate-700 text-[11px] mb-2">Step Execution Trace:</p>
                        <div className="space-y-1.5">
                          {executionDetail.step_results.map((st, idx) => (
                            <div
                              key={idx}
                              className={`flex items-start gap-2 rounded-lg p-2 ${
                                st.status === "failed" ? "bg-rose-50 border border-rose-200" : "bg-slate-50"
                              }`}
                            >
                              <span className="font-bold text-slate-500 font-mono text-[10px]">#{st.step_index}</span>
                              <span
                                className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${
                                  st.status === "passed"
                                    ? "bg-emerald-100 text-emerald-800"
                                    : "bg-rose-100 text-rose-800"
                                }`}
                              >
                                {st.status}
                              </span>
                              <div className="flex-1">
                                <p className="font-medium text-slate-800">{st.action}</p>
                                {st.error_message && (
                                  <p className="mt-0.5 font-mono text-[10px] text-rose-700">{st.error_message}</p>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Screenshot Evidence */}
                    {executionDetail.evidence && executionDetail.evidence.length > 0 && (
                      <div>
                        <p className="font-semibold text-slate-700 text-[11px] mb-2">Visual Failure Evidence:</p>
                        <div className="flex flex-wrap gap-3">
                          {executionDetail.evidence
                            .filter((ev: ExecutionEvidence) => ev.evidence_type === "screenshot")
                            .map((ev: ExecutionEvidence) => {
                              const downloadUrl = api.getEvidenceDownloadUrl(
                                projectId,
                                selectedDefect.execution_id,
                                ev.id
                              );
                              return (
                                <div
                                  key={ev.id}
                                  onClick={() => setZoomedImage(downloadUrl)}
                                  className="group relative cursor-pointer overflow-hidden rounded-xl border border-slate-200 shadow-2xs hover:shadow-md transition"
                                >
                                  <img
                                    src={downloadUrl}
                                    alt={ev.label || "Failure Screenshot"}
                                    className="h-28 w-44 object-cover group-hover:scale-105 transition"
                                  />
                                  <div className="absolute inset-0 flex items-center justify-center bg-slate-900/40 opacity-0 group-hover:opacity-100 transition text-white font-bold text-[11px]">
                                    🔍 Click to Zoom
                                  </div>
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="mt-2 text-slate-400">Execution context could not be loaded.</p>
                )}
              </div>

              {/* AI Root Cause Failure Analysis */}
              <div>
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                    🤖 AI Root Cause Failure Analysis
                  </h4>
                  {!failureAnalysis && (
                    <button
                      onClick={handleTriggerAnalysis}
                      disabled={isLoadingAnalysis}
                      className="rounded-lg bg-violet-700 px-3 py-1 font-semibold text-white shadow-2xs hover:bg-violet-800 disabled:opacity-50 transition"
                    >
                      {isLoadingAnalysis ? "Analyzing…" : "Run AI Root Cause Analysis"}
                    </button>
                  )}
                </div>

                {isLoadingAnalysis ? (
                  <div className="mt-2 rounded-2xl border border-violet-200 bg-violet-50/50 p-4 text-center text-slate-500">
                    <span className="text-xl animate-spin text-violet-600 mr-2">🌀</span>
                    Evaluating failure logs, DOM state, and stack trace with Gemini…
                  </div>
                ) : failureAnalysis ? (
                  <div className="mt-2 rounded-2xl border border-violet-200 bg-white p-5 shadow-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                      <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-[10px] font-bold text-violet-800 uppercase tracking-wider">
                        Category: {failureAnalysis.failure_category}
                      </span>
                      <span className="text-[10px] text-slate-400 font-medium">
                        Confidence: <strong className="text-slate-700 uppercase">{failureAnalysis.confidence}</strong>
                      </span>
                    </div>

                    <div>
                      <p className="font-bold text-slate-800 text-xs">Summary:</p>
                      <p className="mt-0.5 text-slate-600">{failureAnalysis.summary}</p>
                    </div>

                    <div>
                      <p className="font-bold text-rose-800 text-xs">Likely Root Cause:</p>
                      <p className="mt-0.5 text-rose-900 bg-rose-50 p-2.5 rounded-lg font-medium">
                        {failureAnalysis.likely_root_cause}
                      </p>
                    </div>

                    {failureAnalysis.recommended_debugging_steps &&
                      failureAnalysis.recommended_debugging_steps.length > 0 && (
                        <div>
                          <p className="font-bold text-slate-800 text-xs mb-1">Recommended Debugging Steps:</p>
                          <ul className="list-disc space-y-1 pl-5 text-slate-600">
                            {failureAnalysis.recommended_debugging_steps.map((step, idx) => (
                              <li key={idx}>{step}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                  </div>
                ) : (
                  <div className="mt-2 rounded-xl border border-dashed border-slate-200 p-4 text-center text-slate-400">
                    No AI root cause analysis exists for this execution yet. Click “Run AI Root Cause Analysis” to trigger.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen Image Zoom Modal */}
      {zoomedImage && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setZoomedImage(null)}
        >
          <div className="relative max-h-[95vh] max-w-[95vw] overflow-hidden rounded-2xl bg-white p-2 shadow-2xl">
            <button
              onClick={() => setZoomedImage(null)}
              className="absolute right-3 top-3 z-10 rounded-full bg-slate-900/70 p-2 text-white hover:bg-slate-900"
            >
              ✕
            </button>
            <img src={zoomedImage} alt="Zoomed Screenshot" className="max-h-[90vh] max-w-[90vw] object-contain" />
          </div>
        </div>
      )}
    </div>
  );
}
