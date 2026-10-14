from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import APIModel, PageMeta


class FailureCategory(StrEnum):
    ASSERTION_FAILURE = "assertion_failure"
    APPLICATION_ERROR = "application_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ELEMENT_NOT_FOUND = "element_not_found"
    SECURITY_VIOLATION = "security_violation"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FailureAnalysisContent(BaseModel):
    """Raw structured diagnosis produced by the AI model."""

    failure_category: FailureCategory = Field(
        description="The primary category of failure based strictly on observed evidence."
    )
    summary: str = Field(
        description="A concise 1-2 sentence summary of what failed."
    )
    observed_error: str = Field(
        description="The specific observed error message, failed step, and expected vs actual behavior."
    )
    likely_root_cause: str = Field(
        description="The hypothesized root cause deduced from the execution evidence."
    )
    supporting_evidence: list[str] = Field(
        default_factory=list,
        description="Key points of evidence from the execution context (logs, step status, HTTP responses) supporting this diagnosis."
    )
    recommended_debugging_steps: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable debugging steps developers/QAs should take to investigate and resolve the issue."
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Confidence level in the root cause hypothesis: high, medium, or low."
    )
    uncertainty_notes: str | None = Field(
        default=None,
        description="Explicit notes on missing information, ambiguities, or inconclusive evidence."
    )


class FailureAnalysisMetadata(APIModel):
    provider: str
    model: str
    prompt_version: str
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionFailureAnalysisRead(APIModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: UUID
    execution_id: UUID
    project_id: UUID
    failure_category: str
    summary: str
    observed_error: str
    likely_root_cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    recommended_debugging_steps: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    uncertainty_notes: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_",
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


class ExecutionFailureAnalysisListResponse(PageMeta):
    items: list[ExecutionFailureAnalysisRead] = Field(default_factory=list)
