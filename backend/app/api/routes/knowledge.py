from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.models.knowledge_indexing_job import IndexingJobStatus
from app.schemas.knowledge import (
    KnowledgeIndexRequest,
    KnowledgeIndexResult,
    KnowledgeIndexingJobListResponse,
    KnowledgeIndexingJobProcessResponse,
    KnowledgeIndexingJobRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.knowledge_indexing_job_service import KnowledgeIndexingJobService
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService

router = APIRouter()


@router.post(
    "/index",
    response_model=KnowledgeIndexResult,
    status_code=status.HTTP_200_OK,
    summary="Index or refresh historical QA intelligence (defects, failure analyses, test cases) into Qdrant",
)
def index_project_knowledge(
    project_id: UUID,
    payload: KnowledgeIndexRequest | None = None,
    db: Session = Depends(get_db),
) -> KnowledgeIndexResult:
    service = KnowledgeBaseService(db=db)
    record_types = payload.record_types if payload else None
    return service.index_project_knowledge(project_id=project_id, record_types=record_types)


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search project historical knowledge by semantic similarity",
)
def search_project_knowledge(
    project_id: UUID,
    payload: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
) -> KnowledgeSearchResponse:
    service = KnowledgeRetrievalService(db=db)
    return service.search_project_knowledge(
        project_id=project_id,
        query=payload.query,
        record_types=payload.record_types,
        limit=payload.limit,
        min_score=payload.min_score,
    )


@router.get(
    "/jobs",
    response_model=KnowledgeIndexingJobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List background knowledge indexing outbox jobs for a project",
)
def list_indexing_jobs(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[IndexingJobStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> KnowledgeIndexingJobListResponse:
    service = KnowledgeIndexingJobService(db=db)
    items, total, pending, failed = service.list_jobs(
        project_id=project_id,
        status=status_filter,
        limit=page.limit,
        offset=page.offset,
    )
    return KnowledgeIndexingJobListResponse(
        items=[KnowledgeIndexingJobRead.model_validate(j) for j in items],
        total=total,
        pending_count=pending,
        failed_count=failed,
    )


@router.post(
    "/jobs/process",
    response_model=KnowledgeIndexingJobProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger processing or retry of pending and failed knowledge indexing jobs for a project",
)
def process_indexing_jobs(
    project_id: UUID,
    limit: int = 50,
    include_failed: bool = True,
    db: Session = Depends(get_db),
) -> KnowledgeIndexingJobProcessResponse:
    service = KnowledgeIndexingJobService(db=db)
    success, failure = service.process_project_jobs(
        project_id=project_id,
        limit=limit,
        include_failed=include_failed,
    )
    return KnowledgeIndexingJobProcessResponse(
        processed_count=success + failure,
        success_count=success,
        failure_count=failure,
    )
