import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.enums import ReviewStatus, TestCaseStatus
from app.models.knowledge_indexing_job import IndexingJobAction
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.knowledge import KnowledgeRecordType
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate
from app.services.database import commit_and_refresh, commit_or_rollback
from app.services.knowledge_indexing_job_service import KnowledgeIndexingJobService
from app.services.project_service import ProjectService
from app.services.requirement_service import RequirementService

logger = logging.getLogger(__name__)


class TestCaseService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_test_case(self, project_id: UUID, test_case_id: UUID) -> TestCase:
        test_case = self.db.scalar(
            select(TestCase)
            .join(Requirement)
            .where(TestCase.id == test_case_id, Requirement.project_id == project_id)
        )
        if test_case is None:
            raise ResourceNotFoundError("Test case not found for this project.")
        return test_case

    def get_requirement_test_case(
        self, project_id: UUID, requirement_id: UUID, test_case_id: UUID
    ) -> TestCase:
        test_case = self.db.scalar(
            select(TestCase)
            .join(Requirement)
            .where(
                TestCase.id == test_case_id,
                TestCase.requirement_id == requirement_id,
                Requirement.project_id == project_id,
            )
        )
        if test_case is None:
            raise ResourceNotFoundError("Test case not found for this requirement and project.")
        return test_case

    def list_test_cases(
        self,
        project_id: UUID,
        limit: int,
        offset: int,
        requirement_id: UUID | None,
        status: str | None,
        review_status: str | None = None,
    ) -> tuple[list[TestCase], int]:
        ProjectService(self.db).get_project(project_id)
        statement = select(TestCase).join(Requirement).where(Requirement.project_id == project_id)
        if requirement_id is not None:
            statement = statement.where(TestCase.requirement_id == requirement_id)
        if status is not None:
            statement = statement.where(TestCase.status == status)
        if review_status is not None:
            statement = statement.where(TestCase.review_status == review_status)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(TestCase.created_at.desc()).offset(offset).limit(limit)))
        return items, total

    def list_requirement_test_cases(
        self,
        project_id: UUID,
        requirement_id: UUID,
        limit: int,
        offset: int,
        review_status: str | None = None,
        status: str | None = None,
    ) -> tuple[list[TestCase], int]:
        RequirementService(self.db).get_requirement(project_id, requirement_id)
        statement = (
            select(TestCase)
            .join(Requirement)
            .where(Requirement.project_id == project_id, TestCase.requirement_id == requirement_id)
        )
        if review_status is not None:
            statement = statement.where(TestCase.review_status == review_status)
        if status is not None:
            statement = statement.where(TestCase.status == status)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(TestCase.created_at.desc()).offset(offset).limit(limit)))
        return items, total

    def create_test_case(self, project_id: UUID, payload: TestCaseCreate) -> TestCase:
        requirement = self.db.scalar(
            select(Requirement).where(Requirement.id == payload.requirement_id, Requirement.project_id == project_id)
        )
        if requirement is None:
            raise ResourceNotFoundError("Requirement not found for this project.")
        values = payload.model_dump()
        values["steps"] = [step.model_dump() for step in payload.steps]
        test_case = TestCase(**values)
        self.db.add(test_case)
        commit_and_refresh(self.db, test_case)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case.id, IndexingJobAction.UPSERT)
        return test_case

    def update_test_case(self, project_id: UUID, test_case_id: UUID, payload: TestCaseUpdate) -> TestCase:
        test_case = self.get_test_case(project_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases are immutable to preserve reproducible history.")
        values = payload.model_dump(exclude_unset=True)
        if "steps" in values and values["steps"] is not None:
            values["steps"] = [step.model_dump() for step in payload.steps or []]
        for field, value in values.items():
            setattr(test_case, field, value)
        if values:
            test_case.version += 1
        commit_and_refresh(self.db, test_case)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case.id, IndexingJobAction.UPSERT)
        return test_case

    def update_requirement_test_case(
        self, project_id: UUID, requirement_id: UUID, test_case_id: UUID, payload: TestCaseUpdate
    ) -> TestCase:
        test_case = self.get_requirement_test_case(project_id, requirement_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases are immutable to preserve reproducible history.")
        values = payload.model_dump(exclude_unset=True)
        if "steps" in values and values["steps"] is not None:
            values["steps"] = [step.model_dump() for step in payload.steps or []]
        for field, value in values.items():
            setattr(test_case, field, value)
        if values:
            test_case.version += 1
        commit_and_refresh(self.db, test_case)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case.id, IndexingJobAction.UPSERT)
        return test_case

    def approve_requirement_test_case(
        self, project_id: UUID, requirement_id: UUID, test_case_id: UUID
    ) -> TestCase:
        test_case = self.get_requirement_test_case(project_id, requirement_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases cannot be modified.")
        if test_case.review_status == ReviewStatus.APPROVED:
            raise ResourceConflictError("Test case has already been approved.")
        if test_case.review_status == ReviewStatus.REJECTED:
            raise ResourceConflictError("Cannot approve an already rejected test case.")

        test_case.review_status = ReviewStatus.APPROVED
        test_case.status = TestCaseStatus.APPROVED
        test_case.version += 1
        commit_and_refresh(self.db, test_case)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case.id, IndexingJobAction.UPSERT)
        return test_case

    def reject_requirement_test_case(
        self, project_id: UUID, requirement_id: UUID, test_case_id: UUID
    ) -> TestCase:
        test_case = self.get_requirement_test_case(project_id, requirement_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases cannot be modified.")
        if test_case.review_status == ReviewStatus.REJECTED:
            raise ResourceConflictError("Test case has already been rejected.")
        if test_case.review_status == ReviewStatus.APPROVED:
            raise ResourceConflictError("Cannot reject an already approved test case.")

        test_case.review_status = ReviewStatus.REJECTED
        test_case.status = TestCaseStatus.RETIRED
        test_case.version += 1
        commit_and_refresh(self.db, test_case)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case.id, IndexingJobAction.DELETE)
        return test_case

    def delete_test_case(self, project_id: UUID, test_case_id: UUID) -> None:
        test_case = self.get_test_case(project_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases cannot be deleted to preserve execution history.")
        self.db.delete(test_case)
        commit_or_rollback(self.db)
        self._trigger_auto_indexing(project_id, KnowledgeRecordType.TEST_CASE, test_case_id, IndexingJobAction.DELETE)

    def _trigger_auto_indexing(
        self,
        project_id: UUID,
        record_type: KnowledgeRecordType | str,
        source_id: UUID,
        action: IndexingJobAction | str = IndexingJobAction.UPSERT,
    ) -> None:
        """Enqueue durable outbox indexing job and attempt non-blocking immediate processing."""
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
