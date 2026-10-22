from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import WorkflowApprovalAction, WorkflowStage, WorkflowStatus
from app.schemas.execution import ExecutionRead
from app.schemas.failure_analysis import ExecutionFailureAnalysisRead
from app.schemas.test_case import TestCaseRead


class WorkflowStartRequest(BaseModel):
    requirement_id: UUID = Field(..., description="Target requirement identifier for workflow orchestration.")
    notes: str | None = Field(default=None, max_length=1000, description="Optional orchestration context or notes.")


class WorkflowApprovalRequest(BaseModel):
    action: WorkflowApprovalAction = Field(..., description="Decision action: 'approve', 'reject', or 'request_revision'.")
    notes: str | None = Field(default=None, max_length=1000, description="Optional decision explanation or notes.")
    revision_instructions: str | None = Field(
        default=None,
        max_length=2000,
        description="Required if action is 'request_revision' to guide regeneration of test cases.",
    )
    @model_validator(mode="after")
    def validate_revision_instructions(self) -> "WorkflowApprovalRequest":
        if self.action == WorkflowApprovalAction.REQUEST_REVISION:
            if not self.revision_instructions or not self.revision_instructions.strip():
                raise ValueError("revision_instructions must be provided and non-empty when action is 'request_revision'.")
            self.revision_instructions = self.revision_instructions.strip()
        return self


class WorkflowEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    stage: str
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    requirement_id: UUID
    thread_id: str
    status: WorkflowStatus
    current_stage: str
    approval_status: str
    approval_decision: dict[str, Any] = Field(default_factory=dict)
    generated_test_case_ids: list[str] = Field(default_factory=list)
    execution_ids: list[str] = Field(default_factory=list)
    failure_analysis_id: UUID | None = None
    error_message: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_",
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None



class WorkflowListResponse(BaseModel):
    items: list[WorkflowRead]
    total: int


class WorkflowDetailRead(WorkflowRead):
    requirement_title: str | None = None
    generated_test_cases: list[TestCaseRead] = Field(default_factory=list)
    executions: list[ExecutionRead] = Field(default_factory=list)
    failure_analysis: ExecutionFailureAnalysisRead | None = None
    events: list[WorkflowEventRead] = Field(default_factory=list)


class WorkflowHistoryResponse(BaseModel):
    workflow_id: UUID
    events: list[WorkflowEventRead]
    total: int
