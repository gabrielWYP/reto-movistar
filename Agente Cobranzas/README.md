# Agente de Cobranzas y Recaudación · SON-IA

Módulo independiente para reconstruir la cartera B2B, priorizar gestiones de
cobro y detectar aplicaciones de pago que requieren validación. Los cálculos
financieros se ejecutan en Python; OpenAI interpreta la intención, selecciona
tools y redacta respuestas sustentadas en evidencia estructurada.

## Arquitectura

```text
Browser
  ↓
FRONT: Nginx + interfaz estática humanizada
  ↓ /api/collections/*
BACK: FastAPI
  ↓
CollectionsBackend → OpenAI/dispatch → CollectionsService
                                          ↓
                       ledger + reglas + dataset validado
                                          ↓
                         AgentResponse 1.0 + evidencia
```

```text
Agente Cobranzas/
├── BACK/     paquete `collections_agent`, API y pruebas
├── FRONT/    interfaz estática y contenedor Nginx
├── DEPLOY/   referencia standalone para Kubernetes
├── data/     datos locales ignorados por Git e imágenes
└── compose.yaml
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

## Ejecución independiente

Con Docker:

```bash
cd "Agente Cobranzas"
docker compose up --build --wait
```

Abrir `http://localhost:8081`. Solo `collections-front` publica un puerto;
`collections-back` permanece en la red interna.

Sin Docker:

```powershell
cd "Agente Cobranzas\BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m collections_agent
```

## OpenAI y control de costo

`OPENAI_API_KEY` se inyecta en runtime y nunca se versiona. El SDK oficial usa
Responses API con function calling. El modelo de costo balanceado, esfuerzo
reducido, máximo de llamadas a tools y salida compacta se definen una sola vez en
`BACK/src/collections_agent/config.py`; pueden cambiarse mediante variables
`SONIA_COLLECTIONS_*`.

El modelo nunca recibe el dataset completo ni calcula saldos. Recibe solamente
resultados estructurados de las tools necesarias. Sin clave, todas las rutas y
tools determinísticas siguen disponibles.

## Integración con SON-IA

La implementación principal permanece en esta carpeta. La imagen compartida
`back/Dockerfile` instala `collections_agent` y monta su router; la imagen
`front/Dockerfile` publica este frontend bajo `/agents/collections/`. El
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
