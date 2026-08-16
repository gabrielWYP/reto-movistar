# Agente de Cobranzas y Recaudación · SON-IA

Módulo independiente que reconstruye la cartera B2B, prioriza gestiones de
cobro y detecta excepciones de aplicación documental. Python calcula todos los
importes e indicadores; OpenAI interpreta la pregunta, selecciona una o más
herramientas cerradas y explica únicamente resultados estructurados.

## Estructura

```text
Agente Cobranzas/
├── BACK/                 FastAPI, tools, reglas, contrato y pruebas
├── FRONT/                interfaz estática humanizada
├── DEPLOY/kubernetes/    frontend y backend en pods separados
├── compose.yaml          ejecución independiente en dos servicios
└── README.md
```

La implementación vive aquí. `back/` y `front/` de la raíz contienen solo el
router y los recursos mínimos que permiten publicarla junto con SON-IA.

## Capacidades

- cartera global y por cliente;
- trazabilidad factura → pagos → notas de crédito → saldo;
- saldo pendiente, saldo vencido, días de atraso y antigüedad;
- facturas vencidas y pagos parciales;
- priorización reproducible de clientes;
- aplicaciones de pago y casos que requieren revisión;
- carga atómica de hasta seis CSV compatibles;
- preguntas en lenguaje natural con OpenAI y tools;
- contrato JSON `1.1` reutilizable por Supervisor y BI.

No realiza conciliación bancaria: el dataset no contiene extractos ni marcas
de tiempo bancarias. El alcance actual es aplicación documental de pagos.

## Indicadores del reto

- **Cobranza aplicada / facturación:** pagos vinculados observados al corte
  divididos entre facturación.
- **Cobrado dentro de 30 días:** pagos aplicados desde la emisión hasta el día
  30 inclusive, divididos entre facturas que ya tuvieron una ventana completa
  de 30 días al corte. Las sobreaplicaciones no inflan el numerador.
- **Periodo medio de cobro:** días entre emisión y pago, ponderados por el
  importe aplicado. Se excluyen pagos anteriores a la emisión y cada factura se
  limita a su importe facturado.

Cada KPI devuelve valor, unidad, definición y población utilizada dentro de
`kpis`. Los valores de acceso rápido también están en `metrics`.

## Tools determinísticas

| Tool | Resultado |
|---|---|
| `portfolio_snapshot` | KPIs, saldos, pagos y antigüedad global. |
| `customer_snapshot` | Situación, prioridad y facturas de un cliente. |
| `invoice_trace` | Pagos, créditos, saldo, vencimiento y evidencia documental. |
| `collection_priorities` | Ranking explicable con componentes del índice. |
| `reconciliation_exceptions` | Aplicaciones y documentos que requieren revisión. |

Las reglas de antigüedad, tolerancia y prioridad están centralizadas en
`BACK/src/collections_agent/rules.py`.

## OpenAI y control de costo

`OPENAI_API_KEY` se inyecta únicamente en runtime. El SDK oficial usa Responses
API, `gpt-5.6-terra` y razonamiento `low` por defecto. El modelo recibe solo
schemas y evidencia compacta, nunca CSV completos. Se permiten tres llamadas a
tools como máximo y 700 tokens de salida por respuesta, ambos configurables.

Sin clave, las cinco vistas y endpoints determinísticos siguen disponibles; el
endpoint conversacional informa que un administrador debe configurar OpenAI.
No existe enrutamiento por palabras clave que se presente como agente de IA.

Variables:

- secret: `OPENAI_API_KEY`;
- configuración: `SONIA_COLLECTIONS_MODEL`,
  `SONIA_COLLECTIONS_REASONING_EFFORT`, `SONIA_COLLECTIONS_MAX_TOOL_CALLS`,
  `SONIA_COLLECTIONS_MAX_OUTPUT_TOKENS`, límites de carga y dataset opcional;
- reglas de negocio: `rules.py`, versionado y documentado.

## Carga de CSV

La carga valida nombre/estructura, encabezados, columnas obligatorias, fechas,
importes positivos, duplicados y relaciones factura-pago. Un conflicto de
cliente o cuenta rechaza el paquete completo. Pagos o notas que apuntan a
facturas fuera del corte se aceptan como excepciones explícitas, nunca se
asocian silenciosamente a otro documento. El dataset activo solo se reemplaza
cuando todo el paquete es compatible y permanece en memoria.

## API

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

## Ejecutar independientemente

Desde la raíz del repositorio:

```bash
docker compose --file "Agente Cobranzas/compose.yaml" up --build --wait
```

Interfaz: `http://localhost:8081`. Para usar preguntas con IA, define
`OPENAI_API_KEY` en un `.env` local no versionado o en el secret de Kubernetes.

Para desarrollo del backend:

```powershell
cd "Agente Cobranzas\BACK"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -ra
.\.venv\Scripts\python.exe -m collections_agent
```

## Integración futura

El Supervisor puede invocar `CollectionsBackend.execute_tool()` o `query()` sin
depender del frontend. Los resultados contienen estado, métricas, KPIs,
hallazgos, alertas, evidencia y acciones recomendadas. No se implementan aquí
Facturación, BI, Control Tower ni orquestación.

## Limitaciones

- datos anonimizados del reto, no sistemas corporativos en tiempo real;
- sin extractos bancarios ni tiempo real de identificación/conciliación;
- no predice promesas de pago ni causas de mora;
- no ejecuta cobros, comunicaciones ni asientos contables;
- las recomendaciones requieren validación humana.
