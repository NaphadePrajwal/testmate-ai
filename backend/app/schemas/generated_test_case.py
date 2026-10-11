from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.enums import Priority, TestType
from app.schemas.common import APIModel
from app.schemas.test_case import TestCaseRead, TestStep


class TestCaseCategory(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    EDGE_CASE = "edge_case"
    SECURITY = "security"


class GeneratedStep(APIModel):
    action: str = Field(min_length=1, max_length=2_000)
    expected_result: str | None = Field(default=None, max_length=5_000)
    data: dict[str, Any] = Field(default_factory=dict)


class GeneratedTestCaseItem(APIModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5_000)
    category: TestCaseCategory = Field(default=TestCaseCategory.POSITIVE)
    test_type: TestType = Field(default=TestType.WEB)
    priority: Priority = Field(default=Priority.MEDIUM)
    preconditions: list[str] = Field(default_factory=list, max_length=100)
    steps: list[GeneratedStep] = Field(min_length=1, max_length=200)
    expected_result: str = Field(min_length=1, max_length=5_000)
    test_data: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list, max_length=50)


class GeneratedTestCaseCollection(APIModel):
    test_cases: list[GeneratedTestCaseItem] = Field(min_length=1, max_length=50)
    requirement_coverage_summary: str = Field(min_length=1, max_length=5_000)
    assumptions: list[str] = Field(default_factory=list, max_length=50)


class GenerationMetadata(APIModel):
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime


class GeneratedTestCasesResponse(APIModel):
    items: list[TestCaseRead] = Field(default_factory=list)
    total_generated: int
    requirement_coverage_summary: str
    assumptions: list[str] = Field(default_factory=list)
    metadata: GenerationMetadata
