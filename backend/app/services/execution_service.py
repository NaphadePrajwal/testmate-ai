from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.models.defect import Defect
from app.models.execution_evidence import ExecutionEvidence
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.services.project_service import ProjectService


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
