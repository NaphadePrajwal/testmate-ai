from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT, HTTP_500_INTERNAL_SERVER_ERROR

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Return a stable error envelope without exposing implementation details."""

    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )


async def not_found_exception_handler(_: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=HTTP_404_NOT_FOUND, content={"detail": str(exc)})


async def conflict_exception_handler(_: Request, exc: ResourceConflictError) -> JSONResponse:
    return JSONResponse(status_code=HTTP_409_CONFLICT, content={"detail": str(exc)})
