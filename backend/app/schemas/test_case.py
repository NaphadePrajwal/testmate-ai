from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.enums import Priority, TestCaseStatus, TestType
from app.schemas.common import APIModel, PageMeta


class TestStep(APIModel):
    action: str = Field(min_length=1, max_length=2_000)
    expected_result: str | None = Field(default=None, max_length=5_000)
    data: dict[str, Any] = Field(default_factory=dict)


class TestCaseCreate(APIModel):
    requirement_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50_000)
    preconditions: list[str] = Field(default_factory=list, max_length=100)
    steps: list[TestStep] = Field(default_factory=list, max_length=200)
    expected_result: str = Field(min_length=1, max_length=50_000)
    test_type: TestType
    priority: Priority = Priority.MEDIUM
    status: TestCaseStatus = TestCaseStatus.DRAFT


class TestCaseUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50_000)
    preconditions: list[str] | None = Field(default=None, max_length=100)
    steps: list[TestStep] | None = Field(default=None, max_length=200)
    expected_result: str | None = Field(default=None, min_length=1, max_length=50_000)
    test_type: TestType | None = None
    priority: Priority | None = None
    status: TestCaseStatus | None = None


class TestCaseRead(APIModel):
    model_config = {"from_attributes": True}

    id: UUID
    requirement_id: UUID
    title: str
    description: str | None
    preconditions: list[str]
    steps: list[TestStep]
    expected_result: str
    test_type: TestType
    priority: Priority
    status: TestCaseStatus
    version: int
    created_at: datetime
    updated_at: datetime


class TestCaseListResponse(PageMeta):
    items: list[TestCaseRead] = Field(default_factory=list)
