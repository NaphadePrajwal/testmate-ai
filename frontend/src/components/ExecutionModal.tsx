import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type {
  EvidenceListResponse,
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

export function ExecutionModal({ projectId, testCase, isOpen, onClose }: ExecutionModalProps) {
  const [activeExecution, setActiveExecution] = useState<TestExecution | null>(null);
  const [executions, setExecutions] = useState<TestExecution[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceListResponse | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedExecutor, setSelectedExecutor] = useState<"auto" | "playwright" | "httpx" | "pytest">("auto");

  const loadHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    setError(null);
    try {
      const res: ExecutionListResponse = await api.getExecutions(projectId, testCase.id, 20);
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
        setExecutions([]);
        setEvidenceList(null);
        setError(null);
      });
    }
  }, [isOpen]);

  useEffect(() => {
    async function loadEvidence() {
      if (!activeExecution) {
        setEvidenceList(null);
        return;
      }
      try {
        const ev = await api.getExecutionEvidence(projectId, activeExecution.id);
        setEvidenceList(ev);
      } catch {
        setEvidenceList(null);
      }
    }
    void loadEvidence();
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-2xl ring-1 ring-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                {testCase.test_type.toUpperCase()}
              </span>
              <h2 className="text-base font-bold text-slate-900">{testCase.title}</h2>
            </div>
            <p className="text-xs text-slate-500">
              Automated execution engine & evidence viewer
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
                  Running...
                </>
              ) : (
                <>▶ Execute Test</>
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
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
              Run History ({executions.length})
            </h3>
            {isLoadingHistory ? (
              <p className="text-xs text-slate-400">Loading history...</p>
            ) : executions.length === 0 ? (
              <p className="text-xs text-slate-400">No executions recorded yet. Click Execute Test to start.</p>
            ) : (
              <div className="space-y-2">
                {executions.map((run) => {
                  const isSelected = activeExecution?.id === run.id;
                  const statusColors = {
                    passed: "border-emerald-500 bg-emerald-50/50 text-emerald-800",
                    failed: "border-rose-500 bg-rose-50/50 text-rose-800",
                    error: "border-amber-500 bg-amber-50/50 text-amber-800",
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
                          ? "border-indigo-500 bg-indigo-50/30 ring-2 ring-indigo-200"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase ${statusColors}`}>
                          {run.status}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {new Date(run.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
                        <span>Runner: {run.executor || "default"}</span>
                        <span>{run.summary?.total_duration_ms ? `${run.summary.total_duration_ms}ms` : ""}</span>
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
            ) : (
              <>
                {/* Status Card */}
                <div className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/70 p-4">
                  <div>
                    <span className="text-xs font-semibold text-slate-500">Status</span>
                    <div className="mt-0.5 flex items-center gap-2">
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
                      <span className="text-sm font-bold uppercase text-slate-800">
                        {activeExecution.status}
                      </span>
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-semibold text-slate-500">Duration</span>
                    <p className="mt-0.5 text-sm font-bold text-slate-800">
                      {activeExecution.summary?.total_duration_ms
                        ? `${activeExecution.summary.total_duration_ms} ms`
                        : "—"}
                    </p>
                  </div>

                  <div>
                    <span className="text-xs font-semibold text-slate-500">Step Outcomes</span>
                    <p className="mt-0.5 text-sm font-bold text-slate-800">
                      {activeExecution.summary?.passed_steps ?? 0} / {activeExecution.summary?.total_steps ?? 0} Passed
                    </p>
                  </div>

                  <div>
                    <span className="text-xs font-semibold text-slate-500">Run Ref</span>
                    <p className="mt-0.5 font-mono text-xs text-slate-600">
                      {activeExecution.run_reference || activeExecution.id.slice(0, 8)}
                    </p>
                  </div>
                </div>

                {/* Error Banner if Failed */}
                {activeExecution.error_message && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-3 text-xs text-rose-800">
                    <span className="font-bold">Failure Reason: </span>
                    <span>{activeExecution.error_message}</span>
                  </div>
                )}

                {/* Step Breakdown */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Step-by-Step Results
                  </h4>
                  <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                    {activeExecution.summary?.step_results?.map((step) => (
                      <div key={step.step_index} className="p-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                                step.status === "passed"
                                  ? "bg-emerald-100 text-emerald-700"
                                  : step.status === "failed"
                                  ? "bg-rose-100 text-rose-700"
                                  : "bg-amber-100 text-amber-700"
                              }`}
                            >
                              {step.status === "passed" ? "✓" : "✕"}
                            </span>
                            <span className="text-xs font-semibold text-slate-800">
                              Step {step.step_index}: {step.action}
                            </span>
                          </div>
                          <span className="text-[11px] font-mono text-slate-400">
                            {step.duration_ms} ms
                          </span>
                        </div>

                        <div className="mt-2 space-y-1 pl-7 text-[11px]">
                          {step.expected && (
                            <div className="text-slate-500">
                              <span className="font-medium text-slate-600">Expected: </span>
                              {step.expected}
                            </div>
                          )}
                          {step.actual && (
                            <div className="text-slate-700">
                              <span className="font-medium text-slate-600">Actual: </span>
                              {step.actual}
                            </div>
                          )}
                          {step.error_message && (
                            <div className="text-rose-600">
                              <span className="font-medium">Error: </span>
                              {step.error_message}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Evidence Artifacts */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Execution Evidence ({evidenceList?.items.length ?? 0})
                  </h4>
                  {!evidenceList || evidenceList.items.length === 0 ? (
                    <p className="text-xs text-slate-400">No evidence artifacts attached to this run.</p>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {evidenceList.items.map((ev) => {
                        const downloadUrl = api.getEvidenceDownloadUrl(projectId, activeExecution.id, ev.id);
                        return (
                          <div
                            key={ev.id}
                            className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 text-xs"
                          >
                            <div>
                              <div className="flex items-center justify-between">
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-600">
                                  {ev.evidence_type}
                                </span>
                                <span className="text-[10px] text-slate-400">
                                  {new Date(ev.created_at).toLocaleTimeString()}
                                </span>
                              </div>
                              <p className="mt-1 font-semibold text-slate-800">{ev.label || ev.uri}</p>
                              <p className="mt-0.5 text-[11px] text-slate-500">{ev.content_type || "binary"}</p>
                            </div>

                            {/* Image Preview if Screenshot */}
                            {ev.evidence_type === "screenshot" && (
                              <div className="my-2 max-h-32 overflow-hidden rounded border border-slate-100 bg-slate-50">
                                <img
                                  src={downloadUrl}
                                  alt={ev.label || "Screenshot"}
                                  className="h-auto w-full object-contain"
                                />
                              </div>
                            )}

                            <div className="mt-2 border-t border-slate-100 pt-2">
                              <a
                                href={downloadUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-semibold text-indigo-600 hover:text-indigo-800"
                              >
                                ⬇ Download / View Artifact
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
      </div>
    </div>
  );
}
