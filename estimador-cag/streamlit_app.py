import json
import os
import textwrap
import time
from collections.abc import Iterator

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ESTIMATE_STREAM_URL = f"{API_BASE_URL}/api/v1/estimate/stream"
CONTEXT_URL = f"{API_BASE_URL}/api/v1/context"
TIMEOUT_SECONDS = 120


def stream_estimation(transcription: str, meta: dict) -> Iterator[str]:
    """Yield the estimation chunk by chunk and store the final metadata in `meta`."""
    with requests.post(
        ESTIMATE_STREAM_URL,
        json={"transcription": transcription},
        stream=True,
        timeout=TIMEOUT_SECONDS,
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            event = json.loads(line)
            if event["type"] == "delta":
                yield event["text"]
            elif event["type"] == "done":
                meta.update(event)
            elif event["type"] == "error":
                raise RuntimeError(event["detail"])


@st.cache_data(show_spinner=False)
def fetch_context() -> dict:
    """Fetch the static context (system prompt + CAG examples) from the API."""
    response = requests.get(CONTEXT_URL, timeout=10)
    response.raise_for_status()
    return response.json()


def format_meta(meta: dict) -> str:
    return f"{meta['provider']} · {meta['model']} · {meta['total_tokens']} tokens"


def render_metrics(metrics: dict | None) -> None:
    """Draw the metrics of the last call inside the sidebar."""
    if not metrics:
        st.caption("Todavía no hay llamadas en esta sesión.")
        return

    st.caption("Modelo utilizado")
    st.code(metrics["model"], language=None)

    left, right = st.columns(2)
    left.metric("Tokens entrada", f"{metrics['input_tokens']:,}")
    right.metric("Tokens salida", f"{metrics['output_tokens']:,}")

    left, right = st.columns(2)
    left.metric("Tokens totales", f"{metrics['total_tokens']:,}")
    right.metric("Tiempo respuesta", f"{metrics['elapsed_seconds']:.1f} s")


st.set_page_config(page_title="Estimador CAG", page_icon="📊", layout="wide")
st.title("📊 Estimador CAG")
st.caption(f"API: {ESTIMATE_STREAM_URL}")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = None

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
        st.text_area(
            "System prompt activo",
            value=context["system_prompt"],
            height=180,
            disabled=True,  # solo lectura
            label_visibility="collapsed",
        )

        st.subheader(f"Contexto estático ({len(context['examples'])} ejemplos)")
        st.caption(
            "Estimaciones de ejemplo inyectadas en cada llamada como pares "
            "usuario/asistente (CAG)."
        )
        for index, example in enumerate(context["examples"], start=1):
            with st.expander(f"Ejemplo {index}"):
                st.markdown("**Resumen de reunión**")
                st.markdown(example["meeting_summary"])
                st.markdown("**Estimación**")
                st.markdown(textwrap.dedent(example["estimation"]).strip())

    st.divider()
    st.subheader("📈 Última llamada")
    # Placeholder para poder refrescar las métricas tras el streaming
    metrics_slot = st.empty()
    with metrics_slot.container():
        render_metrics(st.session_state.last_metrics)

# 1. Se dibuja el historial existente
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if meta := message.get("meta"):
            st.caption(meta)

# 2. Captura un nuevo mensaje del usuario
if prompt := st.chat_input("Pega aquí la transcripción de la reunión..."):
    # Muestra el mensaje en pantalla
    with st.chat_message("user"):
        st.markdown(prompt)

    # Lo guarda en el historial
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 3. Llama al router y va escribiendo la estimación token a token
    with st.chat_message("assistant"):
        meta: dict = {}
        started_at = time.perf_counter()
        try:
            estimation = st.write_stream(stream_estimation(prompt, meta))
        except requests.HTTPError as exc:
            detail = exc.response.json().get("detail", exc.response.text)
            error = f"❌ Error {exc.response.status_code}: {detail}"
            st.error(error)
            st.session_state.messages.append({"role": "assistant", "content": error})
        except requests.RequestException as exc:
            error = f"❌ No se pudo conectar con la API ({ESTIMATE_STREAM_URL}): {exc}"
            st.error(error)
            st.session_state.messages.append({"role": "assistant", "content": error})
        except RuntimeError as exc:
            error = f"❌ El modelo falló durante la generación: {exc}"
            st.error(error)
            st.session_state.messages.append({"role": "assistant", "content": error})
        else:
            caption = format_meta(meta) if meta else None
            if caption:
                st.caption(caption)
            st.session_state.messages.append(
                {"role": "assistant", "content": estimation, "meta": caption}
            )

            if meta:
                st.session_state.last_metrics = {
                    "model": meta["model"],
                    "input_tokens": meta["input_tokens"],
                    "output_tokens": meta["output_tokens"],
                    "total_tokens": meta["total_tokens"],
                    "elapsed_seconds": time.perf_counter() - started_at,
                }
                # Repinta el panel lateral, que ya se había dibujado antes
                with metrics_slot.container():
                    render_metrics(st.session_state.last_metrics)
