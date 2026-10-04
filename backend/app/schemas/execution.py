from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.enums import DefectStatus, EvidenceType, ExecutionStatus, Severity
from app.schemas.common import APIModel, PageMeta


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
