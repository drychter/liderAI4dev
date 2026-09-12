from anthropic import Anthropic

from app.config import EstimationResponse, Settings, get_settings

import structlog

from app.context.examples import ESTIMATION_EXAMPLES

log = structlog.get_logger()
MAX_TOKENS = 2000

class LLMServiceError(Exception):
    """Raised when the LLM provider is unsupported or the call fails."""
    pass

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
        system_prompt = (
            "You are an expert software estimator that generates estimates based on previous "
            "examples and the transcript of a new meeting. "
            "Provide detailed tasks, "
            "estimated hours, team composition, and total duration."
        )
        response = call_anthropic(system_prompt, transcription, settings)
        return EstimationResponse(**response)
    else:
        raise LLMServiceError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")

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

