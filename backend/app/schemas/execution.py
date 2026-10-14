from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import DefectStatus, EvidenceType, ExecutionStatus, Severity
from app.schemas.common import APIModel, PageMeta


class ExecutionTriggerRequest(APIModel):
    executor: str | None = Field(default=None, description="Optional runner override: playwright, httpx, or pytest")


class TestCaseSnapshotRead(APIModel):
    test_case_id: UUID
    title: str
    version: int = 1
    test_type: str
    priority: str
    target_url: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    expected_result: str
    requirement_id: UUID
    requirement_title: str | None = None
    project_id: UUID | None = None
    snapshot_at: datetime


class StepExecutionResultRead(APIModel):
    step_index: int
    action: str
    status: str
    expected: str | None = None
    actual: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    duration_ms: float = 0.0
    error_message: str | None = None
    error_details: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "expected_result" not in data and "expected" in data:
                data["expected_result"] = data["expected"]
            elif "expected" not in data and "expected_result" in data:
                data["expected"] = data["expected_result"]
            if "actual_result" not in data and "actual" in data:
                data["actual_result"] = data["actual"]
            elif "actual" not in data and "actual_result" in data:
                data["actual"] = data["actual_result"]
            if "error_details" not in data and "error_message" in data:
                data["error_details"] = data["error_message"]
            elif "error_message" not in data and "error_details" in data:
                data["error_message"] = data["error_details"]
        return data



class ExecutionSummaryRead(APIModel):
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    error_steps: int = 0
    skipped_steps: int = 0
    duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    error_category: str | None = None
    failed_step_index: int | None = None
    failure_explanation: str | None = None
    sanitized_failure_reason: str | None = None
    evidence_count: int = 0
    step_results: list[StepExecutionResultRead] = Field(default_factory=list)
    test_case_snapshot: TestCaseSnapshotRead | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_summary_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Duration aliases: duration_ms <-> total_duration_ms (preserve 0.0)
            duration = data.get("duration_ms")
            if duration is None:
                duration = data.get("total_duration_ms")
            if duration is not None:
                try:
                    dur_val = float(duration)
                except (ValueError, TypeError):
                    dur_val = 0.0
                data["duration_ms"] = dur_val
                data["total_duration_ms"] = dur_val
            else:
                data.setdefault("duration_ms", 0.0)
                data.setdefault("total_duration_ms", 0.0)

            # Failure reason aliases: sanitized_failure_reason <-> failure_explanation
            reason = data.get("sanitized_failure_reason")
            if reason is None:
                reason = data.get("failure_explanation")
            if reason is not None:
                data["sanitized_failure_reason"] = reason
                data["failure_explanation"] = reason
        return data



class ExecutionRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    test_case_id: UUID
    status: ExecutionStatus
    executor: str | None
    run_reference: str | None
    summary: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ExecutionListResponse(PageMeta):
    items: list[ExecutionRead] = Field(default_factory=list)


class EvidenceRead(APIModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: UUID
    execution_id: UUID
    evidence_type: EvidenceType
    uri: str
    label: str | None
    content_type: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_", serialization_alias="metadata")
    created_at: datetime


class EvidenceListResponse(PageMeta):
    items: list[EvidenceRead] = Field(default_factory=list)


class DefectRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    execution_id: UUID
    title: str
    description: str
    severity: Severity
    status: DefectStatus
    fingerprint: str | None
    created_at: datetime
    updated_at: datetime


class DefectListResponse(PageMeta):
    items: list[DefectRead] = Field(default_factory=list)


class ExecutionDetailResponse(APIModel):
    id: UUID
    test_case_id: UUID
    status: ExecutionStatus
    executor: str | None = None
    run_reference: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    test_case_snapshot: TestCaseSnapshotRead | None = None
    summary: ExecutionSummaryRead
    step_results: list[StepExecutionResultRead] = Field(default_factory=list)
    evidence: list[EvidenceRead] = Field(default_factory=list)
    evidence_items: list[EvidenceRead] = Field(default_factory=list)
    defects: list[DefectRead] = Field(default_factory=list)


class ExecutionFailureContext(APIModel):
    """Stable Phase 7 data contract for AI failure analysis."""

    execution_id: UUID
    test_case_id: UUID
    requirement_id: UUID
    project_id: UUID
    test_case_title: str
    test_case_version: int = 1
    test_type: str
    status: ExecutionStatus
    executor: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    failed_step_index: int | None = None
    sanitized_failure_reason: str | None = None
    failed_step: StepExecutionResultRead | None = None
    steps: list[StepExecutionResultRead] = Field(default_factory=list)
    step_results: list[StepExecutionResultRead] = Field(default_factory=list)
    test_case_snapshot: TestCaseSnapshotRead | None = None
    logs: list[str] = Field(default_factory=list)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceRead] = Field(default_factory=list)
    defects: list[DefectRead] = Field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
