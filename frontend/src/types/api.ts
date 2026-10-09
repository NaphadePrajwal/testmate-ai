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
