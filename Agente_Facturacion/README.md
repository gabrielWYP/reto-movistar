# SON-IA Billing Assurance Agent · v1.0

Agente evidence-first para responder: **¿qué excepciones documentales de Facturación requieren atención, por qué y con qué evidencia?**

No emite facturas, no calcula tarifa contractual/PxQ, no usa la tabla 004 Pagos, no determina deuda o mora, no atribuye el motivo de una nota de crédito y no declara fugas ni errores financieros confirmados.

## Arquitectura

```text
FRONT (proceso/pod independiente)
  index.html + assets/app.js + assets/styles.css
  Nginx / proxy relativo /api/*
                 ↓ HTTP
BACK (proceso/pod independiente)
  FastAPI → BillingAgentRuntime → catálogo cerrado → BillingService
                 ↓
  DatasetRegistry → DatasetSource CSV/ZIP → modelo canónico
```

Existe una sola implementación Billing productiva: `Agente_Facturacion/BACK/src/billing_agent/`. El backend no importa HTML ni Nginx; el frontend no lee CSV, no conoce rutas internas, no contiene reglas financieras y no accede a secretos.

```text
Agente_Facturacion/
├── BACK/     paquete Python, API, runtime, datasets y tests
├── FRONT/    cliente estático y contenedor Nginx
├── DEPLOY/   contrato y manifiestos Kubernetes de referencia
└── compose.yaml
```

## Inicio local

Desde la raíz del repositorio:

```powershell
& ".\Iniciar Agente Facturacion.ps1" -Dataset ".\data\source\DATASET"
```

También puede configurarse `SONIA_DATASET`. El launcher crea/reutiliza `.venv`, instala las dependencias declaradas si faltan, inicia BACK en `127.0.0.1:8080`, FRONT en `127.0.0.1:8503` y abre el navegador. `Ctrl+C` cierra ambos procesos.

Inicio manual:

```powershell
$env:SONIA_DATASET = ".\data\source\DATASET"
$env:PYTHONPATH = ".\Agente_Facturacion\BACK\src"
.\.venv\Scripts\python.exe -m uvicorn billing_agent.app:app --host 127.0.0.1 --port 8080
```

En otra consola:

```powershell
.\.venv\Scripts\python.exe .\Agente_Facturacion\FRONT\dev_server.py --host 127.0.0.1 --port 8503
```

## Frontend

Las vistas son:

- Resumen: estado general, assurance accionable y calidad/cobertura separada.
- Billing 360: cliente, cuentas, planta, facturas, hallazgos y evidencia.
- Factura: campos documentales, control aritmético derivado por BACK y NC vinculadas.
- Quiebres de ciclo: evidencia antes / periodo sin documento / después.
- Notas de crédito: ajustes post-emisión y hallazgos de materialidad.
- Asistente SON-IA: router cerrado, contexto explícito del navegador y fallback local.
- Fuente de datos: origen, corte, conteos por fuente, carga y eliminación temporal.

Los códigos técnicos y el JSON completo permanecen disponibles en paneles de trazabilidad cerrados por defecto. La primera capa traduce categorías: validación determinística, señal heurística y calidad de datos.

## API

| Método | Endpoint | Responsabilidad |
|---|---|---|
| GET | `/health` | Probe estable de infraestructura. |
| GET | `/api/status` | Estado del agente y dataset seleccionado. |
| GET | `/api/health` | `billing_health_snapshot`. |
| GET | `/api/customer` | `customer_billing_check`. |
| GET | `/api/invoice` | `invoice_quality_check`. |
| GET | `/api/gaps` | `billing_cycle_gaps`. |
| GET | `/api/credit-notes` | `credit_note_review`. |
| POST | `/api/conversation` | Router cerrado, respuesta grounded y contexto explícito. |
| POST | `/api/datasets` | Carga multipart de cinco CSV o un ZIP. |
| GET | `/api/datasets/{dataset_id}/status` | Conteos y corte, sin rutas internas. |
| DELETE | `/api/datasets/{dataset_id}` | Libera el dataset temporal de la memoria del proceso. |

Las cinco tools conservan `AgentResponse v1.0`: `contract_version`, `agent`, `operation`, `as_of_date`, `entity`, `status`, `metrics`, `findings`, `alerts`, `recommended_actions`, `evidence`, `data_quality`, `visualization_hints`, `analysis_scope`, `methodology` y `upstream_inputs`.

## Datasets dinámicos

Fuentes Billing requeridas:

- `001_TBL_CLIENTES_B2B.csv`
- `002_TBL_PLANTA_FIJA_B2B.csv`
- `003_TBL_PLANTA_MOVIL_B2B.csv`
- `005_TBL_FACTURAS_B2B.csv`
- `006_TBL_NOTAS_CREDITO_B2B.csv`

`004_TBL_PAGOS_B2B.csv` no pertenece a este agente. Se acepta un directorio predeterminado mediante `SONIA_DATASET`, cinco archivos CSV multipart o un ZIP con esas cinco fuentes.

Antes de construir `BillingService` se validan: cantidad, nombres reconocidos, extensión, archivo no vacío, tamaño, encoding, delimitador, headers, columnas mínimas y estructura. ZIP valida firma, límite descomprimido y rechaza rutas absolutas o `..`. CSV se trata exclusivamente como datos.

Cada carga recibe un `dataset_id` aleatorio. Cada ID mantiene su propio `BillingService`; no existe un `CURRENT_DATASET` mutable. Los CSV y ZIP se validan desde bytes y el modelo resultante vive exclusivamente en memoria del proceso: no se escriben archivos temporales. Los registros admiten DELETE y TTL, y se pierden al reiniciar el pod.

Variables de seguridad y capacidad:

- `SONIA_MAX_UPLOAD_MB` (20 por defecto).
- `SONIA_MAX_UNCOMPRESSED_MB` (48 por defecto).
- `SONIA_MAX_UPLOAD_FILES` (5 por defecto).
- `SONIA_DATASET_TTL_SECONDS` (4 horas por defecto).

El boundary `DatasetSource` permite sustituir CSV/ZIP por BD, API, lake o warehouse sin modificar frontend, runtime, tools ni contrato.

## Contexto y OpenAI opcional

`POST /api/conversation` recibe y devuelve `context`. El navegador conserva sus identificadores; el backend no comparte un `SessionContext` global ni necesita Redis. Dos navegadores no heredan cliente, cuenta o factura entre sí.

Sin `OPENAI_API_KEY`, las cinco tools, router, explicaciones, handoffs y frontend funcionan de forma determinística. Si se configura, la key solo vive en BACK y `SONIA_BILLING_MODEL` usa `gpt-5` por defecto. Se mantienen `store: false`, `compact_for_llm` y `extract_output_text`. El proveedor no recibe CSV, ZIP, rutas temporales, filas crudas ni dataset completo. Ante cualquier fallo, se usa fallback determinístico.

Consultas de deuda/pago/mora/cobranza/recaudación devuelven `HANDOFF_RECOMMENDED` hacia `collections`; segmento/concentración/riesgo de recuperación hacia `bi`. No existe integración activa entre agentes en este entregable.

## Reglas preservadas

| Código | Categoría | Criterio |
|---|---|---|
| `MISSING_CURRENCY` | DETERMINISTIC | `MONEDA` vacía. |
| `ZERO_VALUE_INVOICE` | DETERMINISTIC | Total igual a cero; requiere contexto. |
| `ARITHMETIC_MISMATCH` | DETERMINISTIC | `abs(neto + IGV - total) > S/ 0.01`. |
| `CREDIT_NOTE_PRESENT` | DETERMINISTIC | `FACTURA_AFECTADA` enlaza una NC. |
| `MATERIAL_CREDIT_NOTE` | HEURISTIC | NC/factura ≥25%: MEDIUM; ≥50%: HIGH. |
| `BILLING_CYCLE_GAP` | HEURISTIC | M y M+2 cíclicos presentes, sin evidencia en M+1 para cliente-cuenta. |
| `PLANT_WITHOUT_BILLING_EVIDENCE` | HEURISTIC | Planta activa sin factura en el extracto; señal exploratoria. |
| `DATA_QUALITY_JOIN_GAP` | DATA_QUALITY | Cuenta facturada sin planta enlazada. |

Identidad temporal: `RAZON_SOCIAL`. Join factura–planta: `RAZON_SOCIAL + COD_CUENTA`. Join NC–factura: `FACTURA_AFECTADA = NRO_DOC_FISCAL`. NIF/RUC se conserva como evidencia y no se usa como llave. Planta móvil no se deduplica.

## Docker y K3S

```powershell
$env:SONIA_DATASET = ".\data\source\DATASET"
docker compose -f .\Agente_Facturacion\compose.yaml up --build
```

Compose publica solo FRONT en `127.0.0.1:8080`; Nginx resuelve BACK como `billing-back:8080`. Ambos contenedores son no-root, independientes y de filesystem read-only con `/tmp`/caches temporales.

La implementación respeta el contrato de `K3S_Infra`: BACK `0.0.0.0:8080`, probe `/health`, usuario 1001, `/tmp` escribible; FRONT puerto 8080, usuario 101 y `BACKEND_HOST=reto-movistar-back`. No se modificó ese repositorio.

## Pruebas

```powershell
$env:SONIA_DATASET = ".\data\source\DATASET"
$env:PYTHONPATH = ".\Agente_Facturacion\BACK\src"
.\.venv\Scripts\python.exe -m unittest discover -s .\Agente_Facturacion\BACK\tests -v
```

La suite incluye regresión del core, AC-01…AC-11, API/arquitectura, uploads válidos e inválidos, traversal ZIP, aislamiento, contexto y minimización de datos. Consulta [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md).
Los resultados manuales y de demo quedan registrados en [VALIDATION_REPORT.md](VALIDATION_REPORT.md).

## Casos demo oficiales

- `S300-0256413`: diferencia aproximada S/ 0.06, por encima de tolerancia; requiere validación.
- `FOBF-00121753`: moneda no informada.
- `S7AA-0067926518`: factura con importe cero; causa no disponible.
- `S1AA-0052649961` / `SJFE-0031656645`: NC material aproximada 73.8%; motivo no disponible.
- `CLIENT_00434` / `993722637`: mayo y julio con evidencia y junio sin documento cíclico; posible quiebre, no ausencia confirmada.

## Limitaciones

El extracto no contiene tarifario/PxQ contractual, motivo de NC, cobertura histórica completa, identificadores individuales de línea móvil ni importe contractual esperado. Las cargas UI son temporales y el registro vive en memoria de un único proceso BACK; para escalar a varias réplicas se necesitaría almacenamiento/registro compartido, fuera del MVP. Pagos, deuda, ML, acciones irreversibles, Supervisor y orquestación multiagente permanecen fuera de alcance.
