"""Render the versioned Jinja2 prompt templates that live next to this module."""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from app.schemas import EstimationRequest

PROMPTS_DIR = Path(__file__).parent
DEFAULT_VERSION = "v1"


class PromptNotFoundError(Exception):
    """Raised when the requested prompt version has no templates on disk."""


@lru_cache
def get_environment() -> Environment:
    """Build the Jinja2 environment rooted at `app/prompts/`.

    `StrictUndefined` makes a missing variable fail loudly at render time instead
    of silently producing a prompt with a hole in it.
    """
    return Environment(
        loader=FileSystemLoader(PROMPTS_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_estimation_prompt(
    request: EstimationRequest, version: str = DEFAULT_VERSION
) -> tuple[str, str]:
    """Render `(system, user)` for an estimation request.

    Changing `version` is enough to switch to another prompt generation: the
    templates live in `app/prompts/estimation/<version>/` and nothing else in the
    codebase needs to know which one is active.
    """
    environment = get_environment()
    context = {
        "version": version,
        "description": request.description,
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
    }

    try:
        system = environment.get_template(f"estimation/{version}/system.j2")
        user = environment.get_template(f"estimation/{version}/user.j2")
    except TemplateNotFound as exc:
        raise PromptNotFoundError(
            f"No estimation prompt templates for version '{version}': {exc.name}"
        ) from exc

    return system.render(context).strip(), user.render(context).strip()
