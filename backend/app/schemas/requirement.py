from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import RequirementStatus
from app.schemas.common import APIModel, PageMeta


class RequirementCreate(APIModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50_000)
    status: RequirementStatus = RequirementStatus.DRAFT
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)


class RequirementUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=50_000)
    status: RequirementStatus | None = None
    acceptance_criteria: list[str] | None = Field(default=None, max_length=100)


class RequirementRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    project_id: UUID
    title: str
    description: str
    status: RequirementStatus
    acceptance_criteria: list[str]
    created_at: datetime
    updated_at: datetime


class RequirementListResponse(PageMeta):
    items: list[RequirementRead] = Field(default_factory=list)
