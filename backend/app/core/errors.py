from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_409_CONFLICT, HTTP_500_INTERNAL_SERVER_ERROR

from app.core.analysis_exceptions import (
    AnalysisConfigurationError,
    AnalysisInputError,
    AnalysisProviderError,
    InvalidAnalysisOutputError,
)
from app.core.config import get_settings
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


async def analysis_configuration_exception_handler(_: Request, __: AnalysisConfigurationError) -> JSONResponse:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        detail = "Requirement analysis is not configured. Set GEMINI_API_KEY and try again."
    elif settings.ai_provider == "openai":
        detail = "Requirement analysis is not configured. Set OPENAI_API_KEY and try again."
    else:
        detail = f"Requirement analysis is not configured for provider '{settings.ai_provider}'."
    return JSONResponse(status_code=503, content={"detail": detail})


async def analysis_input_exception_handler(_: Request, exc: AnalysisInputError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def analysis_provider_exception_handler(_: Request, __: AnalysisProviderError | InvalidAnalysisOutputError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "Requirement analysis is temporarily unavailable. Please try again."})
