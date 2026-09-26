import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.prompts.loader import PromptNotFoundError
from app.schemas import ContextResponse, EstimationRequest, EstimationResponse
from app.services.llm_service import (
    LLMServiceError,
    generate_estimation,
    get_context_info,
    stream_estimation,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["estimations"])


@router.get("/context", response_model=ContextResponse)
async def context() -> ContextResponse:
    """Expose the rendered system prompt (few-shot examples included) and its version."""
    return ContextResponse(**get_context_info())


@router.post("/estimate", response_model=EstimationResponse)
async def estimate(request: EstimationRequest) -> EstimationResponse:
    """Receive a structured project brief and return a software project estimation."""
    try:
        result = generate_estimation(request)
    except (LLMServiceError, PromptNotFoundError) as exc:
        log.error("estimation_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@router.post("/estimate/stream")
def estimate_stream(request: EstimationRequest) -> StreamingResponse:
    """Stream the estimation token by token as NDJSON lines."""
    try:
        lines = stream_estimation(request)
    except (LLMServiceError, PromptNotFoundError) as exc:
        log.error("estimation_stream_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return StreamingResponse(
        lines,
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )