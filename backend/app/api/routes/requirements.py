from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.models.enums import RequirementStatus, ReviewStatus, TestCaseStatus
from app.schemas.generated_test_case import GeneratedTestCasesResponse
from app.schemas.requirement import RequirementCreate, RequirementListResponse, RequirementRead, RequirementUpdate
from app.schemas.requirement_analysis import RequirementAnalysisRead
from app.schemas.test_case import TestCaseListResponse, TestCaseRead, TestCaseUpdate
from app.services.requirement_analysis_service import RequirementAnalysisService, get_requirement_analysis_service
from app.services.requirement_service import RequirementService
from app.services.test_case_generation_service import (
    TestCaseGenerationProvider,
    TestCaseGenerationService,
    get_test_case_generation_provider,
)
from app.services.test_case_service import TestCaseService

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


@router.post(
    "/{requirement_id}/test-cases/generate",
    response_model=GeneratedTestCasesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate structured test cases for a requirement using AI",
)
def generate_test_cases(
    project_id: UUID,
    requirement_id: UUID,
    db: Session = Depends(get_db),
    provider: TestCaseGenerationProvider = Depends(get_test_case_generation_provider),
) -> GeneratedTestCasesResponse:
    return TestCaseGenerationService(db, provider).generate_for_requirement(project_id, requirement_id)


@router.get(
    "/{requirement_id}/test-cases",
    response_model=TestCaseListResponse,
    summary="List test cases for a specific requirement",
)
def list_requirement_test_cases(
    project_id: UUID,
    requirement_id: UUID,
    page: Pagination = Depends(pagination_params),
    review_status_filter: Annotated[ReviewStatus | None, Query(alias="review_status")] = None,
    status_filter: Annotated[TestCaseStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> TestCaseListResponse:
    items, total = TestCaseService(db).list_requirement_test_cases(
        project_id, requirement_id, page.limit, page.offset, review_status_filter, status_filter
    )
    return TestCaseListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{requirement_id}/test-cases/{test_case_id}",
    response_model=TestCaseRead,
    summary="Get a specific test case for a requirement",
)
def get_requirement_test_case(
    project_id: UUID,
    requirement_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
) -> TestCaseRead:
    return TestCaseService(db).get_requirement_test_case(project_id, requirement_id, test_case_id)


@router.patch(
    "/{requirement_id}/test-cases/{test_case_id}",
    response_model=TestCaseRead,
    summary="Update a test case for a requirement",
)
def update_requirement_test_case(
    project_id: UUID,
    requirement_id: UUID,
    test_case_id: UUID,
    payload: TestCaseUpdate,
    db: Session = Depends(get_db),
) -> TestCaseRead:
    return TestCaseService(db).update_requirement_test_case(project_id, requirement_id, test_case_id, payload)


@router.post(
    "/{requirement_id}/test-cases/{test_case_id}/approve",
    response_model=TestCaseRead,
    summary="Approve a pending test case",
)
def approve_requirement_test_case(
    project_id: UUID,
    requirement_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
) -> TestCaseRead:
    return TestCaseService(db).approve_requirement_test_case(project_id, requirement_id, test_case_id)


@router.post(
    "/{requirement_id}/test-cases/{test_case_id}/reject",
    response_model=TestCaseRead,
    summary="Reject a pending test case",
)
def reject_requirement_test_case(
    project_id: UUID,
    requirement_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
) -> TestCaseRead:
    return TestCaseService(db).reject_requirement_test_case(project_id, requirement_id, test_case_id)


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
