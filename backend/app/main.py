from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.analysis_exceptions import AnalysisConfigurationError, AnalysisInputError, AnalysisProviderError, InvalidAnalysisOutputError
from app.core.config import get_settings
from app.core.errors import analysis_configuration_exception_handler, analysis_input_exception_handler, analysis_provider_exception_handler, conflict_exception_handler, not_found_exception_handler, unhandled_exception_handler
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError


def create_application() -> FastAPI:
    """Create the configured FastAPI application."""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Foundation API for the TestMate AI testing platform.",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.add_exception_handler(ResourceNotFoundError, not_found_exception_handler)
    application.add_exception_handler(ResourceConflictError, conflict_exception_handler)
    application.add_exception_handler(AnalysisConfigurationError, analysis_configuration_exception_handler)
    application.add_exception_handler(AnalysisInputError, analysis_input_exception_handler)
    application.add_exception_handler(AnalysisProviderError, analysis_provider_exception_handler)
    application.add_exception_handler(InvalidAnalysisOutputError, analysis_provider_exception_handler)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_application()
