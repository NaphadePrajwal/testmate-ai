from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.schemas.workflow import (
    WorkflowApprovalRequest,
    WorkflowDetailRead,
    WorkflowHistoryResponse,
    WorkflowListResponse,
    WorkflowRead,
    WorkflowStartRequest,
)
from app.services.workflow_service import WorkflowService

router = APIRouter()


@router.post(
    "/workflows",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new LangGraph multi-agent testing workflow",
)
def start_workflow(
    project_id: UUID,
    payload: WorkflowStartRequest,
    db: Session = Depends(get_db),
) -> WorkflowRead:
    wf = WorkflowService(db).start_workflow(
        project_id=project_id,
        requirement_id=payload.requirement_id,
        notes=payload.notes,
    )
    return WorkflowRead.model_validate(wf)


@router.get(
    "/workflows",
    response_model=WorkflowListResponse,
    summary="List workflows for a project",
)
def list_workflows(
    project_id: UUID,
    requirement_id: UUID | None = Query(None, description="Optional requirement ID filter"),
    page: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> WorkflowListResponse:
    items, total = WorkflowService(db).list_workflows(
        project_id=project_id,
        limit=page.limit,
        offset=page.offset,
        requirement_id=requirement_id,
    )
    return WorkflowListResponse(
        items=[WorkflowRead.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowDetailRead,
    summary="Get detailed state of a workflow",
)
def get_workflow_detail(
    project_id: UUID,
    workflow_id: UUID,
    db: Session = Depends(get_db),
) -> WorkflowDetailRead:
    return WorkflowService(db).get_workflow_detail(project_id=project_id, workflow_id=workflow_id)


@router.get(
    "/workflows/{workflow_id}/history",
    response_model=WorkflowHistoryResponse,
    summary="Get event timeline history for a workflow",
)
def get_workflow_history(
    project_id: UUID,
    workflow_id: UUID,
    db: Session = Depends(get_db),
) -> WorkflowHistoryResponse:
    events = WorkflowService(db).get_workflow_history(project_id=project_id, workflow_id=workflow_id)
    return WorkflowHistoryResponse(
        workflow_id=workflow_id,
        events=events,
        total=len(events),
    )


@router.post(
    "/workflows/{workflow_id}/approval",
    response_model=WorkflowDetailRead,
    summary="Submit human approval decision and resume paused workflow",
)
def submit_approval(
    project_id: UUID,
    workflow_id: UUID,
    payload: WorkflowApprovalRequest,
    db: Session = Depends(get_db),
) -> WorkflowDetailRead:
    WorkflowService(db).submit_approval(
        project_id=project_id,
        workflow_id=workflow_id,
        action=payload.action,
        notes=payload.notes,
        revision_instructions=payload.revision_instructions,
    )
    return WorkflowService(db).get_workflow_detail(project_id=project_id, workflow_id=workflow_id)
