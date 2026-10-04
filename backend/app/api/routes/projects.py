from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import Pagination, pagination_params
from app.db.session import get_db
from app.schemas.project import ProjectCreate, ProjectListResponse, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("", response_model=ProjectListResponse, summary="List testing projects")
def list_projects(
    page: Pagination = Depends(pagination_params), db: Session = Depends(get_db)
) -> ProjectListResponse:
    try:
        items, total = ProjectService(db).list_projects(page.limit, page.offset)
        return ProjectListResponse(items=items, total=total, limit=page.limit, offset=page.offset)
    except SQLAlchemyError as exc:
        # Preserve the Phase 0 contract for an unavailable project data store.
        raise HTTPException(status_code=503, detail="Project data is temporarily unavailable.") from exc


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED, summary="Create a project")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).create_project(payload)


@router.get("/{project_id}", response_model=ProjectRead, summary="Get a project")
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Partially update a project")
def update_project(project_id: UUID, payload: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectService(db).update_project(project_id, payload)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an empty project")
def delete_project(project_id: UUID, db: Session = Depends(get_db)) -> Response:
    ProjectService(db).delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
