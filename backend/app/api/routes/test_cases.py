from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.models.enums import TestCaseStatus
from app.schemas.test_case import TestCaseCreate, TestCaseListResponse, TestCaseRead, TestCaseUpdate
from app.services.test_case_service import TestCaseService

router = APIRouter()


@router.get("", response_model=TestCaseListResponse, summary="List project test cases")
def list_test_cases(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    requirement_id: UUID | None = None,
    status_filter: Annotated[TestCaseStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> TestCaseListResponse:
    items, total = TestCaseService(db).list_test_cases(
        project_id, page.limit, page.offset, requirement_id, status_filter
    )
    return TestCaseListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=TestCaseRead, status_code=status.HTTP_201_CREATED, summary="Create a test case")
def create_test_case(project_id: UUID, payload: TestCaseCreate, db: Session = Depends(get_db)) -> TestCaseRead:
    return TestCaseService(db).create_test_case(project_id, payload)


@router.get("/{test_case_id}", response_model=TestCaseRead, summary="Get a test case")
def get_test_case(project_id: UUID, test_case_id: UUID, db: Session = Depends(get_db)) -> TestCaseRead:
    return TestCaseService(db).get_test_case(project_id, test_case_id)


@router.patch("/{test_case_id}", response_model=TestCaseRead, summary="Partially update an unexecuted test case")
def update_test_case(
    project_id: UUID, test_case_id: UUID, payload: TestCaseUpdate, db: Session = Depends(get_db)
) -> TestCaseRead:
    return TestCaseService(db).update_test_case(project_id, test_case_id, payload)


@router.delete("/{test_case_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an unexecuted test case")
def delete_test_case(project_id: UUID, test_case_id: UUID, db: Session = Depends(get_db)) -> Response:
    TestCaseService(db).delete_test_case(project_id, test_case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
