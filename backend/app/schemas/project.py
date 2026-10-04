from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, PageMeta


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)


class ProjectUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)


class ProjectRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    description: str | None
    created_at: datetime


class ProjectListResponse(PageMeta):
    items: list[ProjectRead] = Field(default_factory=list)
