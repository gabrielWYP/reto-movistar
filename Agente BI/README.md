# Agente BI · SON-IA

Entregable autocontenido del Agente de Business Intelligence para el ciclo de
ingresos B2B. Convierte métricas operacionales en concentración de riesgo,
oportunidades y recomendaciones ejecutivas respaldadas por evidencia.

Los cálculos financieros son determinísticos: Python carga y relaciona los seis
CSV, aplica fecha de corte, moneda, saldo, ageing, Pareto y reglas. El LLM
opcional solo selecciona una tool cerrada e interpreta su `AgentResponse`.

## Arquitectura

```text
Browser
  ↓
FRONT: Nginx + cliente estático
  ↓ /api/*
BACK: FastAPI
  ↓
BIBackend → ask/dispatch → BIService → modelo canónico → dataset read-only
                              ↓
                 AgentResponse 1.0 + evidencia
                              ↓
                presentación + dashboard declarativo
```

```text
Agente BI/
├── BACK/     paquete Python, prompts, API y tests
├── FRONT/    interfaz estática y contenedor Nginx
├── DEPLOY/   contrato y manifiestos Kubernetes de referencia
└── compose.yaml
```

FRONT y BACK siguen siendo construibles por separado para desarrollo. En la
integración productiva, `back/Dockerfile` instala `bi_agent` junto con el backend
principal y `front/Dockerfile` publica este frontend bajo `/bi/`. El frontend
nunca lee CSV ni calcula importes; el backend no contiene HTML, CSS o JavaScript.

## Tools

| Tool | Propósito |
|---|---|
| `executive_snapshot` | Estado general de facturación, pagos vinculados y cartera. |
| `risk_concentration` | Concentración y Pareto por dimensiones autorizadas. |
| `recovery_intelligence` | Oportunidades de recupero por impacto de negocio. |
| `management_insights` | Hallazgos y acciones prioritarias para gerencia. |
| `data_quality_report` | Calidad, joins, exclusiones y limitaciones. |

Todas respetan `as_of_date`, mantienen PEN y USD separados y devuelven
`AgentResponse 1.0` con evidencia y metodología.

## API pública

- `GET /health`
- `GET /api/bi/status`
- `POST /api/bi/dataset`
- `POST /api/bi/query`
- `POST /api/bi/tools/{operation}`
- `GET /api/docs`

Ejemplo:

```json
{
  "question": "¿Dónde está concentrado el saldo vencido?",
  "as_of_date": "2026-07-31"
}
```

Estas fronteras están montadas directamente en el backend modular de `main`.

## Dataset

En SON-IA integrado, Supervisor es la única fuente de carga manual. BI muestra
y analiza el dataset compartido publicado por `POST /api/supervisor/dataset`;
su pestaña no permite seleccionar ni reemplazar archivos. El adaptador
`POST /api/bi/dataset` se conserva solo para pruebas y desarrollo standalone.
El dataset permanece en memoria y se pierde al reiniciar el contenedor.

## Ejecución local

```powershell
cd "Agente BI\BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m bi_agent
```

Para servir FRONT sin Docker se puede usar cualquier servidor estático que
proxifique `/api/*`; el flujo recomendado es Compose.

## Docker Compose

El flujo integrado recomendado mantiene solo `back` y `front`:

```bash
docker compose up --build --wait
```

La portada queda en `http://localhost:8080/` y BI en
`http://localhost:8080/bi/`.

El Compose de este directorio se conserva únicamente para desarrollo aislado
del agente; no requiere bind mounts ni una ruta del host.

Abre `http://localhost:8082`. Solo `bi-front` publica puerto; `bi-back` queda en
la red interna. Para cambiar el puerto usa `SONIA_BI_PUBLIC_PORT`.

## LLM y prompt versionado

Con `OPENCODE_KEY`, el backend llama al endpoint OpenAI-compatible de OpenCode
Go y usa `deepseek-v4-flash` por defecto. El modelo selecciona una tool cerrada
y genera la respuesta visible a partir de su resultado determinístico compacto;
nunca recibe CSV completos, el modelo canónico o secretos. `SONIA_BI_MODEL`
permite cambiar el modelo por otro identificador disponible en OpenCode Go.

Sin key, o ante un error del proveedor, las cinco tools siguen disponibles en
modo determinístico. La respuesta informa `mode`, proveedor, modelo y versión
del prompt; los logs estructurados registran latencia y tokens cuando OpenCode
los reporta.

`BACK/prompts/system_v1.md` es la única fuente de verdad. Declara identidad,
tools, inputs/outputs permitidos, guardrails, riesgos y evals. La respuesta
exterior registra `prompt_id` y `prompt_version` cuando interviene el LLM.

## Pruebas

```powershell
cd "Agente BI\BACK"
.\.venv\Scripts\python.exe -m pytest -ra
```

Para la regresión con datos oficiales:

```powershell
$env:SONIA_BI_OFFICIAL_DATASET_PATH = "RUTA_DATASET"
.\.venv\Scripts\python.exe -m pytest -m official_dataset -ra
```

## Supervisor

La UI no es obligatoria:

```python
from pathlib import Path

from bi_agent import BIBackend

backend = BIBackend()
dataset_files = {
    path.name: path.read_bytes()
    for path in Path("DATASET").glob("*.csv")
}
backend.upload_dataset(dataset_files, max_bytes=25 * 1024 * 1024)
result = backend.query("¿Qué debería priorizar la gerencia?", "2026-07-31")
```

También puede usarse `execute_tool`. El Supervisor no necesita conocer el
frontend ni clases internas del modelo financiero.

## Límites

- Describe la muestra anonimizada del hackathon, no toda Integratel.
- No afirma causalidad, conciliación bancaria, provisión, forecast o predicción.
- Una nota de crédito indica contexto documental, no prueba de error.
- No crea un ranking alternativo de Cobranzas.
- El router y el frontend están integrados; la orquestación semántica entre
  Billing, Collections y BI todavía debe definirse en el Supervisor.
- El dataset es efímero por diseño; cada reinicio requiere una nueva carga.
