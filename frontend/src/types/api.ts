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
  status: RequirementStatus;
  acceptance_criteria: string[];
  created_at: string;
  updated_at: string;
}

export type RequirementListResponse = PageResponse<Requirement>;

export interface RequirementInput {
  title: string;
  description: string;
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

export interface StepExecutionResult {
  step_index: number;
  action: string;
  status: "passed" | "failed" | "error" | "skipped";
  expected?: string | null;
  actual?: string | null;
  duration_ms: number;
  error_message?: string | null;
  details?: Record<string, unknown>;
}

export interface ExecutionSummary {
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  error_steps: number;
  skipped_steps: number;
  total_duration_ms: number;
  step_results: StepExecutionResult[];
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
