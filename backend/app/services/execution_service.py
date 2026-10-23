from datetime import datetime, timezone
import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.defect import Defect
from app.models.enums import (
    DefectStatus,
    EvidenceType,
    ExecutionStatus,
    ReviewStatus,
    Severity,
    TestCaseStatus,
    TestType,
    VerificationStatus,
)
from app.models.execution_evidence import ExecutionEvidence
from app.models.knowledge_indexing_job import IndexingJobAction
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.execution import (
    DefectRead,
    DefectUpdate,
    EvidenceRead,
    ExecutionDetailResponse,
    ExecutionFailureContext,
    ExecutionSummaryRead,
    StepExecutionResultRead,
    TestCaseSnapshotRead,
)
from app.schemas.knowledge import KnowledgeRecordType
from app.services.database import commit_or_rollback
from app.services.knowledge_indexing_job_service import KnowledgeIndexingJobService
from app.services.project_service import ProjectService
from app.testing.contract import ErrorCategory, TestCaseSnapshot
from app.testing.evidence_manager import EvidenceManager
from app.testing.httpx_runner import HttpxApiRunner
from app.testing.playwright_runner import PlaywrightWebRunner
from app.testing.pytest_runner import PytestRunner

logger = logging.getLogger(__name__)


class ExecutionService:
    """Read models for execution artifacts, populated by later execution workflows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _project_execution_query(self, project_id: UUID):
        return select(TestExecution).join(TestCase).join(Requirement).where(Requirement.project_id == project_id)

    def get_execution(self, project_id: UUID, execution_id: UUID) -> TestExecution:
        execution = self.db.scalar(self._project_execution_query(project_id).where(TestExecution.id == execution_id))
        if execution is None:
            raise ResourceNotFoundError("Execution not found for this project.")
        return execution

    def list_executions(
        self, project_id: UUID, limit: int, offset: int, status: str | None, test_case_id: UUID | None
    ) -> tuple[list[TestExecution], int]:
        ProjectService(self.db).get_project(project_id)
        statement = self._project_execution_query(project_id)
        if status is not None:
            statement = statement.where(TestExecution.status == status)
        if test_case_id is not None:
            statement = statement.where(TestExecution.test_case_id == test_case_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        return list(self.db.scalars(statement.order_by(TestExecution.created_at.desc()).offset(offset).limit(limit))), total

    def list_test_case_history(
        self,
        project_id: UUID,
        test_case_id: UUID,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[TestExecution], int]:
        """List historical executions for a specific test case within a project, verifying project and test case existence."""
        ProjectService(self.db).get_project(project_id)

        test_case = self.db.scalar(
            select(TestCase)
            .join(Requirement)
            .where(TestCase.id == test_case_id, Requirement.project_id == project_id)
        )
        if test_case is None:
            raise ResourceNotFoundError("Test case not found for this project.")

        return self.list_executions(
            project_id=project_id,
            limit=limit,
            offset=offset,
            status=status,
            test_case_id=test_case_id,
        )

    def get_evidence(self, project_id: UUID, execution_id: UUID, evidence_id: UUID) -> ExecutionEvidence:
        evidence = self.db.scalar(
            select(ExecutionEvidence)
            .join(TestExecution)
            .join(TestCase)
            .join(Requirement)
            .where(
                ExecutionEvidence.id == evidence_id,
                ExecutionEvidence.execution_id == execution_id,
                Requirement.project_id == project_id,
            )
        )
        if evidence is None:
            raise ResourceNotFoundError("Evidence not found for this project execution.")
        return evidence

    def list_evidence(
        self, project_id: UUID, execution_id: UUID, limit: int, offset: int
    ) -> tuple[list[ExecutionEvidence], int]:
        self.get_execution(project_id, execution_id)
        statement = select(ExecutionEvidence).where(ExecutionEvidence.execution_id == execution_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        return list(self.db.scalars(statement.order_by(ExecutionEvidence.created_at.desc()).offset(offset).limit(limit))), total

    def get_defect(self, project_id: UUID, defect_id: UUID) -> Defect:
        defect = self.db.scalar(
            select(Defect)
            .join(TestExecution)
            .join(TestCase)
            .join(Requirement)
            .where(Defect.id == defect_id, Requirement.project_id == project_id)
        )
        if defect is None:
            raise ResourceNotFoundError("Defect not found for this project.")
        return defect

    def list_defects(
        self, project_id: UUID, limit: int, offset: int, status: str | None, severity: str | None
    ) -> tuple[list[Defect], int]:
        ProjectService(self.db).get_project(project_id)
        statement = select(Defect).join(TestExecution).join(TestCase).join(Requirement).where(Requirement.project_id == project_id)
        if status is not None:
            statement = statement.where(Defect.status == status)
        if severity is not None:
            statement = statement.where(Defect.severity == severity)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        return list(self.db.scalars(statement.order_by(Defect.created_at.desc()).offset(offset).limit(limit))), total

    def update_defect(self, project_id: UUID, defect_id: UUID, payload: DefectUpdate) -> Defect:
        """
        Update an existing defect record, enforce technical resolution verification criteria,
        and trigger automatic knowledge index synchronization.
        """
        defect = self.get_defect(project_id, defect_id)
        values = payload.model_dump(exclude_unset=True)

        # Verification validation rules
        if "verification_status" in values and values["verification_status"] is not None:
            target_status = values["verification_status"]
            if target_status == VerificationStatus.VERIFIED:
                notes = values.get("resolution_notes") if "resolution_notes" in values else defect.resolution_notes
                if not notes or not notes.strip():
                    raise ResourceConflictError("Cannot mark defect resolution as verified without documented technical resolution notes.")
                defect.verification_status = VerificationStatus.VERIFIED
                defect.verified_at = datetime.now(timezone.utc)
                if "verification_method" in values and values["verification_method"]:
                    defect.verification_method = values["verification_method"]
                elif not defect.verification_method:
                    defect.verification_method = "manual_verification"
                if "verification_evidence" in values:
                    defect.verification_evidence = values["verification_evidence"]
            elif target_status in (VerificationStatus.UNVERIFIED, VerificationStatus.REVOKED):
                defect.verification_status = target_status
                defect.verified_at = None

        for field in ("title", "description", "severity", "status", "resolution_notes", "verification_method", "verification_evidence"):
            if field in values and values[field] is not None:
                setattr(defect, field, values[field])

        commit_or_rollback(self.db)
        self.db.refresh(defect)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.DEFECT, defect.id)
        return defect

    def _trigger_auto_indexing(
        self,
        project_id: UUID,
        record_type: KnowledgeRecordType | str,
        source_id: UUID,
        action: IndexingJobAction | str = IndexingJobAction.UPSERT,
    ) -> None:
        """Enqueue durable indexing job and attempt safe immediate processing."""
        try:
            job_svc = KnowledgeIndexingJobService(db=self.db)
            job = job_svc.enqueue_job(
                project_id=project_id,
                record_type=record_type,
                source_id=source_id,
                action=action,
            )
            job_svc.process_job(job.id)
        except Exception as exc:
            logger.warning("Automatic indexing trigger failed for %s (%s): %s", record_type, source_id, exc)

    def execute_test_case(
        self,
        project_id: UUID,
        test_case_id: UUID,
        executor_override: str | None = None,
    ) -> TestExecution:
        """Trigger an automated execution run for an approved test case."""
        ProjectService(self.db).get_project(project_id)

        test_case = self.db.scalar(
            select(TestCase)
            .options(joinedload(TestCase.requirement))
            .join(Requirement)
            .where(TestCase.id == test_case_id, Requirement.project_id == project_id)
        )
        if test_case is None:
            raise ResourceNotFoundError("Test case not found for this project.")

        # Phase 5 Requirement: Only approved test cases can be executed
        if test_case.review_status != ReviewStatus.APPROVED or test_case.status != TestCaseStatus.APPROVED:
            raise ResourceConflictError("Only approved test cases are eligible for execution.")

        settings = get_settings()
        evidence_manager = EvidenceManager(settings)

        # Determine runner
        raw_executor = (executor_override or "").lower().strip()
        if raw_executor in ("playwright", "httpx", "pytest"):
            runner_name = raw_executor
        elif test_case.test_type == TestType.WEB:
            runner_name = "playwright"
        elif test_case.test_type == TestType.API:
            runner_name = "httpx"
        else:
            runner_name = "pytest"

        if runner_name == "playwright":
            runner = PlaywrightWebRunner(settings, evidence_manager)
        elif runner_name == "httpx":
            runner = HttpxApiRunner(settings, evidence_manager)
        elif runner_name == "pytest":
            runner = PytestRunner(settings, evidence_manager)
        else:
            raise ResourceConflictError(f"Unsupported executor: '{raw_executor}'. Must be playwright, httpx, or pytest.")

        executor_display = executor_override or runner_name

        # Create immutable execution record in QUEUED state
        now = datetime.now(timezone.utc)
        execution = TestExecution(
            id=uuid4(),
            test_case_id=test_case.id,
            status=ExecutionStatus.QUEUED,
            executor=executor_display,
            run_reference=f"run-{uuid4().hex[:12]}",
            summary={},
            error_message=None,
            started_at=now,
            completed_at=None,
            created_at=now,
        )
        self.db.add(execution)
        commit_or_rollback(self.db)

        # Capture immutable test case snapshot at execution time
        snapshot = TestCaseSnapshot.from_test_case(test_case)

        # Transition to RUNNING state
        execution.status = ExecutionStatus.RUNNING
        commit_or_rollback(self.db)

        try:
            outcome = runner.execute(test_case, execution.id)
            outcome.test_case_snapshot = snapshot
            execution.status = outcome.status
            execution.completed_at = outcome.completed_at
            execution.summary = outcome.summary_dict
            execution.error_message = outcome.error_message

            # Save execution evidence
            for ev in outcome.evidence_items:
                evidence_row = ExecutionEvidence(
                    id=uuid4(),
                    execution_id=execution.id,
                    evidence_type=ev.evidence_type,
                    uri=ev.uri,
                    label=ev.label,
                    content_type=ev.content_type,
                    metadata_=ev.metadata,
                )
                self.db.add(evidence_row)

            # Auto-record defect upon execution failure
            created_defect: Defect | None = None
            if outcome.status == ExecutionStatus.FAILED and outcome.error_message:
                defect = Defect(
                    id=uuid4(),
                    execution_id=execution.id,
                    title=f"Execution Failed: {test_case.title}",
                    description=f"Automated test execution failed.\n\nError: {outcome.error_message}",
                    severity=Severity.HIGH,
                    status=DefectStatus.NEW,
                    fingerprint=f"{test_case.id}-{execution.id}",
                )
                self.db.add(defect)
                created_defect = defect

            # Auto-record self-healing proposal if eligible selector failure
            if outcome.status == ExecutionStatus.FAILED and outcome.healing_context:
                from app.services.self_healing_service import SelfHealingService
                try:
                    hc = outcome.healing_context
                    SelfHealingService(self.db).create_proposal_from_failure(
                        project_id=project_id,
                        test_case_id=test_case.id,
                        execution_id=execution.id,
                        step_index=hc["step_index"],
                        action_type=hc["action_type"],
                        original_selector=hc["original_selector"],
                        failure_reason=hc["failure_reason"],
                        failure_category=hc["failure_category"],
                        page_url=hc.get("page_url"),
                        page_title=hc.get("page_title"),
                        dom_context=hc.get("dom_context", {}),
                        candidate_validation_results=hc.get("candidate_validation_results", []),
                    )
                except Exception as heal_persist_exc:
                    logger.warning("Could not persist healing proposal: %s", heal_persist_exc)

            commit_or_rollback(self.db)
            if created_defect is not None:
                self._trigger_auto_indexing(project_id, KnowledgeRecordType.DEFECT, created_defect.id)

        except Exception as exc:
            execution.status = ExecutionStatus.ERROR
            execution.completed_at = datetime.now(timezone.utc)
            execution.error_message = str(exc)
            execution.summary = {
                "total_steps": len(test_case.steps or []),
                "passed_steps": 0,
                "failed_steps": 0,
                "skipped_steps": len(test_case.steps or []),
                "duration_ms": 0.0,
                "total_duration_ms": 0.0,
                "error_category": ErrorCategory.INFRASTRUCTURE_ERROR.value,
                "failed_step_index": None,
                "failure_explanation": str(exc),
                "sanitized_failure_reason": str(exc),
                "test_case_snapshot": snapshot.model_dump(mode="json"),
                "step_results": [],
            }
            commit_or_rollback(self.db)

        return execution

    def get_execution_detail(self, project_id: UUID, execution_id: UUID) -> ExecutionDetailResponse:
        """Retrieve complete structured execution result, step results, snapshot, evidence, and defects."""
        execution = self.get_execution(project_id, execution_id)
        raw_summary = execution.summary or {}

        # Parse test case snapshot (fall back to current test case if run before Phase 6)
        snapshot_data = raw_summary.get("test_case_snapshot")
        if snapshot_data:
            snapshot = TestCaseSnapshotRead.model_validate(snapshot_data)
        elif execution.test_case:
            snapshot = TestCaseSnapshotRead.model_validate(
                TestCaseSnapshot.from_test_case(execution.test_case).model_dump(mode="json")
            )
        else:
            snapshot = None

        # Parse step results
        raw_steps = raw_summary.get("step_results") or []
        step_results = [StepExecutionResultRead.model_validate(s) for s in raw_steps]

        # Parse summary with dual-key duration and failure reason fallbacks (preserving 0.0)
        duration_val = raw_summary.get("duration_ms")
        if duration_val is None:
            duration_val = raw_summary.get("total_duration_ms")
        if duration_val is None:
            duration_val = 0.0

        failure_reason = raw_summary.get("sanitized_failure_reason")
        if failure_reason is None:
            failure_reason = raw_summary.get("failure_explanation")

        summary = ExecutionSummaryRead(
            total_steps=raw_summary.get("total_steps", 0),
            passed_steps=raw_summary.get("passed_steps", 0),
            failed_steps=raw_summary.get("failed_steps", 0),
            error_steps=raw_summary.get("error_steps", 0),
            skipped_steps=raw_summary.get("skipped_steps", 0),
            duration_ms=float(duration_val),
            total_duration_ms=float(duration_val),
            error_category=raw_summary.get("error_category"),
            failed_step_index=raw_summary.get("failed_step_index"),
            failure_explanation=failure_reason,
            sanitized_failure_reason=failure_reason,
            evidence_count=raw_summary.get("evidence_count", len(raw_summary.get("evidence_items", []))),
            step_results=step_results,
            test_case_snapshot=snapshot,
        )

        evidence_rows = list(
            self.db.scalars(
                select(ExecutionEvidence)
                .where(ExecutionEvidence.execution_id == execution.id)
                .order_by(ExecutionEvidence.created_at.asc())
            )
        )
        evidence_reads = [EvidenceRead.model_validate(e) for e in evidence_rows]

        defect_rows = list(
            self.db.scalars(
                select(Defect)
                .where(Defect.execution_id == execution.id)
                .order_by(Defect.created_at.asc())
            )
        )
        defect_reads = [DefectRead.model_validate(d) for d in defect_rows]

        return ExecutionDetailResponse(
            id=execution.id,
            test_case_id=execution.test_case_id,
            status=execution.status,
            executor=execution.executor,
            run_reference=execution.run_reference,
            error_message=execution.error_message,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            created_at=execution.created_at,
            test_case_snapshot=snapshot,
            summary=summary,
            step_results=step_results,
            evidence=evidence_reads,
            evidence_items=evidence_reads,
            defects=defect_reads,
        )

    def get_execution_for_analysis(self, project_id: UUID, execution_id: UUID) -> ExecutionFailureContext:
        """Stable service-layer contract for Phase 7 AI failure analysis consumption."""
        detail = self.get_execution_detail(project_id, execution_id)
        execution = self.get_execution(project_id, execution_id)

        # Resolve requirement_id from snapshot first, then relation
        if detail.test_case_snapshot and detail.test_case_snapshot.requirement_id:
            requirement_id = detail.test_case_snapshot.requirement_id
        elif execution.test_case and execution.test_case.requirement_id:
            requirement_id = execution.test_case.requirement_id
        else:
            requirement_id = uuid4()

        test_case_title = (
            detail.test_case_snapshot.title
            if detail.test_case_snapshot
            else (execution.test_case.title if execution.test_case else "Unknown Test Case")
        )
        test_case_version = (
            detail.test_case_snapshot.version
            if detail.test_case_snapshot
            else (execution.test_case.version if execution.test_case else 1)
        )
        test_type_str = (
            detail.test_case_snapshot.test_type
            if detail.test_case_snapshot
            else (
                execution.test_case.test_type.value
                if execution.test_case and hasattr(execution.test_case.test_type, "value")
                else "manual"
            )
        )

        # Extract textual logs from step error details or log-type evidence
        extracted_logs: list[str] = []
        for step in detail.step_results:
            if step.error_details:
                extracted_logs.append(f"Step {step.step_index} Error: {step.error_details}")
            if step.actual_result:
                extracted_logs.append(f"Step {step.step_index} Observed: {step.actual_result}")

        for ev in detail.evidence:
            if ev.evidence_type == EvidenceType.LOG and ev.label:
                extracted_logs.append(f"Evidence [{ev.label}]: {ev.uri}")

        summary = detail.summary
        duration = float(summary.duration_ms) if (summary and summary.duration_ms is not None) else 0.0
        sanitized_failure = summary.sanitized_failure_reason if summary else None
        if sanitized_failure is None and detail.error_message:
            sanitized_failure = detail.error_message

        failed_step = None
        if summary and summary.failed_step_index is not None:
            failed_step = next(
                (s for s in detail.step_results if s.step_index == summary.failed_step_index), None
            )

        return ExecutionFailureContext(
            execution_id=detail.id,
            test_case_id=detail.test_case_id,
            project_id=project_id,
            requirement_id=requirement_id,
            test_case_title=test_case_title,
            test_case_version=test_case_version,
            test_type=test_type_str,
            executor=detail.executor,
            status=detail.status,
            error_message=detail.error_message,
            error_category=summary.error_category if summary else None,
            failed_step_index=summary.failed_step_index if summary else None,
            sanitized_failure_reason=sanitized_failure,
            failed_step=failed_step,
            duration_ms=duration,
            test_case_snapshot=detail.test_case_snapshot,
            step_results=detail.step_results,
            steps=detail.step_results,
            evidence=detail.evidence,
            defects=detail.defects,
            logs=extracted_logs,
        )
