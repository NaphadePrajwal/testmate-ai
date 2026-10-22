from fastapi import APIRouter

from app.api.routes import demo, executions, health, knowledge, projects, requirements, test_cases, workflows

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(demo.router, tags=["demo"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(requirements.router, prefix="/projects/{project_id}/requirements", tags=["requirements"])
api_router.include_router(test_cases.router, prefix="/projects/{project_id}/test-cases", tags=["test cases"])
api_router.include_router(executions.router, prefix="/projects/{project_id}", tags=["executions and defects"])
api_router.include_router(knowledge.router, prefix="/projects/{project_id}/knowledge", tags=["historical knowledge"])
api_router.include_router(workflows.router, prefix="/projects/{project_id}", tags=["multi-agent workflows"])

