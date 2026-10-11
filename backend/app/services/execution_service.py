from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.defect import Defect
from app.models.enums import DefectStatus, ExecutionStatus, ReviewStatus, Severity, TestCaseStatus, TestType
from app.models.execution_evidence import ExecutionEvidence
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.services.database import commit_or_rollback
from app.services.project_service import ProjectService
from app.testing.evidence_manager import EvidenceManager
from app.testing.httpx_runner import HttpxApiRunner
from app.testing.playwright_runner import PlaywrightWebRunner
from app.testing.pytest_runner import PytestRunner


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
        executor_name = (executor_override or "").lower().strip()
        if not executor_name:
            if test_case.test_type == TestType.WEB:
                executor_name = "playwright"
            elif test_case.test_type == TestType.API:
                executor_name = "httpx"
            else:
                executor_name = "pytest"

        if executor_name == "playwright":
            runner = PlaywrightWebRunner(settings, evidence_manager)
        elif executor_name == "httpx":
            runner = HttpxApiRunner(settings, evidence_manager)
        elif executor_name == "pytest":
            runner = PytestRunner(settings, evidence_manager)
        else:
            raise ResourceConflictError(f"Unsupported executor: '{executor_name}'. Must be playwright, httpx, or pytest.")

        # Create immutable execution record in QUEUED state
        now = datetime.now(timezone.utc)
        execution = TestExecution(
            id=uuid4(),
            test_case_id=test_case.id,
            status=ExecutionStatus.QUEUED,
            executor=executor_name,
            run_reference=f"run-{uuid4().hex[:12]}",
            summary={},
            error_message=None,
            started_at=now,
            completed_at=None,
            created_at=now,
        )
        self.db.add(execution)
        commit_or_rollback(self.db)

        # Transition to RUNNING state
        execution.status = ExecutionStatus.RUNNING
        commit_or_rollback(self.db)

        try:
            outcome = runner.execute(test_case, execution.id)
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

            commit_or_rollback(self.db)

        except Exception as exc:
            execution.status = ExecutionStatus.ERROR
            execution.completed_at = datetime.now(timezone.utc)
            execution.error_message = str(exc)
            commit_or_rollback(self.db)

        return execution
