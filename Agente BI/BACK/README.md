# Backend del Agente BI

FastAPI independiente con el mismo contrato público previsto para el backend
modular de SON-IA. Contiene todo cálculo, validación, acceso a datos, LLM
opcional, presentación humanizada y trazabilidad. No contiene ni sirve HTML.

## Desarrollo

```powershell
cd "Agente BI/BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m bi_agent
```

Endpoints:

- `GET /health`
- `GET /api/bi/status`
- `POST /api/bi/dataset`
- `POST /api/bi/query`
- `POST /api/bi/tools/{operation}`
- `GET /api/docs`

El backend inicia sin dataset para permitir health checks. Los seis CSV pueden
cargarse juntos o en varias solicitudes multipart; también se acepta un ZIP.
El límite es 25 MiB y el contenido queda únicamente en RAM hasta reiniciar.

## OpenCode Go

El backend consume `https://opencode.ai/zen/go/v1/chat/completions` con
`OPENCODE_KEY` y `deepseek-v4-flash` por defecto. No persiste la clave ni la
expone en contratos HTTP. La IA selecciona una función autorizada y redacta la
respuesta; los cálculos, validaciones y guardrails permanecen en Python.

Las consultas admitidas se limitan a resumen ejecutivo, concentración de riesgo,
recuperación, hallazgos gerenciales y calidad de datos. Si la primera respuesta
del proveedor no contiene exactamente una tool válida, el selector reintenta una
vez con un presupuesto acotado; después conserva el fallback determinístico. Los
logs registran intento, `finish_reason`, cantidad de tools, latencia y tokens, sin
persistir preguntas ni evidencia del dataset.

Para desarrollo, exporta `OPENCODE_KEY` en el entorno antes de iniciar Compose.
No copies el valor a `.env.example`, Git, Dockerfiles o archivos del frontend.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
```

La regresión oficial se habilita con `SONIA_BI_OFFICIAL_DATASET_PATH`. Los seis
CSV o el ZIP nunca deben copiarse al repositorio o a la imagen.
