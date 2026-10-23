import type {
  EvidenceListResponse,
  ExecutionDetailResponse,
  ExecutionFailureContext,
  ExecutionListResponse,
  ExecutionTriggerInput,
  GeneratedTestCasesResponse,
  HealthResponse,
  Project,
  ProjectInput,
  ProjectListResponse,
  Requirement,
  RequirementAnalysisResponse,
  RequirementInput,
  RequirementListResponse,
  ReviewStatus,
  TestCase,
  TestCaseListResponse,
  TestCaseUpdateInput,
  TestExecution,
  FailureAnalysis,
  FailureAnalysisListResponse,
  WorkflowApprovalInput,
  WorkflowDetailResponse,
  WorkflowExecution,
  WorkflowHistoryResponse,
  WorkflowListResponse,
  WorkflowStartInput,
  ProjectAnalyticsResponse,
  ProjectTraceabilityResponse,
  ProjectReportResponse,
  Defect,
  DefectListResponse,
  DefectUpdateInput,
  HealingProposal,
  HealingProposalListResponse,
} from "../types/api";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item && typeof item === "object" && "msg" in item ? String(item.msg) : "Invalid request.").join(" ");
  }
  return "The API request failed.";
}

function collectionPath(path: string, limit: number, offset: number, extraParams: Record<string, string> = {}): string {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), ...extraParams });
  return `${path}?${params.toString()}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers }
    });
  } catch {
    throw new ApiError("The TestMate API is unreachable. Start the backend and try again.");
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(await response.json().catch(() => null)), response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  getHealth: (): Promise<HealthResponse> => request<HealthResponse>("/health"),
  getProjects: (limit = 20, offset = 0): Promise<ProjectListResponse> => request<ProjectListResponse>(collectionPath("/projects", limit, offset)),
  createProject: (payload: ProjectInput): Promise<Project> => request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (projectId: string, payload: Partial<ProjectInput>): Promise<Project> => request<Project>(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  getRequirements: (projectId: string, limit = 20, offset = 0): Promise<RequirementListResponse> => request<RequirementListResponse>(collectionPath(`/projects/${projectId}/requirements`, limit, offset)),
  createRequirement: (projectId: string, payload: RequirementInput): Promise<Requirement> => request<Requirement>(`/projects/${projectId}/requirements`, { method: "POST", body: JSON.stringify(payload) }),
  updateRequirement: (projectId: string, requirementId: string, payload: Partial<RequirementInput>): Promise<Requirement> => request<Requirement>(`/projects/${projectId}/requirements/${requirementId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRequirement: (projectId: string, requirementId: string): Promise<void> => request<void>(`/projects/${projectId}/requirements/${requirementId}`, { method: "DELETE" }),
  analyzeRequirement: (projectId: string, requirementId: string): Promise<RequirementAnalysisResponse> => request<RequirementAnalysisResponse>(`/projects/${projectId}/requirements/${requirementId}/analysis`, { method: "POST" }),
  getRequirementTestCases: (projectId: string, requirementId: string, limit = 50, offset = 0, reviewStatus?: ReviewStatus): Promise<TestCaseListResponse> =>
    request<TestCaseListResponse>(collectionPath(`/projects/${projectId}/requirements/${requirementId}/test-cases`, limit, offset, reviewStatus ? { review_status: reviewStatus } : {})),
  generateRequirementTestCases: (projectId: string, requirementId: string): Promise<GeneratedTestCasesResponse> =>
    request<GeneratedTestCasesResponse>(`/projects/${projectId}/requirements/${requirementId}/test-cases/generate`, { method: "POST" }),
  getRequirementTestCase: (projectId: string, requirementId: string, testCaseId: string): Promise<TestCase> =>
    request<TestCase>(`/projects/${projectId}/requirements/${requirementId}/test-cases/${testCaseId}`),
  updateRequirementTestCase: (projectId: string, requirementId: string, testCaseId: string, payload: TestCaseUpdateInput): Promise<TestCase> =>
    request<TestCase>(`/projects/${projectId}/requirements/${requirementId}/test-cases/${testCaseId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  approveRequirementTestCase: (projectId: string, requirementId: string, testCaseId: string): Promise<TestCase> =>
    request<TestCase>(`/projects/${projectId}/requirements/${requirementId}/test-cases/${testCaseId}/approve`, { method: "POST" }),
  rejectRequirementTestCase: (projectId: string, requirementId: string, testCaseId: string): Promise<TestCase> =>
    request<TestCase>(`/projects/${projectId}/requirements/${requirementId}/test-cases/${testCaseId}/reject`, { method: "POST" }),
  executeTestCase: (projectId: string, testCaseId: string, payload?: ExecutionTriggerInput): Promise<TestExecution> =>
    request<TestExecution>(`/projects/${projectId}/test-cases/${testCaseId}/execute`, { method: "POST", body: payload ? JSON.stringify(payload) : undefined }),
  getExecutions: (projectId: string, testCaseId?: string, limit = 50, offset = 0): Promise<ExecutionListResponse> =>
    request<ExecutionListResponse>(collectionPath(`/projects/${projectId}/executions`, limit, offset, testCaseId ? { test_case_id: testCaseId } : {})),
  getExecution: (projectId: string, executionId: string): Promise<TestExecution> =>
    request<TestExecution>(`/projects/${projectId}/executions/${executionId}`),
  getExecutionDetail: (projectId: string, executionId: string): Promise<ExecutionDetailResponse> =>
    request<ExecutionDetailResponse>(`/projects/${projectId}/executions/${executionId}/detail`),
  getExecutionAnalysisContext: (projectId: string, executionId: string): Promise<ExecutionFailureContext> =>
    request<ExecutionFailureContext>(`/projects/${projectId}/executions/${executionId}/analysis-context`),
  getTestCaseHistory: (projectId: string, testCaseId: string, limit = 50, offset = 0): Promise<ExecutionListResponse> =>
    request<ExecutionListResponse>(collectionPath(`/projects/${projectId}/test-cases/${testCaseId}/history`, limit, offset)),
  getExecutionEvidence: (projectId: string, executionId: string, limit = 50, offset = 0): Promise<EvidenceListResponse> =>
    request<EvidenceListResponse>(collectionPath(`/projects/${projectId}/executions/${executionId}/evidence`, limit, offset)),
  getEvidenceDownloadUrl: (projectId: string, executionId: string, evidenceId: string): string =>
    `${apiBaseUrl}/projects/${projectId}/executions/${executionId}/evidence/${evidenceId}/download`,
  getExecutionFailureAnalysis: (projectId: string, executionId: string): Promise<FailureAnalysis> =>
    request<FailureAnalysis>(`/projects/${projectId}/executions/${executionId}/analysis`),
  requestExecutionFailureAnalysis: (projectId: string, executionId: string, force = false): Promise<FailureAnalysis> =>
    request<FailureAnalysis>(`/projects/${projectId}/executions/${executionId}/analysis${force ? "?force=true" : ""}`, {
      method: "POST",
    }),
  getFailureAnalyses: (projectId: string, category?: string, limit = 50, offset = 0): Promise<FailureAnalysisListResponse> =>
    request<FailureAnalysisListResponse>(
      collectionPath(`/projects/${projectId}/failure-analyses`, limit, offset, category ? { category } : {})
    ),
  startWorkflow: (projectId: string, payload: WorkflowStartInput): Promise<WorkflowExecution> =>
    request<WorkflowExecution>(`/projects/${projectId}/workflows`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getWorkflows: (projectId: string, limit = 50, offset = 0, requirementId?: string): Promise<WorkflowListResponse> =>
    request<WorkflowListResponse>(
      collectionPath(`/projects/${projectId}/workflows`, limit, offset, requirementId ? { requirement_id: requirementId } : {})
    ),
  getWorkflow: (projectId: string, workflowId: string): Promise<WorkflowDetailResponse> =>
    request<WorkflowDetailResponse>(`/projects/${projectId}/workflows/${workflowId}`),
  getWorkflowHistory: (projectId: string, workflowId: string): Promise<WorkflowHistoryResponse> =>
    request<WorkflowHistoryResponse>(`/projects/${projectId}/workflows/${workflowId}/history`),
  submitWorkflowApproval: (projectId: string, workflowId: string, payload: WorkflowApprovalInput): Promise<WorkflowDetailResponse> =>
    request<WorkflowDetailResponse>(`/projects/${projectId}/workflows/${workflowId}/approval`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProjectAnalytics: (projectId: string): Promise<ProjectAnalyticsResponse> =>
    request<ProjectAnalyticsResponse>(`/projects/${projectId}/analytics`),
  getProjectTraceability: (projectId: string): Promise<ProjectTraceabilityResponse> =>
    request<ProjectTraceabilityResponse>(`/projects/${projectId}/traceability`),
  getProjectReport: (projectId: string): Promise<ProjectReportResponse> =>
    request<ProjectReportResponse>(`/projects/${projectId}/report`),
  getDefects: (projectId: string, limit = 50, offset = 0, status?: string, severity?: string): Promise<DefectListResponse> =>
    request<DefectListResponse>(
      collectionPath(`/projects/${projectId}/defects`, limit, offset, {
        ...(status ? { status } : {}),
        ...(severity ? { severity } : {}),
      })
    ),
  getDefect: (projectId: string, defectId: string): Promise<Defect> =>
    request<Defect>(`/projects/${projectId}/defects/${defectId}`),
  updateDefect: (projectId: string, defectId: string, payload: DefectUpdateInput): Promise<Defect> =>
    request<Defect>(`/projects/${projectId}/defects/${defectId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  getHealingProposals: (projectId: string, limit = 50, offset = 0, status?: string): Promise<HealingProposalListResponse> =>
    request<HealingProposalListResponse>(
      collectionPath(`/projects/${projectId}/healing-proposals`, limit, offset, status ? { status } : {})
    ),
  getHealingProposal: (projectId: string, proposalId: string): Promise<HealingProposal> =>
    request<HealingProposal>(`/projects/${projectId}/healing-proposals/${proposalId}`),
  approveHealingProposal: (projectId: string, proposalId: string, notes?: string): Promise<HealingProposal> =>
    request<HealingProposal>(`/projects/${projectId}/healing-proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision: "approve", notes: notes || null }),
    }),
  rejectHealingProposal: (projectId: string, proposalId: string, notes?: string): Promise<HealingProposal> =>
    request<HealingProposal>(`/projects/${projectId}/healing-proposals/${proposalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ decision: "reject", notes: notes || null }),
    }),
  getTestCaseHealingHistory: (projectId: string, testCaseId: string): Promise<HealingProposalListResponse> =>
    request<HealingProposalListResponse>(`/projects/${projectId}/test-cases/${testCaseId}/healing-history`),
  getExecutionHealingProposals: (projectId: string, executionId: string): Promise<HealingProposalListResponse> =>
    request<HealingProposalListResponse>(`/projects/${projectId}/executions/${executionId}/healing-proposals`),
};
