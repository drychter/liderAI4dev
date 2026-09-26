import logging

import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.routers import estimations
from app.schemas import ApiResponse

settings = get_settings()

def configure_logging() -> None:
    """Set up structlog: JSON in production, human-readable in development."""
    settings = get_settings()

    if settings.APP_ENV == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

logging.basicConfig(level=settings.LOG_LEVEL)
log = structlog.get_logger()

app = FastAPI(
    title="Estimador CAG",
    description="Generates software project estimations from meeting transcriptions.",
    version="0.1.0",
)

app.include_router(estimations.router)


@app.get("/health", response_model=ApiResponse)
async def health() -> ApiResponse:
    """Report that the service is up."""
    return ApiResponse(message="ok", status_code=200)
