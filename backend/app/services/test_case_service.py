from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate
from app.services.database import commit_and_refresh, commit_or_rollback
from app.services.project_service import ProjectService


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

    def list_test_cases(
        self, project_id: UUID, limit: int, offset: int, requirement_id: UUID | None, status: str | None
    ) -> tuple[list[TestCase], int]:
        ProjectService(self.db).get_project(project_id)
        statement = select(TestCase).join(Requirement).where(Requirement.project_id == project_id)
        if requirement_id is not None:
            statement = statement.where(TestCase.requirement_id == requirement_id)
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
        return test_case

    def delete_test_case(self, project_id: UUID, test_case_id: UUID) -> None:
        test_case = self.get_test_case(project_id, test_case_id)
        has_executions = self.db.scalar(select(TestExecution.id).where(TestExecution.test_case_id == test_case.id).limit(1))
        if has_executions is not None:
            raise ResourceConflictError("Executed test cases cannot be deleted to preserve execution history.")
        self.db.delete(test_case)
        commit_or_rollback(self.db)
