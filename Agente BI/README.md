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

FRONT y BACK son construibles y desplegables por separado. El frontend nunca
lee CSV ni calcula importes. El backend no contiene HTML, CSS o JavaScript.

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

Estas fronteras son equivalentes a las del backend modular de `main`.

## Dataset

Configura `SONIA_BI_DATASET_PATH` con un directorio que contenga los seis CSV o
con el ZIP oficial. El dataset permanece fuera de Git y de las imágenes.

```powershell
$env:SONIA_BI_DATASET_PATH = "D:\ruta\DATASET"
```

En contenedores/Kubernetes debe montarse con permisos de solo lectura.

## Ejecución local

```powershell
cd "Agente BI\BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:SONIA_BI_DATASET_PATH = "RUTA_DATASET"
.\.venv\Scripts\python.exe -m bi_agent
```

Para servir FRONT sin Docker se puede usar cualquier servidor estático que
proxifique `/api/*`; el flujo recomendado es Compose.

## Docker Compose

Coloca el dataset en `Agente BI/DATASET/` o indica otra ruta:

```powershell
$env:SONIA_BI_DATASET_SOURCE = "D:\ruta\DATASET"
docker compose up --build
```

Abre `http://localhost:8082`. Solo `bi-front` publica puerto; `bi-back` queda en
la red interna. Para cambiar el puerto usa `SONIA_BI_PUBLIC_PORT`.

## LLM y prompt versionado

Sin `OPENAI_API_KEY`, las cinco consultas funcionan en modo determinístico.
Con key, el modelo puede elegir una tool e interpretar su resultado compacto;
nunca recibe CSV completos, el modelo canónico o secretos.

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

backend = BIBackend(dataset_path=Path("/data/bi"))
result = backend.query("¿Qué debería priorizar la gerencia?", "2026-07-31")
```

También puede usarse `execute_tool`. El Supervisor no necesita conocer el
frontend ni clases internas del modelo financiero.

## Límites

- Describe la muestra anonimizada del hackathon, no toda Integratel.
- No afirma causalidad, conciliación bancaria, provisión, forecast o predicción.
- Una nota de crédito indica contexto documental, no prueba de error.
- No crea un ranking alternativo de Cobranzas.
- La integración obligatoria con Billing, Collections y Supervisor queda fuera.
- El almacenamiento definitivo del dataset en K3S aún debe acordarse.
