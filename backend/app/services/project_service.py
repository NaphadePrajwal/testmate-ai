from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectService:
    """Database operations for the project dashboard resource."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_projects(self) -> list[Project]:
        return list(self.db.scalars(select(Project).order_by(Project.created_at.desc())))
