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
