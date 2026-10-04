import type { HealthResponse, ProjectListResponse } from "../types/api";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${apiBaseUrl}${path}`);
  } catch {
    throw new ApiError("The TestMate API is unreachable. Start the backend and try again.");
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "The API request failed.", response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  getHealth: (): Promise<HealthResponse> => request<HealthResponse>("/health"),
  getProjects: (): Promise<ProjectListResponse> => request<ProjectListResponse>("/projects")
};
