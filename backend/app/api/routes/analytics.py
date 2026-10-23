from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import (
    ProjectAnalyticsResponse,
    ProjectReportResponse,
    ProjectTraceabilityResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get(
    "/analytics",
    response_model=ProjectAnalyticsResponse,
    summary="Get comprehensive testing analytics and execution trends for a project",
)
def get_project_analytics(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> ProjectAnalyticsResponse:
    return AnalyticsService(db).get_project_analytics(project_id)


@router.get(
    "/traceability",
    response_model=ProjectTraceabilityResponse,
    summary="Get requirement-to-test traceability matrix and coverage analysis",
)
def get_project_traceability(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> ProjectTraceabilityResponse:
    return AnalyticsService(db).get_project_traceability(project_id)


@router.get(
    "/report",
    response_model=ProjectReportResponse,
    summary="Get executive testing report with quality score and activity summary",
)
def get_project_report(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> ProjectReportResponse:
    return AnalyticsService(db).get_project_report(project_id)
