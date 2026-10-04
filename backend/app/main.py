from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import unhandled_exception_handler


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
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_application()
