from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Return a stable error envelope without exposing implementation details."""

    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred.", "error_type": type(exc).__name__},
    )
