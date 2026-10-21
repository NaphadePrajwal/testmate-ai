from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import engine
from app.schemas.health import DatabaseHealth, HealthResponse, VectorDatabaseHealth
from app.services.qdrant_service import QdrantService

router = APIRouter()


def database_status() -> DatabaseHealth:
    """Probe PostgreSQL without surfacing connection details to API clients."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(status="connected")
    except SQLAlchemyError:
        return DatabaseHealth(status="unavailable")


def vector_database_status() -> VectorDatabaseHealth:
    """Probe Qdrant vector database without throwing unhandled exceptions if unavailable."""
    try:
        service = QdrantService()
        health = service.get_health()
        return VectorDatabaseHealth(
            status=health["status"],
            mode=health.get("mode"),
            collection=health.get("collection"),
        )
    except Exception:
        return VectorDatabaseHealth(status="unavailable")


@router.get("/health", response_model=HealthResponse, summary="Check API, PostgreSQL, and vector database availability")
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        database=database_status(),
        vector_database=vector_database_status(),
    )
