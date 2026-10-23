from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class ExecutionTrendPoint(APIModel):
    """Aggregated test execution metrics for a specific day."""
    date: str  # YYYY-MM-DD
    passed: int = 0
    failed: int = 0
    error: int = 0
    total: int = 0


class RecentExecutionItem(APIModel):
    """Recent execution summary item for dashboard activity streams."""
    id: UUID
    test_case_id: UUID
    test_case_title: str
    status: str
    executor: str | None = None
    duration_ms: float | None = None
    created_at: datetime


class ProjectAnalyticsResponse(APIModel):
    """Project-level testing analytics and metrics summary."""
    project_id: UUID
    project_name: str

    # Core Counts
    total_requirements: int = 0
    total_test_cases: int = 0
    total_test_executions: int = 0

    # Execution Status Breakdown
    passed_executions: int = 0
    failed_executions: int = 0
    running_executions: int = 0
    pending_executions: int = 0
    error_executions: int = 0

    # Rates
    execution_pass_rate: float = 0.0  # passed / (passed + failed + error) * 100
    requirement_coverage_rate: float = 0.0  # covered_requirements / total_requirements * 100

    # Defect Breakdown
    total_defects: int = 0
    open_defects: int = 0
    critical_defects: int = 0
    high_defects: int = 0
    medium_defects: int = 0
    low_defects: int = 0
    defects_by_status: dict[str, int] = Field(default_factory=dict)
    defects_by_severity: dict[str, int] = Field(default_factory=dict)

    # Time Trends & Recent Activity
    execution_trends: list[ExecutionTrendPoint] = Field(default_factory=list)
    recent_executions: list[RecentExecutionItem] = Field(default_factory=list)


class TraceabilityTestCaseItem(APIModel):
    """Test case summary inside requirement traceability matrix."""
    id: UUID
    title: str
    test_type: str
    review_status: str
    status: str
    latest_execution_status: str | None = None


class TraceabilityItem(APIModel):
    """Requirement-to-test traceability entry."""
    requirement_id: UUID
    requirement_title: str
    requirement_status: str
    test_cases_count: int = 0
    coverage_status: str = "uncovered"  # "covered" | "uncovered"
    latest_execution_status: str | None = None  # "passed" | "failed" | "error" | None
    test_cases: list[TraceabilityTestCaseItem] = Field(default_factory=list)
    defect_count: int = 0


class ProjectTraceabilityResponse(APIModel):
    """Project requirement traceability matrix and orphaned record indicators."""
    project_id: UUID
    total_requirements: int = 0
    covered_requirements: int = 0
    uncovered_requirements: int = 0
    coverage_rate: float = 0.0
    requirements_without_cases: int = 0
    cases_without_executions: int = 0
    items: list[TraceabilityItem] = Field(default_factory=list)


class ProjectReportResponse(APIModel):
    """Comprehensive executive project report."""
    project_id: UUID
    project_name: str
    project_description: str | None = None
    created_at: datetime
    analytics: ProjectAnalyticsResponse
    traceability_summary: ProjectTraceabilityResponse
    quality_score: float = 0.0
