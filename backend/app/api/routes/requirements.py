from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.models.enums import RequirementStatus
from app.schemas.requirement import RequirementCreate, RequirementListResponse, RequirementRead, RequirementUpdate
from app.schemas.requirement_analysis import RequirementAnalysisRead
from app.services.requirement_analysis_service import RequirementAnalysisService, get_requirement_analysis_service
from app.services.requirement_service import RequirementService

router = APIRouter()


@router.get("", response_model=RequirementListResponse, summary="List project requirements")
def list_requirements(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[RequirementStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> RequirementListResponse:
    items, total = RequirementService(db).list_requirements(project_id, page.limit, page.offset, status_filter)
    return RequirementListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=RequirementRead, status_code=status.HTTP_201_CREATED, summary="Create a requirement")
def create_requirement(project_id: UUID, payload: RequirementCreate, db: Session = Depends(get_db)) -> RequirementRead:
    return RequirementService(db).create_requirement(project_id, payload)


@router.post("/{requirement_id}/analysis", response_model=RequirementAnalysisRead, summary="Analyze a project requirement")
def analyze_requirement(
    project_id: UUID,
    requirement_id: UUID,
    db: Session = Depends(get_db),
    analysis_service: RequirementAnalysisService = Depends(get_requirement_analysis_service),
) -> RequirementAnalysisRead:
    requirement = RequirementService(db).get_requirement(project_id, requirement_id)
    return analysis_service.analyze(requirement)


@router.get("/{requirement_id}", response_model=RequirementRead, summary="Get a requirement")
def get_requirement(project_id: UUID, requirement_id: UUID, db: Session = Depends(get_db)) -> RequirementRead:
    return RequirementService(db).get_requirement(project_id, requirement_id)


@router.patch("/{requirement_id}", response_model=RequirementRead, summary="Partially update a requirement")
def update_requirement(
    project_id: UUID, requirement_id: UUID, payload: RequirementUpdate, db: Session = Depends(get_db)
) -> RequirementRead:
    return RequirementService(db).update_requirement(project_id, requirement_id, payload)


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an unreferenced requirement")
def delete_requirement(project_id: UUID, requirement_id: UUID, db: Session = Depends(get_db)) -> Response:
    RequirementService(db).delete_requirement(project_id, requirement_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
