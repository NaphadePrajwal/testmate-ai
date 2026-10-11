import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { GeneratedTestCasesResponse, Priority, ReviewStatus, TestCase, TestCaseUpdateInput, TestType } from "../types/api";
import { ExecutionModal } from "./ExecutionModal";

interface TestCaseGenerationPanelProps {
  projectId: string;
  requirementId: string;
  requirementTitle: string;
}

export function TestCaseGenerationPanel({
  projectId,
  requirementId,
  requirementTitle,
}: TestCaseGenerationPanelProps) {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);
  const [generationSummary, setGenerationSummary] = useState<string | null>(null);
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [filterStatus, setFilterStatus] = useState<ReviewStatus | "all">("all");
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [editForm, setEditForm] = useState<TestCaseUpdateInput>({});
  const [executingTestCase, setExecutingTestCase] = useState<TestCase | null>(null);

  const loadTestCases = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.getRequirementTestCases(projectId, requirementId, 100);
      setTestCases(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load test cases.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId, requirementId]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadTestCases();
    });
  }, [loadTestCases]);

  async function handleGenerate() {
    setIsGenerating(true);
    setError(null);
    setSuccessNotice(null);
    try {
      const response: GeneratedTestCasesResponse = await api.generateRequirementTestCases(projectId, requirementId);
      setTestCases(response.items);
      setGenerationSummary(response.requirement_coverage_summary);
      setAssumptions(response.assumptions);
      setSuccessNotice(`Successfully generated ${response.total_generated} test cases!`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate test cases.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleApprove(testCase: TestCase) {
    try {
      const updated = await api.approveRequirementTestCase(projectId, requirementId, testCase.id);
      setTestCases((prev) => prev.map((tc) => (tc.id === updated.id ? updated : tc)));
      setSuccessNotice(`Test case “${updated.title}” approved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve test case.");
    }
  }

  async function handleReject(testCase: TestCase) {
    try {
      const updated = await api.rejectRequirementTestCase(projectId, requirementId, testCase.id);
      setTestCases((prev) => prev.map((tc) => (tc.id === updated.id ? updated : tc)));
      setSuccessNotice(`Test case “${updated.title}” rejected.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject test case.");
    }
  }

  function startEditing(testCase: TestCase) {
    setEditingCase(testCase);
    setEditForm({
      title: testCase.title,
      description: testCase.description,
      expected_result: testCase.expected_result,
      priority: testCase.priority,
      test_type: testCase.test_type,
    });
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCase) return;
    try {
      const updated = await api.updateRequirementTestCase(projectId, requirementId, editingCase.id, editForm);
      setTestCases((prev) => prev.map((tc) => (tc.id === updated.id ? updated : tc)));
      setEditingCase(null);
      setSuccessNotice(`Test case “${updated.title}” updated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update test case.");
    }
  }

  const filteredCases = testCases.filter((tc) => {
    if (filterStatus === "all") return true;
    return tc.review_status === filterStatus;
  });

  return (
    <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50/50 p-6 shadow-inner">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-violet-600 animate-pulse"></span>
            <h4 className="text-base font-bold text-slate-900">AI Test Case Generation & Review</h4>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Generate and review positive, negative, and edge test cases for “{requirementTitle}”.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={isGenerating}
          className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 disabled:opacity-50"
        >
          {isGenerating ? (
            <>
              <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
              </svg>
              <span>Generating with AI…</span>
            </>
          ) : (
            <>
              <span>⚡ Generate Test Cases</span>
            </>
          )}
        </button>
      </div>

      {successNotice && (
        <div role="status" className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {successNotice}
        </div>
      )}

      {error && (
        <div role="alert" className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {generationSummary && (
        <div className="mt-4 rounded-xl border border-violet-100 bg-violet-50/60 p-4 text-xs text-violet-900">
          <p className="font-semibold text-violet-950">Coverage Summary:</p>
          <p className="mt-1">{generationSummary}</p>
          {assumptions.length > 0 && (
            <div className="mt-2">
              <span className="font-medium text-violet-950">Assumptions: </span>
              <span>{assumptions.join("; ")}</span>
            </div>
          )}
        </div>
      )}

      {/* Filter Tabs */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex gap-2">
          {(["all", "pending", "approved", "rejected"] as const).map((status) => {
            const count = status === "all" ? testCases.length : testCases.filter((tc) => tc.review_status === status).length;
            return (
              <button
                key={status}
                type="button"
                onClick={() => setFilterStatus(status)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition-colors ${
                  filterStatus === status
                    ? "bg-slate-900 text-white"
                    : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {status} ({count})
              </button>
            );
          })}
        </div>
        <span className="text-xs text-slate-500">{filteredCases.length} test case(s) displayed</span>
      </div>

      {/* Test Case Edit Modal/Inline Form */}
      {editingCase && (
        <div className="mt-4 rounded-xl border border-slate-300 bg-white p-5 shadow-md">
          <h5 className="font-bold text-slate-900 text-sm">Edit Test Case</h5>
          <form onSubmit={handleSaveEdit} className="mt-4 space-y-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700">Title</label>
              <input
                type="text"
                value={editForm.title || ""}
                onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-xs"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700">Description</label>
              <textarea
                value={editForm.description || ""}
                onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-xs"
                rows={2}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700">Priority</label>
                <select
                  value={editForm.priority || "medium"}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, priority: e.target.value as Priority }))}
                  className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-xs"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700">Type</label>
                <select
                  value={editForm.test_type || "web"}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, test_type: e.target.value as TestType }))}
                  className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-xs"
                >
                  <option value="web">Web</option>
                  <option value="api">API</option>
                  <option value="manual">Manual</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700">Expected Result</label>
              <textarea
                value={editForm.expected_result || ""}
                onChange={(e) => setEditForm((prev) => ({ ...prev, expected_result: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-xs"
                rows={2}
                required
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditingCase(null)}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700"
              >
                Save Changes (Keeps Pending)
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Test Cases List */}
      {isLoading ? (
        <div className="py-8 text-center text-xs text-slate-500">Loading test cases…</div>
      ) : filteredCases.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">
          No test cases found in this view. Click "Generate Test Cases" above to create test specifications.
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {filteredCases.map((tc) => (
            <div
              key={tc.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h5 className="font-bold text-slate-900 text-sm">{tc.title}</h5>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                        tc.review_status === "approved"
                          ? "bg-emerald-100 text-emerald-800"
                          : tc.review_status === "rejected"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {tc.review_status}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                      {tc.priority}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                      {tc.test_type}
                    </span>
                    <span className="text-[10px] text-slate-400">v{tc.version}</span>
                  </div>
                  {tc.description && <p className="mt-1 text-xs text-slate-600">{tc.description}</p>}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {tc.review_status === "pending" && (
                    <>
                      <button
                        type="button"
                        onClick={() => startEditing(tc)}
                        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleApprove(tc)}
                        className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                      >
                        ✓ Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleReject(tc)}
                        className="rounded-lg bg-rose-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-rose-700"
                      >
                        ✕ Reject
                      </button>
                    </>
                  )}
                  {tc.review_status === "approved" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-emerald-700">✓ Approved</span>
                      <button
                        type="button"
                        onClick={() => setExecutingTestCase(tc)}
                        className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
                      >
                        ▶ Run Test
                      </button>
                    </div>
                  )}
                  {tc.review_status === "rejected" && (
                    <span className="text-xs font-semibold text-rose-700">✕ Rejected</span>
                  )}
                </div>
              </div>

              {/* Preconditions */}
              {tc.preconditions.length > 0 && (
                <div className="mt-3 text-xs text-slate-600">
                  <span className="font-semibold text-slate-700">Preconditions: </span>
                  <span>{tc.preconditions.join("; ")}</span>
                </div>
              )}

              {/* Steps */}
              {tc.steps.length > 0 && (
                <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-3">
                  <span className="text-xs font-semibold text-slate-700">Test Steps:</span>
                  <div className="space-y-1 pl-2">
                    {tc.steps.map((step, idx) => (
                      <div key={idx} className="text-xs text-slate-700 flex items-start gap-2">
                        <span className="font-bold text-slate-400">{idx + 1}.</span>
                        <div className="flex-1">
                          <span>{step.action}</span>
                          {step.expected_result && (
                            <span className="text-slate-500 italic block mt-0.5">↳ {step.expected_result}</span>
                          )}
                          {step.data && Object.keys(step.data).length > 0 && (
                            <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                              Data: {JSON.stringify(step.data)}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expected Result */}
              <div className="mt-3 border-t border-slate-100 pt-2 text-xs">
                <span className="font-semibold text-slate-700">Expected Result: </span>
                <span className="text-slate-700">{tc.expected_result}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {executingTestCase && (
        <ExecutionModal
          projectId={projectId}
          testCase={executingTestCase}
          isOpen={true}
          onClose={() => setExecutingTestCase(null)}
        />
      )}
    </div>
  );
}
