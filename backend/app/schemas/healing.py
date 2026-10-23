from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.enums import HealingStatus
from app.schemas.common import APIModel, PageMeta


class CandidateValidationResult(APIModel):
    selector: dict[str, Any]
    selector_type: str
    match_count: int
    is_visible: bool = False
    is_enabled: bool = False
    is_actionable: bool = False
    score: float = 0.0
    valid: bool = False
    rejection_reason: str | None = None
    confidence_explanation: str | None = None


class HealingProposalRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    project_id: UUID
    test_case_id: UUID
    original_execution_id: UUID
    retry_execution_id: UUID | None = None
    step_index: int
    action_type: str
    original_selector: dict[str, Any]
    proposed_selector: dict[str, Any]
    approved_selector: dict[str, Any] | None = None
    status: HealingStatus
    failure_reason: str
    failure_category: str
    page_url: str | None = None
    page_title: str | None = None
    dom_context: dict[str, Any] = Field(default_factory=dict)
    candidate_validation_results: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float
    explanation: str | None = None
    decision_notes: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    repaired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HealingProposalListResponse(PageMeta):
    items: list[HealingProposalRead] = Field(default_factory=list)


class HealingApprovalRequest(APIModel):
    decision_notes: str | None = None
    approved_by: str = "QA Engineer"
    selector_override: dict[str, Any] | None = None


class HealingRejectionRequest(APIModel):
    decision_notes: str | None = None
    rejected_by: str = "QA Engineer"
