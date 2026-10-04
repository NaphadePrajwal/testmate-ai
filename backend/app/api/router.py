from fastapi import APIRouter

from app.api.routes import executions, health, projects, requirements, test_cases

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(requirements.router, prefix="/projects/{project_id}/requirements", tags=["requirements"])
api_router.include_router(test_cases.router, prefix="/projects/{project_id}/test-cases", tags=["test cases"])
api_router.include_router(executions.router, prefix="/projects/{project_id}", tags=["executions and defects"])
