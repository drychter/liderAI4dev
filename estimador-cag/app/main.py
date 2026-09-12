import logging

import structlog
from fastapi import FastAPI

from app.config import ApiResponse, get_settings
from app.routers import estimations

settings = get_settings()

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
