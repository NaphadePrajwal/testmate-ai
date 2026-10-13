from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import EvidenceType, ExecutionStatus


class ErrorCategory(StrEnum):
    ASSERTION_FAILURE = "assertion_failure"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ELEMENT_NOT_FOUND = "element_not_found"
    SECURITY_VIOLATION = "security_violation"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    UNSPECIFIED = "unspecified"


class TestCaseSnapshot(BaseModel):
    test_case_id: UUID
    title: str
    version: int = 1
    test_type: str
    priority: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    expected_result: str
    requirement_id: UUID
    requirement_title: str | None = None
    project_id: UUID | None = None
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_test_case(cls, test_case: Any) -> "TestCaseSnapshot":
        project_id = None
        req_title = None
        if hasattr(test_case, "requirement") and test_case.requirement:
            project_id = getattr(test_case.requirement, "project_id", None)
            req_title = getattr(test_case.requirement, "title", None)

        test_type_str = (
            test_case.test_type.value
            if hasattr(test_case.test_type, "value")
            else str(test_case.test_type)
        )
        priority_str = (
            test_case.priority.value
            if hasattr(test_case.priority, "value")
            else str(test_case.priority)
        )

        return cls(
            test_case_id=test_case.id,
            title=test_case.title,
            version=getattr(test_case, "version", 1),
            test_type=test_type_str,
            priority=priority_str,
            preconditions=list(test_case.preconditions or []),
            steps=list(test_case.steps or []),
            expected_result=test_case.expected_result,
            requirement_id=test_case.requirement_id,
            requirement_title=req_title,
            project_id=project_id,
        )



class StepExecutionResult(BaseModel):
    step_index: int
    action: str
    status: str = Field(description="passed | failed | error | skipped")
    expected: str | None = None
    actual: str | None = None
    duration_ms: float = 0.0
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EvidencePayload(BaseModel):
    evidence_type: EvidenceType
    uri: str
    label: str | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionOutcome(BaseModel):
    status: ExecutionStatus
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    error_message: str | None = None
    error_category: str | None = None
    failed_step_index: int | None = None
    test_case_snapshot: TestCaseSnapshot | None = None
    evidence_items: list[EvidencePayload] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def summary_dict(self) -> dict[str, Any]:
        total = len(self.step_results)
        passed = sum(1 for s in self.step_results if s.status == "passed")
        failed = sum(1 for s in self.step_results if s.status == "failed")
        errors = sum(1 for s in self.step_results if s.status == "error")
        skipped = sum(1 for s in self.step_results if s.status == "skipped")
        duration_ms = sum(s.duration_ms for s in self.step_results)

        # Automatically determine failed step index if not explicitly set
        failed_idx = self.failed_step_index
        if failed_idx is None:
            for s in self.step_results:
                if s.status in ("failed", "error"):
                    failed_idx = s.step_index
                    break

        # Automatically categorize error if not set
        err_cat = self.error_category
        if err_cat is None and self.error_message:
            msg_lower = self.error_message.lower()
            if "timeout" in msg_lower:
                err_cat = ErrorCategory.TIMEOUT.value
            elif "ssrf" in msg_lower or "security" in msg_lower or "blocked" in msg_lower:
                err_cat = ErrorCategory.SECURITY_VIOLATION.value
            elif "not found" in msg_lower or "locator" in msg_lower:
                err_cat = ErrorCategory.ELEMENT_NOT_FOUND.value
            elif "expected http" in msg_lower or "assertion" in msg_lower:
                err_cat = ErrorCategory.ASSERTION_FAILURE.value
            elif "connection" in msg_lower or "network" in msg_lower:
                err_cat = ErrorCategory.NETWORK_ERROR.value
            else:
                err_cat = ErrorCategory.INFRASTRUCTURE_ERROR.value

        dur_rounded = round(duration_ms, 2)
        summary = {
            "total_steps": total,
            "passed_steps": passed,
            "failed_steps": failed,
            "error_steps": errors,
            "skipped_steps": skipped,
            "duration_ms": dur_rounded,
            "total_duration_ms": dur_rounded,
            "error_category": err_cat,
            "failed_step_index": failed_idx,
            "failure_explanation": self.error_message,
            "sanitized_failure_reason": self.error_message,
            "evidence_count": len(self.evidence_items),
            "step_results": [step.model_dump() for step in self.step_results],
        }

        if self.test_case_snapshot:
            summary["test_case_snapshot"] = self.test_case_snapshot.model_dump(mode="json")

        return summary
