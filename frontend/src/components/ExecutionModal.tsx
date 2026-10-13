import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type {
  ExecutionDetailResponse,
  ExecutionListResponse,
  ExecutionTriggerInput,
  TestCase,
  TestExecution,
} from "../types/api";

interface ExecutionModalProps {
  projectId: string;
  testCase: TestCase;
  isOpen: boolean;
  onClose: () => void;
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function ExecutionModal({ projectId, testCase, isOpen, onClose }: ExecutionModalProps) {
  const [activeExecution, setActiveExecution] = useState<TestExecution | null>(null);
  const [executionDetail, setExecutionDetail] = useState<ExecutionDetailResponse | null>(null);
  const [executions, setExecutions] = useState<TestExecution[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedExecutor, setSelectedExecutor] = useState<"auto" | "playwright" | "httpx" | "pytest">("auto");
  const [selectedScreenshotUrl, setSelectedScreenshotUrl] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    setError(null);
    try {
      const res: ExecutionListResponse = await api.getTestCaseHistory(projectId, testCase.id, 20);
      setExecutions(res.items);
      if (res.items.length > 0) {
        setActiveExecution(res.items[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load execution history.");
    } finally {
      setIsLoadingHistory(false);
    }
  }, [projectId, testCase.id]);

  useEffect(() => {
    if (isOpen) {
      queueMicrotask(() => {
        void loadHistory();
      });
    }
  }, [isOpen, loadHistory]);

  useEffect(() => {
    if (!isOpen) {
      queueMicrotask(() => {
        setActiveExecution(null);
        setExecutionDetail(null);
        setExecutions([]);
        setError(null);
        setSelectedScreenshotUrl(null);
      });
    }
  }, [isOpen]);

  useEffect(() => {
    async function loadDetail() {
      if (!activeExecution) {
        setExecutionDetail(null);
        return;
      }
      setIsLoadingDetail(true);
      try {
        const detail = await api.getExecutionDetail(projectId, activeExecution.id);
        setExecutionDetail(detail);
      } catch {
        setExecutionDetail(null);
      } finally {
        setIsLoadingDetail(false);
      }
    }
    void loadDetail();
  }, [activeExecution, projectId]);

  async function handleTriggerExecution() {
    setIsExecuting(true);
    setError(null);
    try {
      const payload: ExecutionTriggerInput | undefined =
        selectedExecutor === "auto" ? undefined : { executor: selectedExecutor };
      const run = await api.executeTestCase(projectId, testCase.id, payload);
      setActiveExecution(run);
      setExecutions((prev) => [run, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed to start.");
    } finally {
      setIsExecuting(false);
    }
  }

  if (!isOpen) return null;

  const currentSummary = executionDetail?.summary || activeExecution?.summary;
  const currentStepResults = executionDetail?.step_results || currentSummary?.step_results || [];
  const currentEvidence = executionDetail?.evidence || [];
  const currentDefects = executionDetail?.defects || [];
  const currentSnapshot = executionDetail?.test_case_snapshot;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-2xl ring-1 ring-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                {testCase.test_type.toUpperCase()}
              </span>
              <h2 className="text-base font-bold text-slate-900">{testCase.title}</h2>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                Current v{testCase.version}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Phase 6 Centralized Test Results & Evidence Management Layer
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ✕
          </button>
        </div>

        {/* Toolbar & Trigger */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 px-6 py-3">
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-slate-600">Runner:</label>
            <select
              value={selectedExecutor}
              onChange={(e) => setSelectedExecutor(e.target.value as "auto" | "playwright" | "httpx" | "pytest")}
              disabled={isExecuting}
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none"
            >
              <option value="auto">Auto ({testCase.test_type})</option>
              <option value="playwright">Playwright (Browser)</option>
              <option value="httpx">HTTPX (API REST)</option>
              <option value="pytest">PyTest (Sandboxed)</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={isExecuting || testCase.review_status !== "approved"}
              onClick={() => void handleTriggerExecution()}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isExecuting ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Executing...
                </>
              ) : (
                <>▶ Execute Run</>
              )}
            </button>
          </div>
        </div>

        {/* Error notification */}
        {error && (
          <div className="mx-6 mt-4 rounded-lg bg-rose-50 p-3 text-xs text-rose-700 ring-1 ring-rose-200">
            {error}
          </div>
        )}

        {/* Body Content */}
        <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-3">
          {/* Left: Execution Runs History */}
          <div className="border-r border-slate-100 p-4 overflow-y-auto">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Run History ({executions.length})
              </h3>
              <span className="text-[10px] text-slate-400">Chronological</span>
            </div>
            {isLoadingHistory ? (
              <p className="text-xs text-slate-400">Loading history...</p>
            ) : executions.length === 0 ? (
              <p className="text-xs text-slate-400">No executions recorded yet. Click Execute Run to start.</p>
            ) : (
              <div className="space-y-2">
                {executions.map((run, idx) => {
                  const isSelected = activeExecution?.id === run.id;
                  const isLatest = idx === 0;
                  const statusColors = {
                    passed: "border-emerald-500 bg-emerald-50 text-emerald-800",
                    failed: "border-rose-500 bg-rose-50 text-rose-800",
                    error: "border-amber-500 bg-amber-50 text-amber-800",
                    queued: "border-slate-300 bg-slate-50 text-slate-700",
                    running: "border-indigo-400 bg-indigo-50 text-indigo-700",
                    cancelled: "border-slate-300 bg-slate-50 text-slate-600",
                  }[run.status] || "border-slate-200 bg-white text-slate-700";

                  return (
                    <button
                      key={run.id}
                      type="button"
                      onClick={() => setActiveExecution(run)}
                      className={`w-full rounded-xl border p-2.5 text-left transition-all ${
                        isSelected
                          ? "border-indigo-500 bg-indigo-50/40 ring-2 ring-indigo-200"
                          : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${statusColors}`}>
                            {run.status}
                          </span>
                          {isLatest && (
                            <span className="rounded bg-indigo-600 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wide text-white">
                              Latest
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                      </div>
                      <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500">
                        <span>Runner: <strong className="text-slate-700">{run.executor || "default"}</strong></span>
                        <span>
                          {run.summary?.passed_steps ?? 0}/{run.summary?.total_steps ?? 0} Steps
                        </span>
                      </div>
                      <div className="mt-0.5 text-[10px] font-mono text-slate-400">
                        {run.run_reference || run.id.slice(0, 8)}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Selected Run Details & Steps & Evidence */}
          <div className="col-span-2 overflow-y-auto p-6 space-y-6">
            {!activeExecution ? (
              <div className="flex h-48 items-center justify-center text-xs text-slate-400">
                Select an execution on the left or trigger a new one.
              </div>
            ) : isLoadingDetail ? (
              <div className="flex h-48 items-center justify-center text-xs text-slate-400">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent mr-2" />
                Loading execution results and verified evidence...
              </div>
            ) : (
              <>
                {/* Historical Execution-Time Snapshot Banner */}
                {currentSnapshot && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-100 bg-indigo-50/50 px-4 py-2.5 text-xs text-indigo-900">
                    <div className="flex items-center gap-2">
                      <span className="font-bold">📸 Execution-Time Snapshot:</span>
                      <span>v{currentSnapshot.version} — {currentSnapshot.title}</span>
                    </div>
                    {testCase.version !== currentSnapshot.version && (
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                        Test case updated to v{testCase.version} since this run
                      </span>
                    )}
                  </div>
                )}

                {/* Status and Metric Summary Cards */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
                  <div>
                    <span className="text-[11px] font-medium text-slate-500">Status</span>
                    <div className="mt-1 flex items-center gap-1.5">
                      <span
                        className={`inline-block h-2.5 w-2.5 rounded-full ${
                          activeExecution.status === "passed"
                            ? "bg-emerald-500"
                            : activeExecution.status === "failed"
                            ? "bg-rose-500"
                            : activeExecution.status === "error"
                            ? "bg-amber-500"
                            : "bg-indigo-500"
                        }`}
                      />
                      <span className="text-xs font-bold uppercase text-slate-800">
                        {activeExecution.status}
                      </span>
                    </div>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-500">Duration</span>
                    <p className="mt-1 text-xs font-bold text-slate-800">
                      {currentSummary?.duration_ms ?? currentSummary?.total_duration_ms ?? "—"} ms
                    </p>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-500">Step Outcomes</span>
                    <p className="mt-1 text-xs font-bold text-slate-800">
                      {currentSummary?.passed_steps ?? 0} / {currentSummary?.total_steps ?? 0} Passed
                    </p>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-500">Runner</span>
                    <p className="mt-1 font-mono text-xs font-bold text-slate-700">
                      {activeExecution.executor || "default"}
                    </p>
                  </div>
                </div>

                {/* Error Banner with Categorization if Failed/Errored */}
                {(activeExecution.error_message || currentSummary?.sanitized_failure_reason) && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-4 text-xs text-rose-900 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-rose-800">Execution Failure</span>
                      {currentSummary?.error_category && (
                        <span className="rounded bg-rose-200/80 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-900">
                          {currentSummary.error_category.replace(/_/g, " ")}
                        </span>
                      )}
                      {currentSummary?.failed_step_index !== null && currentSummary?.failed_step_index !== undefined && (
                        <span className="rounded bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-800">
                          Failed at Step {currentSummary.failed_step_index}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-[11px] text-rose-800 whitespace-pre-wrap">
                      {currentSummary?.sanitized_failure_reason || activeExecution.error_message}
                    </p>
                  </div>
                )}

                {/* Auto-logged Defect Section if exists */}
                {currentDefects.length > 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-amber-900">
                        🚨 Defect Logged ({currentDefects.length})
                      </span>
                      <span className="rounded bg-amber-200 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-900">
                        {currentDefects[0].severity} Severity
                      </span>
                    </div>
                    <p className="mt-1 text-slate-700">{currentDefects[0].title}</p>
                  </div>
                )}

                {/* Step Breakdown */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                      Step-by-Step Results ({currentStepResults.length})
                    </h4>
                    <span className="text-[11px] text-slate-400">Expected vs Observed Behavior</span>
                  </div>
                  <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
                    {currentStepResults.length === 0 ? (
                      <p className="p-4 text-xs text-slate-400">No individual step results recorded.</p>
                    ) : (
                      currentStepResults.map((step) => {
                        const isFailed = step.status === "failed";
                        const isPassed = step.status === "passed";
                        const isSkipped = step.status === "skipped";

                        return (
                          <div key={step.step_index} className={`p-3.5 ${isFailed ? "bg-rose-50/30" : ""}`}>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                                    isPassed
                                      ? "bg-emerald-100 text-emerald-700"
                                      : isFailed
                                      ? "bg-rose-100 text-rose-700"
                                      : isSkipped
                                      ? "bg-slate-100 text-slate-500"
                                      : "bg-amber-100 text-amber-700"
                                  }`}
                                >
                                  {isPassed ? "✓" : isFailed ? "✕" : isSkipped ? "—" : "!"}
                                </span>
                                <span className="text-xs font-semibold text-slate-800">
                                  Step {step.step_index}: {step.action}
                                </span>
                              </div>
                              <span className="text-[11px] font-mono text-slate-400">
                                {step.duration_ms ?? 0} ms
                              </span>
                            </div>

                            <div className="mt-2.5 space-y-1.5 pl-7 text-[11px]">
                              {(step.expected || step.expected_result) && (
                                <div className="text-slate-600">
                                  <span className="font-semibold text-slate-500">Expected: </span>
                                  <span>{step.expected || step.expected_result}</span>
                                </div>
                              )}
                              <div className={isFailed ? "text-rose-700 font-medium" : "text-slate-700"}>
                                <span className="font-semibold text-slate-500">Observed: </span>
                                <span>
                                  {step.actual || step.actual_result || (isSkipped ? "Skipped (preceding failure)" : "Execution confirmed")}
                                </span>
                              </div>
                              {(step.error_message || step.error_details) && (
                                <div className="rounded bg-rose-50 p-2 text-rose-700 font-mono text-[10px]">
                                  <span className="font-semibold">Error: </span>
                                  {step.error_message || step.error_details}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Evidence Artifacts */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                      Execution Evidence & Diagnostic Artifacts ({currentEvidence.length})
                    </h4>
                    <span className="text-[11px] text-slate-400">Containment-Verified</span>
                  </div>
                  {currentEvidence.length === 0 ? (
                    <p className="text-xs text-slate-400">No evidence artifacts attached to this run.</p>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {currentEvidence.map((ev) => {
                        const downloadUrl = api.getEvidenceDownloadUrl(projectId, activeExecution.id, ev.id);
                        const fileSize = (ev.metadata?.size_bytes ?? ev.metadata?.file_size_bytes) as number | undefined;
                        const sha256 = ev.metadata?.sha256 as string | undefined;

                        return (
                          <div
                            key={ev.id}
                            className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-3.5 text-xs shadow-sm hover:border-slate-300 transition-all"
                          >
                            <div>
                              <div className="flex items-center justify-between">
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-600">
                                  {ev.evidence_type}
                                </span>
                                <span className="text-[10px] text-slate-400">
                                  {new Date(ev.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                </span>
                              </div>
                              <p className="mt-1.5 font-semibold text-slate-800 truncate" title={ev.label || ev.uri}>
                                {ev.label || ev.uri}
                              </p>
                              <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                                <span>{ev.content_type || "binary"}</span>
                                <span>{formatBytes(fileSize)}</span>
                              </div>
                              {sha256 && (
                                <p className="mt-1 font-mono text-[9px] text-slate-400 truncate" title={`SHA-256: ${sha256}`}>
                                  SHA: {sha256.slice(0, 16)}...
                                </p>
                              )}
                            </div>

                            {/* Image Preview if Screenshot */}
                            {ev.evidence_type === "screenshot" && (
                              <div
                                onClick={() => setSelectedScreenshotUrl(downloadUrl)}
                                className="my-2.5 max-h-36 overflow-hidden rounded border border-slate-100 bg-slate-50 cursor-pointer hover:opacity-95"
                              >
                                <img
                                  src={downloadUrl}
                                  alt={ev.label || "Screenshot"}
                                  className="h-auto w-full object-contain"
                                />
                              </div>
                            )}

                            <div className="mt-2.5 border-t border-slate-100 pt-2 flex items-center justify-between">
                              <a
                                href={downloadUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-semibold text-indigo-600 hover:text-indigo-800 text-[11px]"
                              >
                                ⬇ Download Artifact
                              </a>
                            </div>
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

        {/* Screenshot Fullscreen Viewer Modal */}
        {selectedScreenshotUrl && (
          <div
            className="fixed inset-0 z-60 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
            onClick={() => setSelectedScreenshotUrl(null)}
          >
            <div className="relative max-h-full max-w-full overflow-auto">
              <button
                type="button"
                onClick={() => setSelectedScreenshotUrl(null)}
                className="absolute top-2 right-2 rounded-full bg-black/60 px-3 py-1 text-sm font-bold text-white hover:bg-black/90"
              >
                ✕ Close
              </button>
              <img
                src={selectedScreenshotUrl}
                alt="Full Screenshot"
                className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
