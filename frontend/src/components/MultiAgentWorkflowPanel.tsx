import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type {
  ExecutionDetailResponse,
  TestCase,
  WorkflowApprovalAction,
  WorkflowDetailResponse,
  WorkflowEvent,
} from "../types/api";

interface MultiAgentWorkflowPanelProps {
  projectId: string;
  requirementId: string;
  requirementTitle: string;
}

export function MultiAgentWorkflowPanel({
  projectId,
  requirementId,
  requirementTitle,
}: MultiAgentWorkflowPanelProps) {
  const [activeWorkflow, setActiveWorkflow] = useState<WorkflowDetailResponse | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [revisionInstructions, setRevisionInstructions] = useState("");
  const [activeAction, setActiveAction] = useState<WorkflowApprovalAction | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [expandedExecId, setExpandedExecId] = useState<string | null>(null);
  const [execDetails, setExecDetails] = useState<Record<string, ExecutionDetailResponse>>({});
  const [loadingExecId, setLoadingExecId] = useState<string | null>(null);
  const [selectedScreenshotUrl, setSelectedScreenshotUrl] = useState<string | null>(null);

  async function handleToggleExecution(execId: string) {
    if (expandedExecId === execId) {
      setExpandedExecId(null);
      return;
    }
    setExpandedExecId(execId);
    if (!execDetails[execId]) {
      setLoadingExecId(execId);
      try {
        const detail = await api.getExecutionDetail(projectId, execId);
        setExecDetails((prev) => ({ ...prev, [execId]: detail }));
      } catch (err) {
        console.error("Failed to load execution detail", err);
      } finally {
        setLoadingExecId(null);
      }
    }
  }

  // Load existing workflow if any
  const loadLatestWorkflow = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.getWorkflows(projectId, 1, 0, requirementId);
      if (res.items.length > 0) {
        const detail = await api.getWorkflow(projectId, res.items[0].id);
        setActiveWorkflow(detail);
        const hist = await api.getWorkflowHistory(projectId, res.items[0].id);
        setEvents(hist.events);
      } else {
        setActiveWorkflow(null);
        setEvents([]);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load workflows.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId, requirementId]);

  useEffect(() => {
    queueMicrotask(() => void loadLatestWorkflow());
  }, [loadLatestWorkflow]);

  // Start new workflow
  async function handleStartWorkflow() {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const started = await api.startWorkflow(projectId, {
        requirement_id: requirementId,
        notes: `Started LangGraph workflow for "${requirementTitle}"`,
      });
      // Fetch full detail with generated cases
      const detail = await api.getWorkflow(projectId, started.id);
      setActiveWorkflow(detail);
      const hist = await api.getWorkflowHistory(projectId, started.id);
      setEvents(hist.events);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to start workflow.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // Submit human approval decision
  async function handleSubmitDecision(action: WorkflowApprovalAction) {
    if (!activeWorkflow) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const updated = await api.submitWorkflowApproval(projectId, activeWorkflow.id, {
        action,
        notes: decisionNotes.trim() || undefined,
        revision_instructions: action === "request_revision" ? revisionInstructions.trim() : undefined,
      });
      setActiveWorkflow(updated);
      const hist = await api.getWorkflowHistory(projectId, activeWorkflow.id);
      setEvents(hist.events);
      setActiveAction(null);
      setDecisionNotes("");
      setRevisionInstructions("");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to submit approval.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // Helper status color badges
  function getStatusBadge(status: string) {
    switch (status) {
      case "completed":
        return <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">COMPLETED</span>;
      case "paused_for_approval":
        return <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800 animate-pulse">PAUSED FOR APPROVAL</span>;
      case "rejected":
        return <span className="rounded-full bg-rose-100 px-3 py-1 text-xs font-bold text-rose-800">REJECTED</span>;
      case "failed":
        return <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-bold text-red-800">FAILED</span>;
      case "executing_tests":
        return <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-bold text-blue-800 animate-pulse">EXECUTING TESTS</span>;
      default:
        return <span className="rounded-full bg-purple-100 px-3 py-1 text-xs font-bold text-purple-800">{status.toUpperCase()}</span>;
    }
  }

  return (
    <div className="mt-6 rounded-2xl border border-violet-200 bg-gradient-to-b from-violet-50/50 to-white p-6 shadow-sm">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-violet-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-violet-600 text-xs font-black text-white">
              LG
            </span>
            <h4 className="text-base font-bold text-slate-900">
              LangGraph Multi-Agent Orchestration
            </h4>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Autonomous pipeline: Requirement Analysis → Test Generation → Human Approval → Execution → Historical RAG & Failure Analysis
          </p>
        </div>

        <div className="flex items-center gap-2">
          {activeWorkflow && getStatusBadge(activeWorkflow.status)}
          <button
            type="button"
            onClick={() => void loadLatestWorkflow()}
            disabled={isLoading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            title="Refresh status"
          >
            {isLoading ? "Refreshing…" : "↻ Refresh"}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <p className="font-semibold">Workflow Error</p>
          <p className="mt-1 text-xs">{errorMessage}</p>
        </div>
      )}

      {/* Pipeline Stepper Visualization */}
      <div className="my-6">
        <div className="grid grid-cols-2 gap-2 text-center text-xs font-semibold sm:grid-cols-5">
          <div className={`rounded-xl p-2.5 transition-colors ${activeWorkflow ? "bg-emerald-50 text-emerald-800 border border-emerald-200" : "bg-slate-100 text-slate-500"}`}>
            <span className="block text-sm">1. Analysis</span>
            <span className="text-[10px] text-slate-500">Requirement Agent</span>
          </div>
          <div className={`rounded-xl p-2.5 transition-colors ${activeWorkflow ? "bg-emerald-50 text-emerald-800 border border-emerald-200" : "bg-slate-100 text-slate-500"}`}>
            <span className="block text-sm">2. Generation</span>
            <span className="text-[10px] text-slate-500">Test Case Agent</span>
          </div>
          <div className={`rounded-xl p-2.5 transition-colors ${
            activeWorkflow?.status === "paused_for_approval"
              ? "bg-amber-100 text-amber-900 border-2 border-amber-400 font-bold animate-pulse"
              : activeWorkflow?.status === "completed" || activeWorkflow?.status === "executing_tests"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
              : activeWorkflow?.status === "rejected"
              ? "bg-rose-50 text-rose-800 border border-rose-200"
              : "bg-slate-100 text-slate-500"
          }`}>
            <span className="block text-sm">3. Human Approval</span>
            <span className="text-[10px] text-slate-500">Checkpoint / Pause</span>
          </div>
          <div className={`rounded-xl p-2.5 transition-colors ${
            activeWorkflow?.status === "executing_tests"
              ? "bg-blue-100 text-blue-900 border-2 border-blue-400 animate-pulse"
              : activeWorkflow?.status === "completed"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
              : "bg-slate-100 text-slate-500"
          }`}>
            <span className="block text-sm">4. Test Execution</span>
            <span className="text-[10px] text-slate-500">Execution Engine</span>
          </div>
          <div className={`rounded-xl p-2.5 transition-colors ${
            activeWorkflow?.failure_analysis_id
              ? "bg-amber-50 text-amber-800 border border-amber-300"
              : activeWorkflow?.status === "completed"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
              : "bg-slate-100 text-slate-500"
          }`}>
            <span className="block text-sm">5. Analysis & RAG</span>
            <span className="text-[10px] text-slate-500">Conditional Route</span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {!activeWorkflow && !isLoading && (
        <div className="rounded-xl border border-dashed border-violet-200 bg-white p-8 text-center">
          <p className="text-sm font-medium text-slate-700">No active workflow for this requirement</p>
          <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
            Clicking Start will trigger the LangGraph orchestration engine to analyze the requirement,
            synthesize structured test cases, and automatically pause at the Human Approval Checkpoint.
          </p>
          <button
            type="button"
            onClick={() => void handleStartWorkflow()}
            disabled={isSubmitting}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-violet-800 disabled:opacity-50"
          >
            {isSubmitting ? "Orchestrating agents…" : "⚡ Start LangGraph Multi-Agent Workflow"}
          </button>
        </div>
      )}

      {activeWorkflow && (
        <div className="space-y-6">
          {/* Metadata pill */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 bg-slate-50 rounded-xl px-4 py-2 border border-slate-200">
            <span>Workflow ID: <code className="font-mono text-slate-800">{activeWorkflow.id}</code></span>
            <span>Current Stage: <span className="font-semibold text-violet-700">{activeWorkflow.current_stage}</span></span>
            <span>Created: {new Date(activeWorkflow.created_at).toLocaleTimeString()}</span>
          </div>

          {/* CHECKPOINT INTERACTION: Paused for Human Approval */}
          {activeWorkflow.status === "paused_for_approval" && (
            <div className="rounded-2xl border-2 border-amber-300 bg-amber-50/70 p-5 shadow-sm">
              <div className="flex items-center gap-2 text-amber-900">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-xs text-white font-bold">!</span>
                <h5 className="font-bold text-sm">Human Approval Checkpoint Interruption</h5>
              </div>
              <p className="mt-1 text-xs text-amber-800">
                The agent has generated <strong>{activeWorkflow.generated_test_cases.length} test case(s)</strong>.
                Test execution is strictly suspended until authorized by human review.
              </p>

              {/* Generated Cases Preview */}
              <div className="mt-4 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-amber-900">Review Generated Cases:</p>
                <div className="max-h-60 overflow-y-auto space-y-2 pr-1">
                  {activeWorkflow.generated_test_cases.map((tc: TestCase) => (
                    <div key={tc.id} className="rounded-xl border border-amber-200 bg-white p-3 text-xs shadow-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900">{tc.title}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">{tc.test_type}</span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700">{tc.priority}</span>
                        </div>
                      </div>
                      {tc.description && <p className="mt-1 text-slate-600">{tc.description}</p>}
                      <div className="mt-2 text-[11px] text-slate-500">
                        <strong>Expected:</strong> {tc.expected_result}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Form */}
              <div className="mt-5 border-t border-amber-200 pt-4">
                {activeAction === "request_revision" ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-semibold text-slate-700">
                      Revision Instructions for Test Case Agent:
                      <textarea
                        value={revisionInstructions}
                        onChange={(e) => setRevisionInstructions(e.target.value)}
                        placeholder="e.g. Include negative cases for card expiration and CVV mismatch..."
                        className="mt-1 block w-full rounded-xl border border-slate-300 bg-white p-2.5 text-xs text-slate-900 focus:border-violet-500 focus:ring-1 focus:ring-violet-500"
                        rows={3}
                      />
                    </label>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void handleSubmitDecision("request_revision")}
                        disabled={isSubmitting || !revisionInstructions.trim()}
                        className="rounded-xl bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50"
                      >
                        {isSubmitting ? "Submitting…" : "Send Revision Request to Agent"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveAction(null)}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-2">
                      Optional Decision Notes:
                      <input
                        type="text"
                        value={decisionNotes}
                        onChange={(e) => setDecisionNotes(e.target.value)}
                        placeholder="e.g. Approved for staging automated test suite"
                        className="mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-violet-500"
                      />
                    </label>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => void handleSubmitDecision("approve")}
                        disabled={isSubmitting}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
                      >
                        ✓ Approve & Execute Tests
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveAction("request_revision")}
                        disabled={isSubmitting}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-amber-400 bg-amber-100 px-4 py-2.5 text-xs font-bold text-amber-900 hover:bg-amber-200 disabled:opacity-50"
                      >
                        ✎ Request Revision
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleSubmitDecision("reject")}
                        disabled={isSubmitting}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-rose-300 bg-rose-50 px-4 py-2.5 text-xs font-bold text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                      >
                        ✗ Reject & Terminate
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* REJECTION SCREEN */}
          {activeWorkflow.status === "rejected" && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
              <p className="font-bold text-sm">Workflow Rejected</p>
              <p className="mt-1">
                The test cases were rejected by human reviewer. Execution was prevented.
              </p>
              <button
                type="button"
                onClick={() => void handleStartWorkflow()}
                disabled={isSubmitting}
                className="mt-3 rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-violet-800"
              >
                Start New Workflow
              </button>
            </div>
          )}

          {/* EXECUTION RESULTS & EVIDENCE */}
          {activeWorkflow.executions && activeWorkflow.executions.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-3">
                <h5 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Execution Results & Evidence ({activeWorkflow.executions.length} runs)
                </h5>
                <span className="text-[11px] text-slate-500">
                  Playwright Autonomous Runner
                </span>
              </div>

              <div className="space-y-3">
                {activeWorkflow.executions.map((exec) => {
                  const isExpanded = expandedExecId === exec.id;
                  const detail = execDetails[exec.id];
                  const isLoadingThis = loadingExecId === exec.id;
                  const evidenceList = detail?.evidence || detail?.evidence_items || [];

                  return (
                    <div
                      key={exec.id}
                      className="rounded-xl border border-slate-200 bg-slate-50/70 overflow-hidden transition-all shadow-xs"
                    >
                      {/* Execution Header Summary */}
                      <div className="flex items-center justify-between p-3.5 bg-white border-b border-slate-100">
                        <div className="flex items-center gap-2.5">
                          <button
                            type="button"
                            onClick={() => void handleToggleExecution(exec.id)}
                            className="inline-flex items-center justify-center h-6 w-6 rounded-md bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-bold"
                            title={isExpanded ? "Collapse" : "Expand steps and evidence"}
                          >
                            {isExpanded ? "▲" : "▼"}
                          </button>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-slate-900">
                                Exec: {exec.id.slice(0, 8)}…
                              </span>
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
                              {exec.executor && (
                                <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                                  {exec.executor}
                                </span>
                              )}
                            </div>
                            {exec.error_message && (
                              <p className="mt-1 text-xs text-rose-600 font-medium">
                                ⚠ {exec.error_message}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {exec.summary?.duration_ms !== undefined && (
                            <span className="text-[11px] text-slate-500 font-mono">
                              {(exec.summary.duration_ms / 1000).toFixed(2)}s
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => void handleToggleExecution(exec.id)}
                            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            {isExpanded ? "Hide Details" : "Inspect Steps & Evidence"}
                          </button>
                        </div>
                      </div>

                      {/* Expanded Details Body */}
                      {isExpanded && (
                        <div className="p-4 space-y-4">
                          {isLoadingThis && (
                            <div className="flex items-center justify-center py-6 text-xs text-slate-500 gap-2">
                              <span className="animate-spin text-violet-600">🌀</span>
                              <span>Loading structured step execution results & captured evidence…</span>
                            </div>
                          )}

                          {!isLoadingThis && !detail && (
                            <p className="text-xs text-slate-500 py-2">
                              Unable to load detailed execution record.
                            </p>
                          )}

                          {!isLoadingThis && detail && (
                            <>
                              {/* Step-by-Step Actions */}
                              <div>
                                <h6 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-2">
                                  Executed Steps ({detail.step_results?.length || 0})
                                </h6>
                                {(!detail.step_results || detail.step_results.length === 0) ? (
                                  <p className="text-xs text-slate-400 italic">No structured step records captured.</p>
                                ) : (
                                  <div className="space-y-1.5">
                                    {detail.step_results.map((st, idx) => (
                                      <div
                                        key={idx}
                                        className={`rounded-lg p-2.5 text-xs border ${
                                          st.status === "passed"
                                            ? "bg-white border-emerald-200"
                                            : st.status === "failed"
                                            ? "bg-rose-50 border-rose-200"
                                            : "bg-amber-50 border-amber-200"
                                        }`}
                                      >
                                        <div className="flex items-center justify-between">
                                          <div className="flex items-center gap-2">
                                            <span className="font-mono text-slate-400 font-bold text-[10px]">
                                              #{idx + 1}
                                            </span>
                                            <span className="rounded bg-slate-800 text-white px-1.5 py-0.5 text-[10px] font-mono uppercase">
                                              {st.action}
                                            </span>
                                            <span
                                              className={`font-semibold ${
                                                st.status === "passed"
                                                  ? "text-emerald-700"
                                                  : "text-rose-700"
                                              }`}
                                            >
                                              {st.status.toUpperCase()}
                                            </span>
                                          </div>
                                          {st.duration_ms !== undefined && (
                                            <span className="text-[10px] font-mono text-slate-500">
                                              {st.duration_ms}ms
                                            </span>
                                          )}
                                        </div>

                                        {st.expected && (
                                          <div className="mt-1 text-[11px] text-slate-600">
                                            <span className="font-medium text-slate-500">Expected:</span> {st.expected}
                                          </div>
                                        )}
                                        {st.actual && (
                                          <div className="text-[11px] text-slate-600">
                                            <span className="font-medium text-slate-500">Actual:</span> {st.actual}
                                          </div>
                                        )}
                                        {st.error_message && (
                                          <div className="mt-1 text-[11px] font-mono text-rose-700 bg-rose-100/60 p-1.5 rounded">
                                            {st.error_message}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {/* Captured Evidence (Screenshots & Logs) */}
                              {evidenceList.length > 0 && (
                                <div>
                                  <h6 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-2">
                                    Captured Evidence ({evidenceList.length} artifacts)
                                  </h6>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                                    {evidenceList.map((ev) => {
                                      const isImage =
                                        ev.evidence_type === "screenshot" ||
                                        ev.content_type?.startsWith("image/") ||
                                        ev.uri.endsWith(".png") ||
                                        ev.uri.endsWith(".jpg");

                                      const downloadUrl = api.getEvidenceDownloadUrl(projectId, exec.id, ev.id);

                                      if (isImage) {
                                        return (
                                          <div
                                            key={ev.id}
                                            className="group relative rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs hover:border-violet-400 transition-all cursor-pointer"
                                            onClick={() => setSelectedScreenshotUrl(downloadUrl)}
                                          >
                                            <div className="h-32 bg-slate-900 flex items-center justify-center overflow-hidden">
                                              <img
                                                src={downloadUrl}
                                                alt={ev.label || "Execution Screenshot"}
                                                className="h-full w-full object-cover group-hover:scale-105 transition-transform"
                                                loading="lazy"
                                              />
                                            </div>
                                            <div className="p-2 text-center bg-white border-t border-slate-100">
                                              <p className="text-[11px] font-semibold text-slate-800 truncate">
                                                📷 {ev.label || "Failure Screenshot"}
                                              </p>
                                              <p className="text-[10px] text-violet-600 font-medium">Click to zoom</p>
                                            </div>
                                          </div>
                                        );
                                      }

                                      return (
                                        <div
                                          key={ev.id}
                                          className="rounded-xl border border-slate-200 bg-white p-3 shadow-xs"
                                        >
                                          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                                            <span>📄</span>
                                            <span className="truncate">{ev.label || ev.evidence_type}</span>
                                          </div>
                                          <p className="mt-1 text-[10px] font-mono text-slate-500 truncate">
                                            {ev.uri}
                                          </p>
                                          <a
                                            href={downloadUrl}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="mt-2 inline-block text-[11px] font-medium text-violet-600 hover:text-violet-800 underline"
                                          >
                                            Download Artifact →
                                          </a>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}

                              {/* Associated Defects */}
                              {detail.defects && detail.defects.length > 0 && (
                                <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3">
                                  <h6 className="text-[11px] font-bold uppercase tracking-wider text-rose-800 mb-2">
                                    Auto-Created Defect ({detail.defects.length})
                                  </h6>
                                  {detail.defects.map((def) => (
                                    <div key={def.id} className="rounded-lg bg-white border border-rose-200 p-2.5 text-xs">
                                      <div className="flex items-center justify-between">
                                        <span className="font-bold text-rose-900">{def.title}</span>
                                        <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-bold text-rose-800 uppercase">
                                          {def.severity}
                                        </span>
                                      </div>
                                      <p className="mt-1 text-slate-600 text-[11px]">{def.description}</p>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* HISTORICAL RAG & FAILURE ANALYSIS (Conditional Branch Result) */}
          {activeWorkflow.failure_analysis && (
            <div className="rounded-2xl border-2 border-indigo-200 bg-gradient-to-b from-indigo-50/50 to-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-xs text-white font-bold">AI</span>
                  <h5 className="font-bold text-sm text-slate-900">Failure Analysis Agent Diagnosis</h5>
                </div>
                <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-bold text-indigo-800">
                  Confidence: {String(activeWorkflow.failure_analysis.confidence).toUpperCase()}
                </span>
              </div>

              {/* RAG Context metadata */}
              {Boolean(activeWorkflow.metadata?.retrieval_status) && (
                <div className="mt-2 text-xs text-slate-500">
                  <span>Historical Qdrant RAG: </span>
                  <span className="font-semibold text-indigo-700">
                    {String(activeWorkflow.metadata?.retrieval_status)}
                  </span>
                  {activeWorkflow.metadata?.historical_candidates_count !== undefined && (
                    <span className="ml-1 text-slate-400">
                      ({String(activeWorkflow.metadata.historical_candidates_count)} matching precedent(s) found)
                    </span>
                  )}
                </div>
              )}

              <div className="mt-4 space-y-3 text-xs">
                <div>
                  <span className="font-semibold text-slate-700">Category: </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-800">
                    {activeWorkflow.failure_analysis.failure_category}
                  </span>
                </div>
                <div>
                  <span className="font-semibold text-slate-700">Root Cause Hypothesis: </span>
                  <p className="mt-0.5 text-slate-800 leading-relaxed bg-white p-2.5 rounded-xl border border-indigo-100">
                    {activeWorkflow.failure_analysis.likely_root_cause}
                  </p>
                </div>
                {activeWorkflow.failure_analysis.recommended_debugging_steps?.length > 0 && (
                  <div>
                    <span className="font-semibold text-slate-700">Recommended Debugging Actions:</span>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-600">
                      {activeWorkflow.failure_analysis.recommended_debugging_steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeWorkflow.status === "completed" && !activeWorkflow.failure_analysis_id && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800">
              <p className="font-bold text-sm">✓ All Test Executions Passed</p>
              <p className="mt-1">
                Zero test failures occurred. Per conditional graph routing, Historical RAG retrieval and Failure Analysis were skipped.
              </p>
            </div>
          )}

          {/* Audit Event History Accordion */}
          <div className="border-t border-slate-200 pt-3">
            <button
              type="button"
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center justify-between w-full text-xs font-semibold text-slate-600 hover:text-slate-900"
            >
              <span>Workflow Stage Transitions & Audit Log ({events.length} events)</span>
              <span>{showHistory ? "▲ Hide" : "▼ Show"}</span>
            </button>

            {showHistory && (
              <div className="mt-3 space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {events.map((evt) => (
                  <div key={evt.id} className="flex items-start justify-between rounded-lg bg-slate-50 px-3 py-2 text-[11px] text-slate-600 border border-slate-100">
                    <div>
                      <span className="font-semibold text-violet-700">[{evt.stage}]</span>{" "}
                      <span className="font-medium text-slate-800">{evt.event_type}</span>:{" "}
                      <span>{evt.message || "Stage event"}</span>
                    </div>
                    <span className="font-mono text-slate-400 text-[10px] whitespace-nowrap ml-2">
                      {new Date(evt.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Screenshot Zoom Modal */}
          {selectedScreenshotUrl && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-xs"
              onClick={() => setSelectedScreenshotUrl(null)}
            >
              <div
                className="relative max-w-5xl w-full max-h-[90vh] bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 shadow-2xl flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700 text-xs font-semibold text-slate-200">
                  <span className="flex items-center gap-1.5">
                    <span>📷</span>
                    <span>Execution Screenshot & Evidence Inspection</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <a
                      href={selectedScreenshotUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200"
                    >
                      Open Original ↗
                    </a>
                    <button
                      type="button"
                      onClick={() => setSelectedScreenshotUrl(null)}
                      className="h-6 w-6 flex items-center justify-center rounded bg-rose-500/20 text-rose-300 hover:bg-rose-500 hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <div className="p-4 overflow-auto flex items-center justify-center bg-black/50">
                  <img
                    src={selectedScreenshotUrl}
                    alt="Execution High-Res Screenshot"
                    className="max-h-[75vh] w-auto rounded-lg border border-slate-800 object-contain shadow-lg"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
