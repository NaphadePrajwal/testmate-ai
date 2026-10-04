from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError


def commit_and_refresh(db: Session, instance: object) -> None:
    """Commit a mutation and translate integrity failures into a stable domain error."""

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ResourceConflictError("The request conflicts with an existing or related resource.") from exc
    db.refresh(instance)


def commit_or_rollback(db: Session) -> None:
    """Commit a mutation while translating database constraint races consistently."""

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ResourceConflictError("The request conflicts with an existing or related resource.") from exc
