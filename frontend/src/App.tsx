import { useCallback, useState } from "react";
import { ApiStatus } from "./components/ApiStatus";
import { useApiResource } from "./hooks/useApiResource";
import { AppLayout } from "./layouts/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { api } from "./services/api";

type Page = "Dashboard" | "Projects";

export default function App() {
  const [page, setPage] = useState<Page>("Dashboard");
  const loadHealth = useCallback(() => api.getHealth(), []);
  const loadProjects = useCallback(() => api.getProjects(), []);
  const health = useApiResource(loadHealth);
  const projects = useApiResource(loadProjects);

  return (
    <AppLayout activePage={page} onNavigate={setPage} status={<ApiStatus health={health.data} error={health.error} loading={health.isLoading} />}>
      {page === "Dashboard" ? (
        <DashboardPage health={health.data} projectCount={projects.data?.items.length ?? null} isLoadingProjects={projects.isLoading} />
      ) : (
        <ProjectsPage projects={projects.data?.items ?? null} error={projects.error} isLoading={projects.isLoading} onRetry={() => void projects.reload()} />
      )}
    </AppLayout>
  );
}
