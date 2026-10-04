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

export interface ProjectListResponse {
  items: Project[];
}
