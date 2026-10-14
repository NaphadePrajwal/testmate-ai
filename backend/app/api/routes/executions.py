from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.core.config import get_settings
from app.core.exceptions import ResourceNotFoundError
from app.db.session import get_db
from app.models.enums import DefectStatus, ExecutionStatus, Severity
from app.schemas.execution import (
    DefectListResponse,
    DefectRead,
    EvidenceListResponse,
    EvidenceRead,
    ExecutionDetailResponse,
    ExecutionFailureContext,
    ExecutionListResponse,
    ExecutionRead,
    ExecutionTriggerRequest,
)
from app.schemas.failure_analysis import (
    ExecutionFailureAnalysisListResponse,
    ExecutionFailureAnalysisRead,
    FailureCategory,
)
from app.services.execution_service import ExecutionService
from app.services.failure_analysis_service import FailureAnalysisService

router = APIRouter()


@router.post(
    "/test-cases/{test_case_id}/execute",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Execute an approved test case",
)
def execute_test_case(
    project_id: UUID,
    test_case_id: UUID,
    body: ExecutionTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> ExecutionRead:
    executor = body.executor if body else None
    return ExecutionService(db).execute_test_case(project_id, test_case_id, executor)


@router.get("/executions", response_model=ExecutionListResponse, summary="List project execution history")
def list_executions(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
    test_case_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ExecutionListResponse:
    items, total = ExecutionService(db).list_executions(
        project_id, page.limit, page.offset, status_filter, test_case_id
    )
    return ExecutionListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/test-cases/{test_case_id}/history",
    response_model=ExecutionListResponse,
    summary="List execution history for a specific test case",
)
def list_test_case_history(
    project_id: UUID,
    test_case_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> ExecutionListResponse:
    items, total = ExecutionService(db).list_test_case_history(
        project_id, test_case_id, page.limit, page.offset, status_filter
    )
    return ExecutionListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/executions/{execution_id}", response_model=ExecutionRead, summary="Get an execution record")
def get_execution(project_id: UUID, execution_id: UUID, db: Session = Depends(get_db)) -> ExecutionRead:
    return ExecutionService(db).get_execution(project_id, execution_id)


@router.get(
    "/executions/{execution_id}/detail",
    response_model=ExecutionDetailResponse,
    summary="Get full structured execution details with step results, snapshot, evidence, and defects",
)
def get_execution_detail(
    project_id: UUID, execution_id: UUID, db: Session = Depends(get_db)
) -> ExecutionDetailResponse:
    return ExecutionService(db).get_execution_detail(project_id, execution_id)


@router.get(
    "/executions/{execution_id}/analysis-context",
    response_model=ExecutionFailureContext,
    summary="Get stable execution and failure context prepared for Phase 7 AI failure analysis",
)
def get_execution_for_analysis(
    project_id: UUID, execution_id: UUID, db: Session = Depends(get_db)
) -> ExecutionFailureContext:
    return ExecutionService(db).get_execution_for_analysis(project_id, execution_id)


@router.get(
    "/executions/{execution_id}/evidence", response_model=EvidenceListResponse, summary="List execution evidence"
)
def list_evidence(
    project_id: UUID,
    execution_id: UUID,
    page: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> EvidenceListResponse:
    items, total = ExecutionService(db).list_evidence(project_id, execution_id, page.limit, page.offset)
    return EvidenceListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/executions/{execution_id}/evidence/{evidence_id}", response_model=EvidenceRead, summary="Get execution evidence"
)
def get_evidence(
    project_id: UUID, execution_id: UUID, evidence_id: UUID, db: Session = Depends(get_db)
) -> EvidenceRead:
    return ExecutionService(db).get_evidence(project_id, execution_id, evidence_id)


@router.get(
    "/executions/{execution_id}/evidence/{evidence_id}/download",
    summary="Download or stream execution evidence binary/file",
)
def download_evidence_file(
    project_id: UUID, execution_id: UUID, evidence_id: UUID, db: Session = Depends(get_db)
) -> FileResponse:
    evidence = ExecutionService(db).get_evidence(project_id, execution_id, evidence_id)
    settings = get_settings()
    base_dir = Path(settings.evidence_storage_dir).resolve()
    file_path = (base_dir / evidence.uri).resolve()

    if not file_path.is_relative_to(base_dir) or not file_path.is_file():
        raise ResourceNotFoundError("Evidence file not found on disk.")

    return FileResponse(
        path=file_path,
        media_type=evidence.content_type or "application/octet-stream",
        filename=file_path.name,
    )


@router.get("/defects", response_model=DefectListResponse, summary="List project defects")
def list_defects(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[DefectStatus | None, Query(alias="status")] = None,
    severity: Severity | None = None,
    db: Session = Depends(get_db),
) -> DefectListResponse:
    items, total = ExecutionService(db).list_defects(project_id, page.limit, page.offset, status_filter, severity)
    return DefectListResponse(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/defects/{defect_id}", response_model=DefectRead, summary="Get a defect")
def get_defect(project_id: UUID, defect_id: UUID, db: Session = Depends(get_db)) -> DefectRead:
    return ExecutionService(db).get_defect(project_id, defect_id)


@router.post(
    "/executions/{execution_id}/analysis",
    response_model=ExecutionFailureAnalysisRead,
    summary="Trigger or retrieve AI root cause failure analysis for a completed failed execution",
)
def request_failure_analysis(
    project_id: UUID,
    execution_id: UUID,
    force: bool = False,
    db: Session = Depends(get_db),
) -> ExecutionFailureAnalysisRead:
    analysis = FailureAnalysisService(db).get_or_create_analysis(
        project_id, execution_id, force_refresh=force
    )
    return ExecutionFailureAnalysisRead.model_validate(analysis)


@router.get(
    "/executions/{execution_id}/analysis",
    response_model=ExecutionFailureAnalysisRead,
    summary="Get stored AI root cause failure analysis for an execution",
)
def get_failure_analysis(
    project_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> ExecutionFailureAnalysisRead:
    analysis = FailureAnalysisService(db).get_analysis(project_id, execution_id)
    return ExecutionFailureAnalysisRead.model_validate(analysis)


@router.get(
    "/failure-analyses",
    response_model=ExecutionFailureAnalysisListResponse,
    summary="List stored failure analyses for a project",
)
def list_failure_analyses(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    category: Annotated[FailureCategory | None, Query(alias="category")] = None,
    db: Session = Depends(get_db),
) -> ExecutionFailureAnalysisListResponse:
    items, total = FailureAnalysisService(db).list_analyses(
        project_id, page.limit, page.offset, category.value if category else None
    )
    return ExecutionFailureAnalysisListResponse(
        items=[ExecutionFailureAnalysisRead.model_validate(item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
