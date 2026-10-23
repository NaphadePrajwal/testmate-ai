export type DatabaseStatus = "connected" | "unavailable";

export interface HealthResponse {
  status: "ok";
  service: string;
  database: { status: DatabaseStatus };
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface PageResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type ProjectListResponse = PageResponse<Project>;

export interface ProjectInput {
  name: string;
  description: string | null;
}

export type RequirementStatus = "draft" | "approved" | "obsolete";

export interface Requirement {
  id: string;
  project_id: string;
  title: string;
  description: string;
  target_url?: string | null;
  status: RequirementStatus;
  acceptance_criteria: string[];
  created_at: string;
  updated_at: string;
}

export type RequirementListResponse = PageResponse<Requirement>;

export interface RequirementInput {
  title: string;
  description: string;
  target_url?: string | null;
  status: RequirementStatus;
  acceptance_criteria: string[];
}

export type AnalysisSource = "explicit" | "inferred" | "suggested" | "unspecified";
export type RequirementType = "functional" | "non_functional" | "business_rule" | "constraint" | "other" | "uncertain";
export type ClarityLevel = "low" | "medium" | "high";

export interface AnalysisItem { text: string; source: AnalysisSource; }
export interface RequirementAnalysis {
  summary: AnalysisItem;
  requirement_type: { classification: RequirementType; rationale: AnalysisItem };
  actors_and_entities: AnalysisItem[];
  expected_behaviors: AnalysisItem[];
  inputs: AnalysisItem[];
  outputs: AnalysisItem[];
  preconditions: AnalysisItem[];
  postconditions: AnalysisItem[];
  acceptance_criteria: AnalysisItem[];
  ambiguities_and_missing_information: AnalysisItem[];
  dependencies_and_constraints: AnalysisItem[];
  clarification_questions: AnalysisItem[];
  quality_assessment: { clarity: ClarityLevel; completeness: ClarityLevel; reasons: AnalysisItem[]; limitation: string };
}

export interface RequirementAnalysisResponse {
  analysis: RequirementAnalysis;
  metadata: { provider: string; model: string; prompt_version: string; analyzed_at: string };
}

export type ReviewStatus = "pending" | "approved" | "rejected";
export type TestCaseStatus = "draft" | "approved" | "retired";
export type TestType = "web" | "api" | "manual";
export type Priority = "low" | "medium" | "high" | "critical";

export interface TestStep {
  action: string;
  expected_result?: string | null;
  data?: Record<string, unknown>;
}

export interface TestCase {
  id: string;
  requirement_id: string;
  title: string;
  description: string | null;
  target_url?: string | null;
  preconditions: string[];
  steps: TestStep[];
  expected_result: string;
  test_type: TestType;
  priority: Priority;
  status: TestCaseStatus;
  review_status: ReviewStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export type TestCaseListResponse = PageResponse<TestCase>;

export interface TestCaseUpdateInput {
  title?: string;
  description?: string | null;
  target_url?: string | null;
  preconditions?: string[];
  steps?: TestStep[];
  expected_result?: string;
  test_type?: TestType;
  priority?: Priority;
}

export interface GeneratedTestCasesResponse {
  items: TestCase[];
  total_generated: number;
  requirement_coverage_summary: string;
  assumptions: string[];
  metadata: {
    provider: string;
    model: string;
    prompt_version: string;
    generated_at: string;
  };
}

export type ExecutionStatus = "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
export type EvidenceType = "screenshot" | "video" | "log" | "trace" | "request_response";
export type DefectSeverity = "low" | "medium" | "high" | "critical";
export type DefectStatus = "new" | "triaged" | "in_progress" | "resolved" | "closed" | "rejected";

export interface Defect {
  id: string;
  execution_id: string;
  title: string;
  description?: string | null;
  severity: DefectSeverity;
  status: DefectStatus;
  fingerprint?: string | null;
  resolution_notes?: string | null;
  verification_status?: string | null;
  created_at: string;
  updated_at: string;
}

export type DefectListResponse = PageResponse<Defect>;

export interface DefectUpdateInput {
  title?: string;
  description?: string;
  severity?: DefectSeverity;
  status?: DefectStatus;
  resolution_notes?: string;
  verification_status?: string;
  verification_method?: string;
  verification_evidence?: string;
}

export interface TestCaseSnapshot {
  test_case_id: string;
  title: string;
  version: number;
  test_type: string;
  priority: string;
  target_url?: string | null;
  preconditions?: string[];
  steps?: TestStep[];
  expected_result: string;
  requirement_id: string;
  requirement_title?: string | null;
  project_id?: string | null;
  snapshot_at: string;
}

export interface StepExecutionResult {
  step_index: number;
  action: string;
  status: "passed" | "failed" | "error" | "skipped";
  expected?: string | null;
  actual?: string | null;
  expected_result?: string | null;
  actual_result?: string | null;
  duration_ms?: number;
  error_message?: string | null;
  error_details?: string | null;
  details?: Record<string, unknown>;
}

export interface ExecutionSummary {
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  error_steps?: number;
  skipped_steps: number;
  duration_ms?: number;
  total_duration_ms?: number;
  error_category?: string | null;
  failed_step_index?: number | null;
  failure_explanation?: string | null;
  sanitized_failure_reason?: string | null;
  evidence_count?: number;
  step_results?: StepExecutionResult[];
  test_case_snapshot?: TestCaseSnapshot | null;
}

export interface TestExecution {
  id: string;
  test_case_id: string;
  status: ExecutionStatus;
  executor?: string | null;
  run_reference?: string | null;
  summary: ExecutionSummary;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export type ExecutionListResponse = PageResponse<TestExecution>;

export interface ExecutionEvidence {
  id: string;
  execution_id: string;
  evidence_type: EvidenceType;
  uri: string;
  label?: string | null;
  content_type?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export type EvidenceListResponse = PageResponse<ExecutionEvidence>;

export interface ExecutionTriggerInput {
  executor?: "playwright" | "httpx" | "pytest";
}

export interface ExecutionDetailResponse {
  id: string;
  test_case_id: string;
  status: ExecutionStatus;
  executor?: string | null;
  run_reference?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  test_case_snapshot?: TestCaseSnapshot | null;
  summary: ExecutionSummary;
  step_results: StepExecutionResult[];
  evidence: ExecutionEvidence[];
  evidence_items?: ExecutionEvidence[];
  defects?: Defect[];
}

export interface ExecutionFailureContext {
  execution_id: string;
  test_case_id: string;
  requirement_id: string;
  project_id: string;
  test_case_title: string;
  test_case_version: number;
  test_type: string;
  status: ExecutionStatus;
  executor?: string | null;
  error_category?: string | null;
  error_message?: string | null;
  failed_step_index?: number | null;
  sanitized_failure_reason?: string | null;
  failed_step?: StepExecutionResult | null;
  steps: StepExecutionResult[];
  step_results: StepExecutionResult[];
  test_case_snapshot?: TestCaseSnapshot | null;
  logs: string[];
  evidence_references: Record<string, unknown>[];
  evidence: ExecutionEvidence[];
  defects: Defect[];
  duration_ms: number;
  timestamp: string;
}

export type FailureCategory =
  | "assertion_failure"
  | "application_error"
  | "timeout"
  | "network_error"
  | "element_not_found"
  | "security_violation"
  | "infrastructure_error"
  | "unknown";

export type ConfidenceLevel = "high" | "medium" | "low";

export interface FailureAnalysisMetadata {
  provider?: string;
  model?: string;
  prompt_version?: string;
  analyzed_at?: string;
  [key: string]: unknown;
}

export interface FailureAnalysis {
  id: string;
  execution_id: string;
  project_id: string;
  failure_category: FailureCategory | string;
  summary: string;
  observed_error: string;
  likely_root_cause: string;
  supporting_evidence: string[];
  recommended_debugging_steps: string[];
  confidence: ConfidenceLevel | string;
  uncertainty_notes?: string | null;
  metadata: FailureAnalysisMetadata;
  created_at: string;
  updated_at: string;
}

export type FailureAnalysisListResponse = PageResponse<FailureAnalysis>;

export type WorkflowStatus =
  | "pending"
  | "analyzing_requirement"
  | "generating_test_cases"
  | "paused_for_approval"
  | "executing_tests"
  | "analyzing_failure"
  | "completed"
  | "failed"
  | "rejected";

export type WorkflowApprovalAction = "approve" | "reject" | "request_revision";

export interface WorkflowExecution {
  id: string;
  project_id: string;
  requirement_id: string;
  status: WorkflowStatus;
  current_stage: string;
  generated_test_case_ids: string[];
  execution_ids: string[];
  failure_analysis_id?: string | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface WorkflowDetailResponse extends WorkflowExecution {
  generated_test_cases: TestCase[];
  executions: TestExecution[];
  failure_analysis?: FailureAnalysis | null;
}

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  stage: string;
  event_type: string;
  message?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface WorkflowHistoryResponse {
  workflow_id: string;
  events: WorkflowEvent[];
}

export type WorkflowListResponse = PageResponse<WorkflowExecution>;

export interface WorkflowStartInput {
  requirement_id: string;
  notes?: string | null;
}

export interface WorkflowApprovalInput {
  action: WorkflowApprovalAction;
  notes?: string | null;
  revision_instructions?: string | null;
}

// Phase 11: Complete Dashboard Integration Types
export interface ExecutionTrendPoint {
  date: string;
  passed: number;
  failed: number;
  error: number;
  total: number;
}

export interface RecentExecutionItem {
  id: string;
  test_case_id: string;
  test_case_title: string;
  status: string;
  executor?: string | null;
  duration_ms?: number | null;
  created_at: string;
}

export interface ProjectAnalyticsResponse {
  project_id: string;
  project_name: string;
  total_requirements: number;
  total_test_cases: number;
  total_test_executions: number;
  passed_executions: number;
  failed_executions: number;
  running_executions: number;
  pending_executions: number;
  error_executions: number;
  execution_pass_rate: number;
  requirement_coverage_rate: number;
  total_defects: number;
  open_defects: number;
  critical_defects: number;
  high_defects: number;
  medium_defects: number;
  low_defects: number;
  defects_by_status: Record<string, number>;
  defects_by_severity: Record<string, number>;
  execution_trends: ExecutionTrendPoint[];
  recent_executions: RecentExecutionItem[];
}

export interface TraceabilityTestCaseItem {
  id: string;
  title: string;
  test_type: string;
  review_status: string;
  status: string;
  latest_execution_status?: string | null;
}

export interface TraceabilityItem {
  requirement_id: string;
  requirement_title: string;
  requirement_status: string;
  test_cases_count: number;
  coverage_status: "covered" | "uncovered";
  latest_execution_status?: string | null;
  test_cases: TraceabilityTestCaseItem[];
  defect_count: number;
}

export interface ProjectTraceabilityResponse {
  project_id: string;
  total_requirements: number;
  covered_requirements: number;
  uncovered_requirements: number;
  coverage_rate: number;
  requirements_without_cases: number;
  cases_without_executions: number;
  items: TraceabilityItem[];
}

export interface ProjectReportResponse {
  project_id: string;
  project_name: string;
  project_description?: string | null;
  created_at: string;
  analytics: ProjectAnalyticsResponse;
  traceability_summary: ProjectTraceabilityResponse;
  quality_score: number;
}

export type HealingStatus =
  | "detected"
  | "analyzing"
  | "proposed"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "validating"
  | "healed"
  | "failed";

export type HealingApprovalAction = "approve" | "reject";

export interface CandidateValidationResult {
  candidate: Record<string, unknown>;
  candidate_type: string;
  matched: boolean;
  match_count: number;
  is_visible: boolean;
  is_actionable: boolean;
  score: number;
  reasons: string[];
}

export interface HealingProposal {
  id: string;
  project_id: string;
  test_case_id: string;
  test_case_title?: string | null;
  original_execution_id: string;
  retry_execution_id?: string | null;
  failed_step_index: number;
  failed_action_type: string;
  original_selector: Record<string, unknown>;
  original_error?: string | null;
  page_url?: string | null;
  page_title?: string | null;
  proposed_selector?: Record<string, unknown> | null;
  proposed_selector_type?: string | null;
  candidate_validations?: CandidateValidationResult[] | null;
  status: HealingStatus;
  confidence_score: number;
  ranking_explanation?: string | null;
  approval_decision?: string | null;
  approval_notes?: string | null;
  approved_at?: string | null;
  applied_at?: string | null;
  applied_selector?: Record<string, unknown> | null;
  failure_reason?: string | null;
  evidence_ids?: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface HealingProposalListResponse {
  items: HealingProposal[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealingApprovalRequest {
  decision: "approve";
  notes?: string | null;
}

export interface HealingRejectionRequest {
  decision: "reject";
  notes?: string | null;
}
