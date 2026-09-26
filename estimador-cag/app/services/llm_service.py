"""Wrapper de proveedor sobre LiteLLM: un solo cliente para Anthropic y OpenAI."""

import json
from collections.abc import Iterator
from dataclasses import dataclass

import litellm
import structlog
from litellm import completion

from app.config import Settings, get_settings
from app.prompts.loader import DEFAULT_VERSION, render_estimation_prompt
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
)

log = structlog.get_logger()
MAX_TOKENS = 2000

# Un parámetro que el proveedor de destino no soporte se descarta en vez de
# reventar la llamada: es lo que permite usar el mismo código para los dos.
litellm.drop_params = True
litellm.telemetry = False
litellm.suppress_debug_info = True  # los banners rojos del SDK ensucian el log

# Proveedores soportados y el campo de Settings del que sale su API key.
PROVIDER_API_KEY_SETTINGS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# Encargo ficticio que solo sirve para previsualizar el prompt en GET /context:
# el system prompt depende de output_format y detail_level, así que hay que fijar
# una configuración de referencia para poder renderizarlo fuera de una llamada real.
CONTEXT_REFERENCE_REQUEST = EstimationRequest(
    description=(
        "Reference brief used only to preview the prompt that the model receives."
    ),
    project_type=ProjectType.WEB_SAAS,
    detail_level=DetailLevel.MEDIUM,
    output_format=OutputFormat.PHASES_TABLE,
)


class LLMServiceError(Exception):
    """Raised when the LLM provider is unsupported or every provider fails."""
    pass


@dataclass(frozen=True)
class Provider:
    """Un proveedor concreto listo para llamar: quién, con qué modelo y qué key."""

    name: str
    model: str
    api_key: str

    @property
    def litellm_model(self) -> str:
        """Identificador que espera LiteLLM, p. ej. `anthropic/claude-haiku-4-5`."""
        return f"{self.name}/{self.model}"


def build_provider_chain(settings: Settings) -> list[Provider]:
    """Devolver [primario, respaldo], saltando los que no tengan API key.

    El orden es el de la configuración: `LLM_PROVIDER` primero y
    `LLM_FALLBACK_PROVIDER` después. Cambiar de proveedor es cambiar el `.env`.
    """
    configured = [
        (settings.LLM_PROVIDER, settings.LLM_MODEL),
        (settings.LLM_FALLBACK_PROVIDER, settings.LLM_FALLBACK_MODEL),
    ]

    chain: list[Provider] = []
    for name, model in configured:
        if not name or not model:
            continue

        name = name.lower()
        if name not in PROVIDER_API_KEY_SETTINGS:
            raise LLMServiceError(f"Unsupported LLM provider: {name}")

        api_key = getattr(settings, PROVIDER_API_KEY_SETTINGS[name])
        if not api_key or api_key == "NONE":
            log.warning("provider_skipped_without_api_key", provider=name, model=model)
            continue

        provider = Provider(name=name, model=model, api_key=api_key)
        if provider not in chain:
            chain.append(provider)

    if not chain:
        raise LLMServiceError(
            "No usable LLM provider: set an API key for LLM_PROVIDER "
            f"({settings.LLM_PROVIDER}) or for LLM_FALLBACK_PROVIDER "
            f"({settings.LLM_FALLBACK_PROVIDER})."
        )

    return chain


def build_messages(system: str, user: str) -> list[dict]:
    """Los dos turnos, separados. LiteLLM traduce `system` al formato de cada API."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def get_context_info() -> dict:
    """Return the prompt the model receives, rendered for a reference request."""
    settings = get_settings()
    system, _ = render_estimation_prompt(CONTEXT_REFERENCE_REQUEST)
    primary = build_provider_chain(settings)[0]

    return {
        "system_prompt": system,
        "provider": primary.name,
        "model": primary.model,
        "prompt_version": DEFAULT_VERSION,
    }


def generate_estimation(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> EstimationResponse:
    """Generate a software project estimation from a structured request."""
    settings = get_settings()
    system, user = render_estimation_prompt(request, version)
    chain = build_provider_chain(settings)

    text = call_llm(system, user, chain, request, version)
    return EstimationResponse(text=text, prompt_version=version)


def stream_estimation(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> Iterator[str]:
    """Stream an estimation as NDJSON lines: many `delta` events, then one `done`."""
    settings = get_settings()
    # La cadena se construye aquí, fuera del generador, para que una configuración
    # inválida devuelva un 500 antes de empezar a emitir la respuesta.
    chain = build_provider_chain(settings)
    system, user = render_estimation_prompt(request, version)

    return stream_llm(system, user, chain, request, version)


def call_llm(
    system: str,
    user: str,
    chain: list[Provider],
    request: EstimationRequest,
    version: str,
) -> str:
    """Probar cada proveedor de la cadena en orden y devolver la primera respuesta."""
    failures: list[str] = []

    for provider in chain:
        try:
            response = completion(
                model=provider.litellm_model,
                messages=build_messages(system, user),
                max_tokens=MAX_TOKENS,
                api_key=provider.api_key,
            )
        except Exception as exc:
            log.warning(
                "llm_provider_failed",
                provider=provider.name,
                model=provider.model,
                error=str(exc),
            )
            failures.append(f"{provider.litellm_model}: {exc}")
            continue

        log.info(
            "llm_response",
            provider=provider.name,
            model=response.model,
            fell_back=provider is not chain[0],
            prompt_version=version,
            project_type=request.project_type.value,
            detail_level=request.detail_level.value,
            output_format=request.output_format.value,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )

        return response.choices[0].message.content

    raise LLMServiceError("Every LLM provider failed -> " + " | ".join(failures))


def stream_llm(
    system: str,
    user: str,
    chain: list[Provider],
    request: EstimationRequest,
    version: str,
) -> Iterator[str]:
    """Igual que `call_llm`, pero emitiendo líneas NDJSON.

    El fallback solo puede ocurrir antes del primer trozo: una vez que el
    proveedor empieza a escribir ya no se puede cambiar de caballo, así que un
    fallo posterior viaja como evento `error`.
    """
    failures: list[str] = []

    for provider in chain:
        try:
            stream = completion(
                model=provider.litellm_model,
                messages=build_messages(system, user),
                max_tokens=MAX_TOKENS,
                api_key=provider.api_key,
                stream=True,
                stream_options={"include_usage": True},
            )
            chunks = iter(stream)
            first_chunk = next(chunks)
        except StopIteration:
            failures.append(f"{provider.litellm_model}: empty stream")
            continue
        except Exception as exc:
            log.warning(
                "llm_provider_failed",
                provider=provider.name,
                model=provider.model,
                error=str(exc),
            )
            failures.append(f"{provider.litellm_model}: {exc}")
            continue

        yield from drain_stream(
            chunks, first_chunk, provider, chain, request, version
        )
        return

    log.error("llm_all_providers_failed", failures=failures)
    yield json.dumps(
        {"type": "error", "detail": "Every LLM provider failed -> " + " | ".join(failures)}
    ) + "\n"


def drain_stream(
    chunks: Iterator,
    first_chunk,
    provider: Provider,
    chain: list[Provider],
    request: EstimationRequest,
    version: str,
) -> Iterator[str]:
    """Convertir los trozos de LiteLLM en líneas NDJSON `delta` y un `done` final."""
    usage = None
    model = provider.model

    try:
        for chunk in (first_chunk, *chunks):
            # El trozo final de uso llega con `choices` vacío.
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if getattr(chunk, "model", None):
                model = chunk.model
            if not chunk.choices:
                continue

            text = chunk.choices[0].delta.content
            if text:
                yield json.dumps({"type": "delta", "text": text}) + "\n"
    except Exception as exc:
        # La respuesta ya había empezado, así que el error viaja como evento.
        log.error("llm_stream_error", provider=provider.name, error=str(exc))
        yield json.dumps({"type": "error", "detail": str(exc)}) + "\n"
        return

    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0

    log.info(
        "llm_streamed_response",
        provider=provider.name,
        model=model,
        fell_back=provider is not chain[0],
        prompt_version=version,
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )

    yield json.dumps(
        {
            "type": "done",
            "model": model,
            "provider": provider.name,
            "prompt_version": version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    ) + "\n"
