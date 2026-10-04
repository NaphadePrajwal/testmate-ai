from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.project import ProjectListResponse
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("", response_model=ProjectListResponse, summary="List testing projects")
def list_projects(db: Session = Depends(get_db)) -> ProjectListResponse:
    try:
        return ProjectListResponse(items=ProjectService(db).list_projects())
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Project data is temporarily unavailable.") from exc
