from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import EvidenceType, ExecutionStatus


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

        return {
            "total_steps": total,
            "passed_steps": passed,
            "failed_steps": failed,
            "error_steps": errors,
            "skipped_steps": skipped,
            "total_duration_ms": round(duration_ms, 2),
            "step_results": [step.model_dump() for step in self.step_results],
        }
