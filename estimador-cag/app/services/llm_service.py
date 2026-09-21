import json
from collections.abc import Iterator

from anthropic import Anthropic, APIError

from app.config import EstimationResponse, Settings, get_settings

import structlog

from app.context.examples import ESTIMATION_EXAMPLES

log = structlog.get_logger()
MAX_TOKENS = 2000

SYSTEM_PROMPT = (
    "You are an expert software estimator that generates estimates based on previous "
    "examples and the transcript of a new meeting. "
    "Provide detailed tasks, "
    "estimated hours, team composition, and total duration."
)

class LLMServiceError(Exception):
    """Raised when the LLM provider is unsupported or the call fails."""
    pass

def get_context_info() -> dict:
    """Return the static context (system prompt + CAG examples) used on every call."""
    settings = get_settings()

    return {
        "system_prompt": SYSTEM_PROMPT,
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "examples": ESTIMATION_EXAMPLES,
    }


def build_messages(transcription: str) -> list[dict]:
    messages = []

    for example in ESTIMATION_EXAMPLES:
        messages.append({"role": "user", "content": example["meeting_summary"]})
        messages.append({"role": "assistant", "content": example["estimation"]})

    messages.append({"role": "user", "content": transcription})
    return messages    

def generate_estimation(transcription: str) -> EstimationResponse:
    """Generate a software project estimation based on a meeting transcription."""
    settings = get_settings()

    if settings.LLM_PROVIDER.lower() == "anthropic":
        response = call_anthropic(SYSTEM_PROMPT, transcription, settings)
        return EstimationResponse(**response)
    else:
        raise LLMServiceError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")


def stream_estimation(transcription: str) -> Iterator[str]:
    """Stream an estimation as NDJSON lines: many `delta` events, then one `done`."""
    settings = get_settings()

    if settings.LLM_PROVIDER.lower() != "anthropic":
        raise LLMServiceError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")

    return stream_anthropic(SYSTEM_PROMPT, transcription, settings)

def call_anthropic(system: str, user_message: str, settings: Settings) -> dict:
    """Send a message request to the Anthropic API."""
    
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = build_messages(user_message)

    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
    )

    log.info(
        "Response from Anthropic API",
        provider="anthropic",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    return {
        "estimation": response.content[0].text,
        "model": response.model,
        "provider": "anthropic",
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens
    }


def stream_anthropic(system: str, user_message: str, settings: Settings) -> Iterator[str]:
    """Stream a message request to the Anthropic API as NDJSON lines."""

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = build_messages(user_message)

    try:
        with client.messages.stream(
            model=settings.LLM_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield json.dumps({"type": "delta", "text": text}) + "\n"

            final_message = stream.get_final_message()
    except APIError as exc:
        # The response already started, so the error travels as a stream event.
        log.error("anthropic_stream_error", error=str(exc))
        yield json.dumps({"type": "error", "detail": str(exc)}) + "\n"
        return

    log.info(
        "Streamed response from Anthropic API",
        provider="anthropic",
        input_tokens=final_message.usage.input_tokens,
        output_tokens=final_message.usage.output_tokens,
    )

    yield json.dumps(
        {
            "type": "done",
            "model": final_message.model,
            "provider": "anthropic",
            "input_tokens": final_message.usage.input_tokens,
            "output_tokens": final_message.usage.output_tokens,
            "total_tokens": (
                final_message.usage.input_tokens + final_message.usage.output_tokens
            ),
        }
    ) + "\n"

