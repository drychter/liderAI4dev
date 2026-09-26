# Estimador CAG

Servicio FastAPI que genera estimaciones de proyectos software a partir de una
descripción, usando ejemplos estáticos inyectados en cada llamada (CAG), más un
cliente Streamlit con formulario.

## Contrato

El contrato vive en `app/schemas.py` y lo comparten servicio y cliente.

### POST /api/v1/estimate

Request (`EstimationRequest`):

```json
{
  "description": "Plataforma SaaS para que agencias inmobiliarias gestionen su cartera de propiedades, registren clientes y envíen una newsletter quincenal destacando inmuebles.",
  "project_type": "web_saas",
  "detail_level": "medium",
  "output_format": "phases_table"
}
```

| Campo | Tipo | Valores |
| --- | --- | --- |
| `description` | str | entre 20 y 2000 caracteres |
| `project_type` | enum | `mobile_app`, `web_saas`, `internal_tool`, `data_pipeline` |
| `detail_level` | enum | `summary`, `medium`, `detailed` |
| `output_format` | enum | `phases_table`, `line_items`, `narrative` |

Response (`EstimationResponse`):

```json
{
  "text": "# Dance Studio Booking Portal – Estimate\n\n| Phase | Deliverables | Hours | Role |\n...",
  "prompt_version": "v1"
}
```

Una descripción demasiado corta o un enum inválido devuelven `422` con el detalle
de validación de Pydantic.

### Otros endpoints

- `POST /api/v1/estimate/stream` — mismo request, respuesta NDJSON (`delta`…, `done`).
- `GET /api/v1/context` — system prompt renderizado (ejemplos CAG incluidos), modelo y `prompt_version`.
- `GET /health`

Las métricas de tokens no forman parte del contrato: se registran en el log del
servicio (`input_tokens`, `output_tokens`, `total_tokens`) y viajan en el evento
`done` del endpoint de streaming.

## Prompts

Los prompts viven en plantillas Jinja2 versionadas, no en constantes de Python:

```
app/prompts/
├── loader.py
└── estimation/
    └── v1/
        ├── system.j2      # rol, instrucciones, condicionales de output_format y detail_level
        ├── user.j2        # envuelve la descripción, condicional de project_type
        └── examples.j2    # ejemplos few-shot (incluido desde system.j2)
```

`render_estimation_prompt(request, version="v1")` devuelve `(system, user)` ya
renderizados. Para probar una generación nueva de prompts basta con copiar la
carpeta a `v2`, editarla y pasar `version="v2"`: el resto del código no cambia.
El `prompt_version` de la respuesta es la versión que se usó para renderizar.

El entorno Jinja2 usa `StrictUndefined`, así que una variable que falte rompe el
render en vez de colarse como hueco vacío en el prompt.

## Proveedores

Las llamadas al modelo pasan por [LiteLLM](https://docs.litellm.ai/), que expone
una interfaz única para todos los proveedores. El wrapper vive en
`app/services/llm_service.py` y es lo único que conoce el SDK.

El proveedor se elige por configuración, con **anthropic por defecto** y un
respaldo opcional que solo se usa si el primario falla:

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` | proveedor primario |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | modelo del primario |
| `LLM_FALLBACK_PROVIDER` | `openai` | respaldo; vacío = sin fallback |
| `LLM_FALLBACK_MODEL` | `gpt-4o-mini` | modelo del respaldo |
| `ANTHROPIC_API_KEY` | — | key de Anthropic |
| `OPENAI_API_KEY` | — | key de OpenAI |

`build_provider_chain()` construye la lista `[primario, respaldo]` y descarta los
proveedores sin API key (deja un `warning` en el log). Cada llamada recorre la
cadena en orden: si el primario devuelve error, se reintenta con el siguiente y
el log lo marca con `fell_back=True`. Si fallan todos, `LLMServiceError`.

En streaming el fallback solo puede ocurrir **antes** del primer trozo: una vez
que el proveedor empieza a escribir ya no se cambia, y un fallo posterior viaja
como evento `error`.

Invertir el orden (OpenAI primario, Anthropic de respaldo) es solo editar el
`.env`; no hay que tocar código.

## Ejecución

```bash
uvicorn app.main:app --reload          # servicio IA
streamlit run streamlit_app.py         # cliente (API_BASE_URL, por defecto http://localhost:8000)
```
