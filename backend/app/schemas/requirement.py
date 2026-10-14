from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.url_utils import validate_and_normalize_url
from app.models.enums import RequirementStatus
from app.schemas.common import APIModel, PageMeta


class RequirementCreate(APIModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50_000)
    target_url: str | None = Field(default=None, max_length=2048)
    status: RequirementStatus = RequirementStatus.DRAFT
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            return validate_and_normalize_url(v)
        return None


class RequirementUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=50_000)
    target_url: str | None = Field(default=None, max_length=2048)
    status: RequirementStatus | None = None
    acceptance_criteria: list[str] | None = Field(default=None, max_length=100)

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            return validate_and_normalize_url(v)
        return None


class RequirementRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    project_id: UUID
    title: str
    description: str
    target_url: str | None = None
    status: RequirementStatus
    acceptance_criteria: list[str]
    created_at: datetime
    updated_at: datetime


class RequirementListResponse(PageMeta):
    items: list[RequirementRead] = Field(default_factory=list)
