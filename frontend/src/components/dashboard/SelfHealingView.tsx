import { useEffect, useState, useMemo, useCallback } from "react";
import { api } from "../../services/api";
import type { HealingProposal, HealingStatus, CandidateValidationResult } from "../../types/api";

interface SelfHealingViewProps {
  projectId: string;
  projectName: string;
}

export function SelfHealingView({ projectId, projectName }: SelfHealingViewProps) {
  const [proposals, setProposals] = useState<HealingProposal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspect Modal State
  const [selectedProposal, setSelectedProposal] = useState<HealingProposal | null>(null);
  const [actionNotes, setActionNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadProposals = useCallback(() => {
    setIsLoading(true);
    setError(null);
    api
      .getHealingProposals(projectId, 100, 0)
      .then((res) => setProposals(res.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load healing proposals."))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadProposals());
  }, [loadProposals]);

  const filteredProposals = useMemo(() => {
    return proposals.filter((p) => {
      if (statusFilter !== "all" && p.status !== statusFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const title = (p.test_case_title || "").toLowerCase();
        const origSel = JSON.stringify(p.original_selector).toLowerCase();
        const propSel = JSON.stringify(p.proposed_selector || {}).toLowerCase();
        const id = p.id.toLowerCase();
        return title.includes(q) || origSel.includes(q) || propSel.includes(q) || id.includes(q);
      }
      return true;
    });
  }, [proposals, statusFilter, searchQuery]);

  // Statistics
  const stats = useMemo(() => {
    const total = proposals.length;
    const awaiting = proposals.filter((p) => p.status === "awaiting_approval" || p.status === "proposed").length;
    const healed = proposals.filter((p) => p.status === "healed").length;
    const rejected = proposals.filter((p) => p.status === "rejected").length;
    const failed = proposals.filter((p) => p.status === "failed").length;
    const resolved = healed + rejected + failed;
    const successRate = resolved > 0 ? Math.round((healed / resolved) * 100) : 0;
    return { total, awaiting, healed, rejected, failed, successRate };
  }, [proposals]);

  const handleApprove = async () => {
    if (!selectedProposal) return;
    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await api.approveHealingProposal(projectId, selectedProposal.id, actionNotes);
      setSelectedProposal(updated);
      setProposals((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (updated.status === "healed") {
        setActionSuccess("Proposal approved and repair applied successfully! The re-execution passed all assertions.");
      } else if (updated.status === "failed") {
        setActionError("Repair was applied, but the re-execution failed or assertions did not pass. Healing marked as failed.");
      } else {
        setActionSuccess("Proposal approved successfully.");
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve proposal.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!selectedProposal) return;
    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await api.rejectHealingProposal(projectId, selectedProposal.id, actionNotes);
      setSelectedProposal(updated);
      setProposals((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionSuccess("Proposal was rejected. Original test definition was safely preserved.");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject proposal.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusBadge = (status: HealingStatus) => {
    switch (status) {
      case "awaiting_approval":
      case "proposed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
            Awaiting Approval
          </span>
        );
      case "healed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Healed
          </span>
        );
      case "rejected":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Rejected
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
            Healing Failed
          </span>
        );
      case "validating":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Validating…
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const formatSelector = (selector: Record<string, unknown> | null | undefined): string => {
    if (!selector) return "None";
    if (selector.role && selector.name) {
      return `getByRole('${selector.role}', { name: '${selector.name}' })`;
    }
    if (selector.test_id) {
      return `getByTestId('${selector.test_id}')`;
    }
    if (selector.label) {
      return `getByLabel('${selector.label}')`;
    }
    if (selector.placeholder) {
      return `getByPlaceholder('${selector.placeholder}')`;
    }
    if (selector.text) {
      return `getByText('${selector.text}')`;
    }
    if (selector.selector) {
      return `locator('${selector.selector}')`;
    }
    return JSON.stringify(selector);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-500">
        <span className="text-3xl animate-spin text-violet-600 mb-3">🌀</span>
        <p className="text-sm font-medium">Loading self-healing proposals for {projectName}…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <h4 className="font-bold text-base text-rose-900">Self-Healing Unavailable</h4>
        <p className="mt-1">{error}</p>
        <button
          onClick={loadProposals}
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
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-violet-700">
            <span>Playwright Automation Resilience</span>
            <span>•</span>
            <span className="text-slate-500">{projectName}</span>
          </div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Self-Healing Test Locators
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Automated selector failure recovery with live browser candidate validation, transparent ranking, and human-in-the-loop approval.
          </p>
        </div>
        <button
          onClick={loadProposals}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition"
        >
          🔄 Refresh Proposals
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Proposals</p>
          <p className="mt-2 text-2xl font-extrabold text-slate-900">{stats.total}</p>
          <p className="mt-1 text-[11px] text-slate-400">All detected failures</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-600">Awaiting Review</p>
          <p className="mt-2 text-2xl font-extrabold text-amber-600">{stats.awaiting}</p>
          <p className="mt-1 text-[11px] text-amber-700">Needs human approval</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Successfully Healed</p>
          <p className="mt-2 text-2xl font-extrabold text-emerald-600">{stats.healed}</p>
          <p className="mt-1 text-[11px] text-emerald-700">Repairs passed</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Rejected</p>
          <p className="mt-2 text-2xl font-extrabold text-slate-700">{stats.rejected}</p>
          <p className="mt-1 text-[11px] text-slate-400">Original preserved</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-rose-600">Failed Repairs</p>
          <p className="mt-2 text-2xl font-extrabold text-rose-600">{stats.failed}</p>
          <p className="mt-1 text-[11px] text-rose-700">Retry assertion failed</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
          <p className="text-xs font-semibold uppercase tracking-wider text-violet-600">Resolution Rate</p>
          <p className="mt-2 text-2xl font-extrabold text-violet-700">{stats.successRate}%</p>
          <p className="mt-1 text-[11px] text-violet-600">Healing pass rate</p>
        </div>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold text-slate-500 mr-1">Status:</span>
          {[
            { id: "all", label: "All Proposals" },
            { id: "awaiting_approval", label: "Awaiting Review" },
            { id: "healed", label: "Healed" },
            { id: "rejected", label: "Rejected" },
            { id: "failed", label: "Failed" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${
                statusFilter === tab.id
                  ? "bg-violet-700 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <input
            type="text"
            placeholder="Search test, selector, or ID…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-800 placeholder-slate-400 shadow-2xs hover:border-slate-400 focus:border-violet-600 focus:outline-hidden"
          />
        </div>
      </div>

      {/* Proposals Table */}
      {filteredProposals.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-xs">
          <span className="text-4xl">🩺</span>
          <h3 className="mt-3 text-base font-bold text-slate-900">No Healing Proposals Found</h3>
          <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
            {statusFilter === "all"
              ? "All test locators are robust or no selector failures have been detected yet during Playwright executions."
              : `No proposals match the filter "${statusFilter}".`}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                <tr>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4">Test Case</th>
                  <th className="py-3.5 px-4">Failed Step</th>
                  <th className="py-3.5 px-4">Original Selector</th>
                  <th className="py-3.5 px-4">Proposed Replacement</th>
                  <th className="py-3.5 px-4">Confidence</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800">
                {filteredProposals.map((proposal) => (
                  <tr key={proposal.id} className="hover:bg-slate-50 transition">
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {getStatusBadge(proposal.status)}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="font-bold text-slate-900 max-w-xs truncate">
                        {proposal.test_case_title || `Test Case #${proposal.test_case_id.slice(0, 8)}`}
                      </div>
                      <div className="font-mono text-[10px] text-slate-400">ID: {proposal.id.slice(0, 8)}</div>
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span className="font-mono text-slate-600 font-semibold">Step {proposal.failed_step_index + 1}</span>
                      <span className="ml-1.5 px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded text-[10px] uppercase font-bold">
                        {proposal.failed_action_type}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-[11px] text-rose-700 max-w-xs truncate">
                      {formatSelector(proposal.original_selector)}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-[11px] text-emerald-700 max-w-xs truncate font-semibold">
                      {proposal.proposed_selector ? formatSelector(proposal.proposed_selector) : (
                        <span className="text-slate-400 italic font-normal">No candidate validated</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {proposal.confidence_score > 0 ? (
                        <div className="flex items-center gap-2">
                          <div className="w-14 bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200">
                            <div
                              className={`h-full rounded-full ${
                                proposal.confidence_score >= 80
                                  ? "bg-emerald-500"
                                  : proposal.confidence_score >= 50
                                  ? "bg-amber-500"
                                  : "bg-rose-500"
                              }`}
                              style={{ width: `${proposal.confidence_score}%` }}
                            />
                          </div>
                          <span className="font-bold text-slate-800 text-[11px]">
                            {proposal.confidence_score}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-400 text-[11px]">N/A</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <button
                        onClick={() => {
                          setSelectedProposal(proposal);
                          setActionNotes("");
                          setActionSuccess(null);
                          setActionError(null);
                        }}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-violet-700 shadow-2xs hover:bg-violet-50 transition"
                      >
                        Inspect Proposal →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Proposal Review Modal */}
      {selectedProposal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs"
          onClick={() => setSelectedProposal(null)}
        >
          <div
            className="bg-white border border-slate-200 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🩺</span>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-slate-900">
                      Review Self-Healing Proposal
                    </h3>
                    {getStatusBadge(selectedProposal.status)}
                  </div>
                  <p className="text-xs text-slate-500 font-mono mt-0.5">
                    Proposal ID: {selectedProposal.id}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedProposal(null)}
                className="h-7 w-7 rounded-lg bg-slate-200 text-slate-600 hover:bg-slate-300 flex items-center justify-center text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 text-xs text-slate-700">
              {/* Alert Feedback Messages */}
              {actionSuccess && (
                <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 font-medium">
                  {actionSuccess}
                </div>
              )}
              {actionError && (
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 font-medium">
                  {actionError}
                </div>
              )}

              {/* Step & Context Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Test Case</div>
                  <div className="text-slate-900 font-bold text-sm">
                    {selectedProposal.test_case_title || selectedProposal.test_case_id}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    Failed at Step {selectedProposal.failed_step_index + 1} ({selectedProposal.failed_action_type.toUpperCase()})
                  </div>
                </div>
                <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Page Context</div>
                  <div className="text-slate-900 font-mono text-xs truncate" title={selectedProposal.page_url || ""}>
                    {selectedProposal.page_url || "N/A"}
                  </div>
                  <div className="text-slate-500 text-xs truncate mt-1">
                    {selectedProposal.page_title || "N/A"}
                  </div>
                </div>
              </div>

              {/* Selector Comparison */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 bg-rose-50/50 border border-rose-200 rounded-xl">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-rose-800 flex items-center gap-1.5">
                      ❌ Broken Selector
                    </span>
                    <span className="text-[10px] font-mono uppercase bg-rose-100 text-rose-700 px-1.5 py-0.5 rounded">Original</span>
                  </div>
                  <pre className="p-3 bg-white rounded-lg border border-rose-200 text-rose-800 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap">
                    {formatSelector(selectedProposal.original_selector)}
                  </pre>
                  {selectedProposal.original_error && (
                    <div className="mt-2 text-[11px] text-rose-700 bg-rose-100/60 p-2.5 rounded border border-rose-200 font-mono line-clamp-3">
                      {selectedProposal.original_error}
                    </div>
                  )}
                </div>

                <div className="p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-emerald-800 flex items-center gap-1.5">
                      ✅ Proposed Replacement
                    </span>
                    <span className="text-[10px] font-mono uppercase bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">
                      {selectedProposal.proposed_selector_type || "Semantic"}
                    </span>
                  </div>
                  <pre className="p-3 bg-white rounded-lg border border-emerald-200 text-emerald-800 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap font-semibold">
                    {selectedProposal.proposed_selector ? formatSelector(selectedProposal.proposed_selector) : "No candidate validated"}
                  </pre>
                  {selectedProposal.ranking_explanation && (
                    <div className="mt-2 text-[11px] text-emerald-800 bg-emerald-100/60 p-2.5 rounded border border-emerald-200">
                      <span className="font-bold">Evaluation:</span> {selectedProposal.ranking_explanation}
                    </div>
                  )}
                </div>
              </div>

              {/* Candidate Validation Results */}
              {selectedProposal.candidate_validations && selectedProposal.candidate_validations.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                    Live Live Candidate Evaluation Signals ({selectedProposal.candidate_validations.length})
                  </h4>
                  <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 text-slate-600 text-[11px] font-bold border-b border-slate-200 uppercase tracking-wider">
                        <tr>
                          <th className="py-2.5 px-3">Candidate</th>
                          <th className="py-2.5 px-3">Type</th>
                          <th className="py-2.5 px-3">Matches</th>
                          <th className="py-2.5 px-3">Actionable</th>
                          <th className="py-2.5 px-3">Score</th>
                          <th className="py-2.5 px-3">Signals & Reasons</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 text-slate-700">
                        {selectedProposal.candidate_validations.map((c: CandidateValidationResult, i: number) => (
                          <tr key={i} className="hover:bg-slate-50">
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-900 font-semibold">
                              {formatSelector(c.candidate)}
                            </td>
                            <td className="py-2.5 px-3">
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-700 font-mono">
                                {c.candidate_type}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              {c.match_count === 1 ? (
                                <span className="text-emerald-700 font-bold">1 (Unique)</span>
                              ) : c.match_count > 1 ? (
                                <span className="text-amber-700 font-bold">{c.match_count} (Ambiguous)</span>
                              ) : (
                                <span className="text-slate-400">0</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3">
                              {c.is_actionable ? (
                                <span className="text-emerald-700 font-semibold">Yes</span>
                              ) : (
                                <span className="text-slate-400">No</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-bold text-slate-900">{c.score}</td>
                            <td className="py-2.5 px-3 text-[11px] text-slate-500">
                              {c.reasons && c.reasons.length > 0 ? c.reasons.join(", ") : "Standard match"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Human Approval Controls */}
              {selectedProposal.status === "awaiting_approval" || selectedProposal.status === "proposed" ? (
                <div className="p-4 bg-violet-50/60 border border-violet-200 rounded-xl space-y-3">
                  <div className="text-violet-900 font-bold text-xs uppercase tracking-wider">
                    Human Review & Controlled Approval
                  </div>
                  <p className="text-[11px] text-violet-800 leading-relaxed">
                    Approving will safely update the test step with the proposed selector, preserve previous selector history, and automatically trigger a re-execution to verify that both the interaction and assertions pass.
                  </p>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Review Notes (optional)
                    </label>
                    <textarea
                      value={actionNotes}
                      onChange={(e) => setActionNotes(e.target.value)}
                      placeholder="Add rationale, bug ticket link, or verification notes…"
                      className="w-full px-3 py-2 text-xs bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:border-violet-600"
                      rows={2}
                    />
                  </div>
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <button
                      onClick={handleReject}
                      disabled={isSubmitting}
                      className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-rose-700 shadow-xs hover:bg-rose-50 transition"
                    >
                      ✕ Reject Proposal
                    </button>
                    <button
                      onClick={handleApprove}
                      disabled={isSubmitting || !selectedProposal.proposed_selector}
                      className="rounded-xl bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition"
                    >
                      {isSubmitting ? "Applying & Re-executing…" : "✓ Approve & Re-execute Test"}
                    </button>
                  </div>
                </div>
              ) : (
                /* Audit Trail for Resolved Proposals */
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                  <div className="text-xs font-bold text-slate-800 uppercase tracking-wider">Decision Audit Trail</div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
                    <div>
                      <span className="text-slate-500 block">Decision:</span>
                      <span className="font-bold text-slate-900 capitalize">{selectedProposal.approval_decision || selectedProposal.status}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Approved At:</span>
                      <span className="text-slate-700">{selectedProposal.approved_at ? new Date(selectedProposal.approved_at).toLocaleString() : "N/A"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Applied At:</span>
                      <span className="text-slate-700">{selectedProposal.applied_at ? new Date(selectedProposal.applied_at).toLocaleString() : "N/A"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Retry Execution:</span>
                      <span className="font-mono text-violet-700 font-bold">{selectedProposal.retry_execution_id ? selectedProposal.retry_execution_id.slice(0, 8) : "None"}</span>
                    </div>
                  </div>
                  {selectedProposal.approval_notes && (
                    <div className="text-[11px] text-slate-600 pt-1">
                      <span className="font-bold text-slate-500">Notes:</span> {selectedProposal.approval_notes}
                    </div>
                  )}
                  {selectedProposal.failure_reason && (
                    <div className="text-[11px] text-rose-700 pt-1">
                      <span className="font-bold text-rose-600">Failure Reason:</span> {selectedProposal.failure_reason}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
              <span>Created {new Date(selectedProposal.created_at).toLocaleString()}</span>
              <button
                onClick={() => setSelectedProposal(null)}
                className="rounded-xl border border-slate-300 bg-white px-4 py-1.5 font-bold text-slate-700 hover:bg-slate-100 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
