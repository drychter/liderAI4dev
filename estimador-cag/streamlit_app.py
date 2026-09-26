import os
import time

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ESTIMATE_URL = f"{API_BASE_URL}/api/v1/estimate"
CONTEXT_URL = f"{API_BASE_URL}/api/v1/context"
TIMEOUT_SECONDS = 120

# Los valores son los de los enums del servicio (app/schemas.py); las claves, la
# etiqueta que ve el usuario. El formulario solo envía valores válidos del contrato.
PROJECT_TYPES = {
    "App móvil": "mobile_app",
    "SaaS web": "web_saas",
    "Herramienta interna": "internal_tool",
    "Pipeline de datos": "data_pipeline",
}

DETAIL_LEVELS = {
    "Resumen": "summary",
    "Medio": "medium",
    "Detallado": "detailed",
}

OUTPUT_FORMATS = {
    "Tabla por fases": "phases_table",
    "Lista de partidas": "line_items",
    "Narrativo": "narrative",
}

DESCRIPTION_MIN_CHARS = 20
DESCRIPTION_MAX_CHARS = 2000


def request_estimation(payload: dict) -> dict:
    """POST /estimate con un EstimationRequest y devolver el EstimationResponse."""
    response = requests.post(ESTIMATE_URL, json=payload, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False)
def fetch_context() -> dict:
    """Fetch the rendered system prompt and its version from the API."""
    response = requests.get(CONTEXT_URL, timeout=10)
    response.raise_for_status()
    return response.json()


def describe_http_error(exc: requests.HTTPError) -> str:
    """Convertir un error HTTP (incluido el 422 de Pydantic) en una línea legible."""
    try:
        detail = exc.response.json()["detail"]
    except (ValueError, KeyError):
        return f"❌ Error {exc.response.status_code}: {exc.response.text}"

    if isinstance(detail, list):
        # 422: FastAPI devuelve una lista de errores de validación de Pydantic.
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in detail
        )

    return f"❌ Error {exc.response.status_code}: {detail}"


def render_last_call(info: dict | None) -> None:
    """Dibujar los datos de la última llamada en el panel lateral."""
    if not info:
        st.caption("Todavía no hay llamadas en esta sesión.")
        return

    st.caption("Versión de prompt")
    st.code(info["prompt_version"], language=None)
    st.metric("Tiempo respuesta", f"{info['elapsed_seconds']:.1f} s")


st.set_page_config(page_title="Estimador CAG", page_icon="📊", layout="wide")
st.title("📊 Estimador CAG")
st.caption(f"API: {ESTIMATE_URL}")

if "estimation" not in st.session_state:
    st.session_state.estimation = None
if "last_call" not in st.session_state:
    st.session_state.last_call = None

# --- Panel lateral: qué información está usando el modelo -------------------
with st.sidebar:
    st.header("🧠 Contexto del modelo")

    try:
        context = fetch_context()
    except requests.RequestException as exc:
        context = None
        st.warning(f"No se pudo cargar el contexto desde la API: {exc}")

    if context:
        st.subheader("System prompt")
        st.caption(
            "Plantilla Jinja2 renderizada, con los ejemplos few-shot (CAG) incluidos. "
            "Se muestra para una configuración de referencia: los bloques que dependen "
            "de nivel de detalle y formato cambian según lo que elijas abajo."
        )
        st.text_area(
            "System prompt activo",
            value=context["system_prompt"],
            height=320,
            disabled=True,  # solo lectura
            label_visibility="collapsed",
        )
        st.caption(f"Versión de prompt: `{context['prompt_version']}`")

    st.divider()
    st.subheader("📈 Última llamada")
    render_last_call(st.session_state.last_call)

# --- Formulario: construye el EstimationRequest -----------------------------
with st.form("estimation_form"):
    description = st.text_area(
        "Descripción del proyecto",
        height=220,
        max_chars=DESCRIPTION_MAX_CHARS,
        placeholder="Describe el proyecto o pega aquí el resumen de la reunión...",
        help=f"Entre {DESCRIPTION_MIN_CHARS} y {DESCRIPTION_MAX_CHARS} caracteres.",
    )

    left, middle, right = st.columns(3)
    project_type_label = left.selectbox("Tipo de proyecto", PROJECT_TYPES)
    detail_level_label = middle.selectbox("Nivel de detalle", DETAIL_LEVELS, index=1)
    output_format_label = right.selectbox("Formato de salida", OUTPUT_FORMATS)

    submitted = st.form_submit_button("Generar estimación", type="primary")

if submitted:
    description = description.strip()

    if len(description) < DESCRIPTION_MIN_CHARS:
        st.error(
            f"La descripción necesita al menos {DESCRIPTION_MIN_CHARS} caracteres "
            f"(tiene {len(description)})."
        )
    else:
        payload = {
            "description": description,
            "project_type": PROJECT_TYPES[project_type_label],
            "detail_level": DETAIL_LEVELS[detail_level_label],
            "output_format": OUTPUT_FORMATS[output_format_label],
        }

        started_at = time.perf_counter()
        try:
            with st.spinner("Generando estimación..."):
                result = request_estimation(payload)
        except requests.HTTPError as exc:
            st.session_state.estimation = None
            st.error(describe_http_error(exc))
        except requests.RequestException as exc:
            st.session_state.estimation = None
            st.error(f"❌ No se pudo conectar con la API ({ESTIMATE_URL}): {exc}")
        else:
            st.session_state.estimation = result
            st.session_state.last_call = {
                "prompt_version": result["prompt_version"],
                "elapsed_seconds": time.perf_counter() - started_at,
            }
            # El panel lateral ya se dibujó, así que se repinta con los datos nuevos.
            st.rerun()

if st.session_state.estimation:
    st.divider()
    st.markdown(st.session_state.estimation["text"])
    st.caption(f"prompt_version: {st.session_state.estimation['prompt_version']}")
