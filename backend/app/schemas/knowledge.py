from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeRecordType(StrEnum):
    """Enumeration of historical QA knowledge sources."""

    DEFECT = "defect"
    FAILURE_ANALYSIS = "failure_analysis"
    TEST_CASE = "test_case"


class PreparedKnowledgeDocument(BaseModel):
    """
    Standardized, serializable document representation for historical knowledge
    prepared for embedding generation and vector search indexing.
    """

    model_config = ConfigDict(from_attributes=True)

    record_type: KnowledgeRecordType
    source_id: str
    project_id: str
    title: str
    search_text: str
    is_verified_resolution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class IndexingErrorItem(BaseModel):
    """Details of a single document indexing failure."""

    source_id: str | None = None
    record_type: str | None = None
    error: str


class KnowledgeIndexResult(BaseModel):
    """Structured report returned upon completion of a project knowledge indexing run."""

    total_discovered: int = 0
    total_prepared: int = 0
    total_indexed: int = 0
    total_failed: int = 0
    errors: list[IndexingErrorItem] = Field(default_factory=list)
    is_successful: bool = True


class KnowledgeIndexRequest(BaseModel):
    """Optional parameters for project knowledge indexing."""

    record_types: list[KnowledgeRecordType] | None = None


class HistoricalCandidateItem(BaseModel):
    """A matched historical knowledge record retrieved via semantic similarity."""

    model_config = ConfigDict(from_attributes=True)

    record_type: KnowledgeRecordType
    source_id: str
    project_id: str
    title: str
    search_text: str
    similarity_score: float
    is_verified_resolution: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    """Request payload for semantic retrieval across historical QA intelligence."""

    query: str = Field(..., min_length=1, max_length=5000, description="Failure description, error trace, or question")
    record_types: list[KnowledgeRecordType] | None = Field(
        default=None,
        description="Optional filter by record type(s) (defect, failure_analysis, test_case)",
    )
    limit: int = Field(default=5, ge=1, le=50, description="Maximum number of historical candidates to return")
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum cosine similarity score threshold (0.0 to 1.0)",
    )


class KnowledgeSearchResponse(BaseModel):
    """Structured response containing ranked historical candidates matching the query."""

    query: str
    total_found: int
    candidates: list[HistoricalCandidateItem] = Field(default_factory=list)


class KnowledgeIndexingJobRead(BaseModel):
    """Read representation of a durable knowledge indexing job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    record_type: str
    source_id: UUID
    action: str
    status: str
    retry_count: int
    max_retries: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class KnowledgeIndexingJobListResponse(BaseModel):
    """List response for knowledge indexing jobs with summary counters."""

    items: list[KnowledgeIndexingJobRead] = Field(default_factory=list)
    total: int
    pending_count: int
    failed_count: int


class KnowledgeIndexingJobProcessResponse(BaseModel):
    """Structured report returned after processing queued indexing jobs."""

    processed_count: int
    success_count: int
    failure_count: int
