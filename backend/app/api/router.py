from fastapi import APIRouter

from app.api.routes import health, projects

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
