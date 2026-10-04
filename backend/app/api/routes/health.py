from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import engine
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter()


def database_status() -> DatabaseHealth:
    """Probe PostgreSQL without surfacing connection details to API clients."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(status="connected")
    except SQLAlchemyError:
        return DatabaseHealth(status="unavailable")


@router.get("/health", response_model=HealthResponse, summary="Check API and PostgreSQL availability")
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, database=database_status())
