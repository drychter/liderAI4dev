"""Tests del template de estimación v1: renderizado puro, sin llamar a ningún LLM."""

import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

DESCRIPTION = (
    "A bakery chain wants a web shop with click-and-collect orders, "
    "stock synced across four stores and a weekly sales report."
)

# Frases literales de system.j2 que identifican cada variante.
PHASES_TABLE_MARKER = "Phase | Deliverables | Hours | Role"
DETAILED_ASSUMPTIONS_MARKER = "explicit sections for assumptions"


def render(
    output_format: OutputFormat = OutputFormat.PHASES_TABLE,
    detail_level: DetailLevel = DetailLevel.MEDIUM,
) -> tuple[str, str]:
    request = EstimationRequest(
        description=DESCRIPTION,
        project_type=ProjectType.WEB_SAAS,
        detail_level=detail_level,
        output_format=output_format,
    )
    return render_estimation_prompt(request, version="v1")


def test_user_prompt_includes_description_in_its_section():
    _, user = render()

    section = user.split("Description:", 1)[1]
    assert DESCRIPTION in section


@pytest.mark.parametrize(
    ("output_format", "expected"),
    [(OutputFormat.PHASES_TABLE, True), (OutputFormat.NARRATIVE, False)],
)
def test_system_prompt_mentions_table_columns_only_for_phases_table(output_format, expected):
    system, _ = render(output_format=output_format)

    assert (PHASES_TABLE_MARKER in system) is expected


@pytest.mark.parametrize(
    ("detail_level", "expected"),
    [(DetailLevel.DETAILED, True), (DetailLevel.SUMMARY, False)],
)
def test_system_prompt_asks_for_assumptions_section_only_when_detailed(detail_level, expected):
    system, _ = render(detail_level=detail_level)

    assert (DETAILED_ASSUMPTIONS_MARKER in system) is expected
