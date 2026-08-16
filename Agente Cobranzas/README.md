# Agente de Cobranzas y Recaudación · SON-IA

Módulo independiente para reconstruir la cartera B2B, priorizar gestiones de
cobro y detectar aplicaciones de pago que requieren validación. Los cálculos
financieros se ejecutan en Python; OpenCode Go interpreta la intención, selecciona
tools y redacta respuestas sustentadas en evidencia estructurada.

## Arquitectura

```text
Browser
  ↓
FRONT: Nginx + interfaz estática humanizada
  ↓ /api/collections/*
BACK: FastAPI
  ↓
CollectionsBackend → OpenCode/dispatch → CollectionsService
                                          ↓
                       ledger + reglas + dataset validado
                                          ↓
                         AgentResponse 1.0 + evidencia
```

```text
Agente Cobranzas/
├── BACK/     paquete `collections_agent`, API y pruebas
├── FRONT/    interfaz estática y contenedor Nginx
├── data/     datos locales ignorados por Git e imágenes
└── README.md
```

## Capacidades y tools

| Tool | Resultado determinístico |
|---|---|
| `portfolio_snapshot` | KPIs globales y antigüedad de la deuda. |
| `customer_snapshot` | Situación de cobranza de un cliente. |
| `invoice_trace` | Factura, pagos aplicados, saldo y estados. |
| `collection_priorities` | Ranking explicable para gestión. |
| `reconciliation_exceptions` | Casos de aplicación documental que requieren validación. |

Todas las respuestas financieras incluyen contrato estable, fecha de corte,
métricas, hallazgos, acciones y evidencia. El agente no afirma conciliación
bancaria porque el dataset no contiene extractos bancarios.

## Reglas de negocio versionadas

`BACK/src/collections_agent/rules.py` es la fuente ejecutable de los tramos de
antigüedad, tolerancia y prioridad. El índice de prioridad pondera monto vencido
(45%), mayor atraso (30%), proporción vencida (15%) y concentración en cartera
(10%). Prioridad alta empieza en 60 puntos y media en 30. Estos valores son
explicables y deben revisarse con negocio antes de un uso productivo.

## API pública

- `GET /health`
- `GET /api/collections/status`
- `GET /api/collections/portfolio`
- `GET /api/collections/customer`
- `GET /api/collections/invoice`
- `GET /api/collections/priorities`
- `GET /api/collections/exceptions`
- `POST /api/collections/dataset`
- `POST /api/collections/query`
- `GET /api/docs`

La carga acepta únicamente CSV compatibles. Valida nombres de tabla, columnas,
tipos, límites y relaciones mínimas antes de reemplazar el dataset activo. Una
carga inválida no mezcla ni sustituye silenciosamente la información anterior.

## Ejecución local

El despliegue soportado usa el `compose.yaml` raíz: un contenedor backend para
los tres agentes y un contenedor frontend para todas las interfaces.

```bash
docker compose up --build --wait
```

Para desarrollar únicamente el paquete Python:

```powershell
cd "Agente Cobranzas\BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m collections_agent
```

## OpenCode Go y control de costo

`OPENCODE_KEY` se inyecta en runtime y nunca se versiona. El endpoint compatible
con OpenAI usa `deepseek-v4-flash` por defecto. Cada consulta realiza como máximo
una llamada de selección y una de interpretación; la selección debe contener
exactamente una tool autorizada. Los límites de salida se configuran mediante
variables `SONIA_COLLECTIONS_*`.

El modelo nunca recibe el dataset completo ni calcula saldos. Recibe solamente
evidencia compacta del resultado determinístico. Sin clave o ante un fallo del
proveedor, las rutas y tools siguen disponibles y la respuesta indica el modo
determinístico; la insignia `Hecho con IA` solo aparece en modo `llm`.

## Guardrails y observabilidad

- La selección debe producir exactamente una de las cinco tools autorizadas.
- La fecha de corte enviada por la interfaz prevalece sobre la sugerida por el modelo.
- Identificadores, límites y argumentos desconocidos se validan antes del dispatch.
- No se permiten cálculos del modelo, código arbitrario, predicciones ni causalidad.
- La conciliación es documental y las excepciones no se presentan como errores confirmados.
- Cada etapa registra proveedor, modelo, latencia y tokens cuando el proveedor los informa.
- Los logs nunca incluyen prompts, CSV, evidencia completa, API keys ni cabeceras de autorización.

`POST /api/collections/query` devuelve `mode`, `tool_used`, argumentos validados,
resultado determinístico, metadata del prompt y consumo de tokens. En un fallo del
proveedor devuelve `deterministic_fallback`, sin marcar la respuesta como generada por IA.

## Integración con SON-IA

La implementación principal permanece en esta carpeta. La imagen compartida
`back/Dockerfile` instala `collections_agent` y monta su router; la imagen
`front/Dockerfile` publica este frontend bajo `/agents/collections/`. No existen
Deployments ni contenedores productivos específicos por agente. El
Supervisor podrá consumir `CollectionsBackend.execute_tool()` o `query()` sin
depender del frontend.

## Pruebas

```powershell
cd "Agente Cobranzas\BACK"
.\.venv\Scripts\python.exe -m pytest -ra
```

Las pruebas con el ZIP oficial se habilitan mediante `SONIA_DATASET`. El dataset
no se versiona, no se incorpora a imágenes y permanece fuera de prompts.

## Límites

- Trabaja con datos anonimizados del reto, no con sistemas corporativos reales.
- La conciliación es documental factura-pago, no bancaria.
- No ejecuta cobros, comunicaciones ni aplicaciones contables.
- Las recomendaciones requieren validación humana antes de cualquier acción.
