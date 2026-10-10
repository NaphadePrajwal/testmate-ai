import type {
  HealthResponse,
  Project,
  ProjectInput,
  ProjectListResponse,
  Requirement,
  RequirementAnalysisResponse,
  RequirementInput,
  RequirementListResponse
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

function collectionPath(path: string, limit: number, offset: number): string {
  return `${path}?${new URLSearchParams({ limit: String(limit), offset: String(offset) })}`;
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
  analyzeRequirement: (projectId: string, requirementId: string): Promise<RequirementAnalysisResponse> => request<RequirementAnalysisResponse>(`/projects/${projectId}/requirements/${requirementId}/analysis`, { method: "POST" })
};
