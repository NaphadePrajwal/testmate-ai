from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.project import Project
from app.models.requirement import Requirement
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.database import commit_and_refresh, commit_or_rollback


class ProjectService:
    """Database operations for the project dashboard resource."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_projects(self, limit: int = 20, offset: int = 0) -> tuple[list[Project], int]:
        total = self.db.scalar(select(func.count()).select_from(Project)) or 0
        items = list(
            self.db.scalars(select(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit))
        )
        return items, total

    def get_project(self, project_id: UUID) -> Project:
        project = self.db.get(Project, project_id)
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        return project

    def create_project(self, payload: ProjectCreate) -> Project:
        project = Project(**payload.model_dump())
        self.db.add(project)
        commit_and_refresh(self.db, project)
        return project

    def update_project(self, project_id: UUID, payload: ProjectUpdate) -> Project:
        project = self.get_project(project_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        commit_and_refresh(self.db, project)
        return project

    def delete_project(self, project_id: UUID) -> None:
        project = self.get_project(project_id)
        has_requirements = self.db.scalar(
            select(Requirement.id).where(Requirement.project_id == project.id).limit(1)
        )
        if has_requirements is not None:
            raise ResourceConflictError(
                "Projects with requirements or execution history cannot be deleted. Preserve the audit trail instead."
            )
        self.db.delete(project)
        commit_or_rollback(self.db)
