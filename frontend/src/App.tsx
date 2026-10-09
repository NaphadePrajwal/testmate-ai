import { useCallback, useState } from "react";
import { ApiStatus } from "./components/ApiStatus";
import { useApiResource } from "./hooks/useApiResource";
import { AppLayout } from "./layouts/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectDetailsPage } from "./pages/ProjectDetailsPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { api } from "./services/api";
import type { Project, ProjectInput } from "./types/api";

type Page = "Dashboard" | "Projects" | "Project details";
const pageSize = 20;

export default function App() {
  const [page, setPage] = useState<Page>("Dashboard");
  const [projectOffset, setProjectOffset] = useState(0);
  const loadHealth = useCallback(() => api.getHealth(), []);
  const loadProjects = useCallback(() => api.getProjects(pageSize, projectOffset), [projectOffset]);
  const health = useApiResource(loadHealth);
  const projects = useApiResource(loadProjects);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  async function createProject(values: ProjectInput) {
    const project = await api.createProject(values);
    await projects.reload();
    return project;
  }

  function openProject(project: Project) {
    setSelectedProject(project);
    setPage("Project details");
  }

  function updateSelectedProject(project: Project) {
    setSelectedProject(project);
    void projects.reload();
  }

  function navigate(nextPage: "Dashboard" | "Projects") {
    setPage(nextPage);
    if (nextPage === "Projects") setSelectedProject(null);
  }

  return (
    <AppLayout activePage={page === "Dashboard" ? "Dashboard" : "Projects"} onNavigate={navigate} status={<ApiStatus health={health.data} error={health.error} loading={health.isLoading} />}>
      {page === "Dashboard" ? (
        <DashboardPage health={health.data} projectCount={projects.data?.items.length ?? null} isLoadingProjects={projects.isLoading} />
      ) : page === "Project details" && selectedProject ? <ProjectDetailsPage project={selectedProject} onBack={() => navigate("Projects")} onProjectUpdated={updateSelectedProject} /> : <ProjectsPage projects={projects.data} error={projects.error} isLoading={projects.isLoading} onRetry={() => void projects.reload()} onCreate={createProject} onOpen={openProject} onPageChange={setProjectOffset} />}
    </AppLayout>
  );
}
