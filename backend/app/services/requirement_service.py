from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.schemas.requirement import RequirementCreate, RequirementUpdate
from app.services.database import commit_and_refresh, commit_or_rollback
from app.services.project_service import ProjectService


class RequirementService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_requirement(self, project_id: UUID, requirement_id: UUID) -> Requirement:
        requirement = self.db.scalar(
            select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id)
        )
        if requirement is None:
            raise ResourceNotFoundError("Requirement not found for this project.")
        return requirement

    def list_requirements(
        self, project_id: UUID, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[Requirement], int]:
        ProjectService(self.db).get_project(project_id)
        statement = select(Requirement).where(Requirement.project_id == project_id)
        if status is not None:
            statement = statement.where(Requirement.status == status)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.db.scalars(statement.order_by(Requirement.created_at.desc()).offset(offset).limit(limit)))
        return items, total

    def create_requirement(self, project_id: UUID, payload: RequirementCreate) -> Requirement:
        ProjectService(self.db).get_project(project_id)
        requirement = Requirement(project_id=project_id, **payload.model_dump())
        self.db.add(requirement)
        commit_and_refresh(self.db, requirement)
        return requirement

    def update_requirement(self, project_id: UUID, requirement_id: UUID, payload: RequirementUpdate) -> Requirement:
        requirement = self.get_requirement(project_id, requirement_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(requirement, field, value)
        commit_and_refresh(self.db, requirement)
        return requirement

    def delete_requirement(self, project_id: UUID, requirement_id: UUID) -> None:
        requirement = self.get_requirement(project_id, requirement_id)
        has_cases = self.db.scalar(select(TestCase.id).where(TestCase.requirement_id == requirement.id).limit(1))
        if has_cases is not None:
            raise ResourceConflictError("Requirements with test cases cannot be deleted to preserve traceability.")
        self.db.delete(requirement)
        commit_or_rollback(self.db)
