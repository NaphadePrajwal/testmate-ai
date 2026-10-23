from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.models.enums import HealingStatus
from app.models.healing_proposal import HealingProposal
from app.schemas.healing import (
    HealingApprovalRequest,
    HealingProposalListResponse,
    HealingProposalRead,
    HealingRejectionRequest,
)
from app.services.self_healing_service import SelfHealingService

router = APIRouter()


@router.get(
    "/healing-proposals",
    response_model=HealingProposalListResponse,
    status_code=status.HTTP_200_OK,
    summary="List self-healing proposals for a project",
)
def list_healing_proposals(
    project_id: UUID,
    page: Pagination = Depends(pagination_params),
    status_filter: Annotated[HealingStatus | None, Query(alias="status")] = None,
    test_case_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> HealingProposalListResponse:
    service = SelfHealingService(db)
    items, total = service.list_proposals(
        project_id=project_id,
        limit=page.limit,
        offset=page.offset,
        status=status_filter,
        test_case_id=test_case_id,
    )
    return HealingProposalListResponse(
        items=[HealingProposalRead.model_validate(p) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/healing-proposals/{proposal_id}",
    response_model=HealingProposalRead,
    status_code=status.HTTP_200_OK,
    summary="Get details of a self-healing proposal including candidate validation results",
)
def get_healing_proposal(
    project_id: UUID,
    proposal_id: UUID,
    db: Session = Depends(get_db),
) -> HealingProposalRead:
    service = SelfHealingService(db)
    proposal = service.get_proposal(project_id, proposal_id)
    return HealingProposalRead.model_validate(proposal)


@router.post(
    "/healing-proposals/{proposal_id}/approve",
    response_model=HealingProposalRead,
    status_code=status.HTTP_200_OK,
    summary="Approve a self-healing proposal, apply selector repair, and verify via re-execution",
)
def approve_healing_proposal(
    project_id: UUID,
    proposal_id: UUID,
    payload: HealingApprovalRequest | None = None,
    db: Session = Depends(get_db),
) -> HealingProposalRead:
    service = SelfHealingService(db)
    request = payload or HealingApprovalRequest()
    updated = service.approve_proposal(project_id, proposal_id, request)
    return HealingProposalRead.model_validate(updated)


@router.post(
    "/healing-proposals/{proposal_id}/reject",
    response_model=HealingProposalRead,
    status_code=status.HTTP_200_OK,
    summary="Reject a self-healing proposal and preserve original test definition unchanged",
)
def reject_healing_proposal(
    project_id: UUID,
    proposal_id: UUID,
    payload: HealingRejectionRequest | None = None,
    db: Session = Depends(get_db),
) -> HealingProposalRead:
    service = SelfHealingService(db)
    request = payload or HealingRejectionRequest()
    updated = service.reject_proposal(project_id, proposal_id, request)
    return HealingProposalRead.model_validate(updated)


@router.get(
    "/test-cases/{test_case_id}/healing-history",
    response_model=HealingProposalListResponse,
    status_code=status.HTTP_200_OK,
    summary="List healing proposal history for a specific test case",
)
def get_test_case_healing_history(
    project_id: UUID,
    test_case_id: UUID,
    page: Pagination = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> HealingProposalListResponse:
    service = SelfHealingService(db)
    items, total = service.list_proposals(
        project_id=project_id,
        limit=page.limit,
        offset=page.offset,
        test_case_id=test_case_id,
    )
    return HealingProposalListResponse(
        items=[HealingProposalRead.model_validate(p) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/executions/{execution_id}/healing-proposals",
    response_model=HealingProposalListResponse,
    status_code=status.HTTP_200_OK,
    summary="List healing proposals associated with a specific execution",
)
def get_execution_healing_proposals(
    project_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> HealingProposalListResponse:
    stmt = (
        select(HealingProposal)
        .where(
            HealingProposal.project_id == project_id,
            (HealingProposal.original_execution_id == execution_id)
            | (HealingProposal.retry_execution_id == execution_id),
        )
        .order_by(HealingProposal.created_at.desc())
    )
    items = list(db.scalars(stmt))
    return HealingProposalListResponse(
        items=[HealingProposalRead.model_validate(p) for p in items],
        total=len(items),
        limit=len(items),
        offset=0,
    )
