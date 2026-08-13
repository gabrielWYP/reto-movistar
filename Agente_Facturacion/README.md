# SON-IA Billing Assurance Agent — Conversational MVP v0.3

Agente determinístico y auditable para responder: **¿la facturación disponible presenta excepciones documentales que requieren revisión?**

No emite facturas, no calcula PxQ ni tarifas contractuales, no usa pagos, no calcula deuda/mora, no hace conciliación bancaria y no declara fugas o errores financieros confirmados.

## Aplicación web local

La experiencia principal es un **Revenue Operations Control Center — Facturación**, disponible sólo de forma local en `http://127.0.0.1:8503`.

```powershell
$env:PYTHONPATH = "src"
python -m billing_agent.web_app --dataset "C:\ruta\DATASET" --port 8503 --open
```

Para una persona no técnica, ejecutar `Iniciar Agente Facturacion.cmd` desde la raíz del repositorio, o:

```powershell
.\Iniciar Agente Facturacion.ps1 -Dataset "C:\ruta\DATASET"
```

El navegador se abre automáticamente. Para cerrar la aplicación, volver a la consola y presionar `Ctrl+C`.

Vistas:

- **Resumen:** universo procesado, prioridades de revisión, narrativa determinística y calidad de datos.
- **Cliente:** Billing 360 de cuentas con factura y/o planta; evidencia de documentos y alertas por cuenta.
- **Factura:** campos del documento, control visual neto + IGV, notas de crédito y evidencia.
- **Quiebres de ciclo:** investigación de periodos antes / sin documento / después.
- **Notas de crédito:** ranking de ajustes post-emisión por el umbral heurístico existente.

La UI consume exclusivamente las cinco tools de `BillingService`; no recalcula tolerancias, materialidad, joins ni severidades. La trazabilidad técnica completa del `AgentResponse` está disponible de manera expandible.

## Modo conversacional

La vista **Asistente SON-IA** añade una capa agéntica ligera encima del core, sin reemplazar ninguna vista ni regla existente. Funciona sin API key mediante un router local determinístico y una explicación evidence-first. Ejemplos:

- `¿Qué debería revisar hoy?`
- `Revisa la factura S300-0256413`
- `Analiza CLIENT_00434`
- `¿Y la cuenta 993722637?` (después de consultar el cliente)
- `Busca quiebres de CLIENT_00434`
- `Revisa las notas de crédito materiales`

Arquitectura:

```text
Pregunta → BillingAgentRuntime → router/registro cerrado → BillingService
         → AgentResponse intacto → explicación grounded → Web local o Supervisor futuro
```

El runtime sólo permite una tool principal por consulta:

- `billing_health_snapshot`
- `customer_billing_check`
- `invoice_quality_check`
- `billing_cycle_gaps`
- `credit_note_review`

Los intents son `portfolio_health`, `customer_review`, `invoice_review`, `cycle_gap_review`, `credit_note_review`, `out_of_scope` y `clarification_required`. El contexto es sólo de sesión local y guarda identificadores/resultados recientes, nunca CSV completos.

Consultas de deuda, pago, mora, cobranza o recaudo devuelven `HANDOFF_RECOMMENDED` hacia `collections`; consultas de segmento, concentración, estrategia o riesgo de recupero se derivan hacia `bi`. Facturación no abre ni usa la tabla de Pagos.

### Privacidad y LLM opcional

El producto base no requiere LLM ni API key: muestra **Modo local determinístico**. Si se configura `OPENAI_API_KEY`, la interfaz muestra **Modo IA: LLM + tools**. El modelo se elige con `SONIA_BILLING_MODEL` (por defecto `gpt-5`) y es opcional. El adaptador HTTP recorre explícitamente `output → message → content → output_text`; no depende de la propiedad de conveniencia del SDK.

El proveedor sólo recibe en fase 1 la pregunta y los esquemas cerrados de las cinco tools. En fase 2 recibe un resultado compacto: operación, métricas, hallazgos, acciones, IDs de evidencia y limitaciones. No se envían CSV, modelo canónico, filas fuente completas, pagos ni herramientas arbitrarias; las llamadas llevan `store: false`. Si la API falla, devuelve JSON inválido, propone una tool no autorizada o argumentos inválidos, el runtime vuelve al router y explicación determinísticos.

La respuesta pública `AgentResult` contiene `agent`, `intent`, `route`, `tool`, `arguments`, `answer`, `status`, `agent_response` intacto y `trace`. El bloque **Ver razonamiento operativo** muestra intent, router, tool, argumentos, estado, referencias y duración; no expone chain-of-thought. La Web MVP conserva una única sesión conversacional local para la demo actual; el contexto se pierde al reiniciar el servidor y no constituye un sistema de sesiones multiusuario.

## Alcance y fuentes

Lee los cinco CSV oficiales de Facturación, como directorio o ZIP:

- `001_TBL_CLIENTES_B2B.csv`
- `002_TBL_PLANTA_FIJA_B2B.csv`
- `003_TBL_PLANTA_MOVIL_B2B.csv`
- `005_TBL_FACTURAS_B2B.csv`
- `006_TBL_NOTAS_CREDITO_B2B.csv`

`RAZON_SOCIAL` es la identidad temporal canónica. El NIF/RUC se preserva como evidencia, pero no se usa para joins porque es inconsistente entre las fuentes anonimizadas. `COD_CUENTA` se conserva como texto. Las filas de planta móvil nunca se deduplican automáticamente.

Joins:

```text
Cliente → Factura: RAZON_SOCIAL
Factura → NC: NRO_DOC_FISCAL = FACTURA_AFECTADA
Factura → Planta: RAZON_SOCIAL + COD_CUENTA (left join)
```

## Reglas

| Código | Categoría | Criterio |
|---|---|---|
| `MISSING_CURRENCY` | DETERMINISTIC | `MONEDA` vacía. |
| `ZERO_VALUE_INVOICE` | DETERMINISTIC | Total de factura igual a cero; requiere contexto. |
| `ARITHMETIC_MISMATCH` | DETERMINISTIC | `abs(neto + IGV - total) > S/ 0.01`. |
| `CREDIT_NOTE_PRESENT` | DETERMINISTIC | NC enlazada documentalmente. |
| `MATERIAL_CREDIT_NOTE` | HEURISTIC | NC/factura ≥25%: MEDIUM; ≥50%: HIGH. |
| `BILLING_CYCLE_GAP` | HEURISTIC | M y M+2 cíclicos presentes, sin M+1 para cliente-cuenta. |
| `PLANT_WITHOUT_BILLING_EVIDENCE` | HEURISTIC | Planta Active/Activo sin factura en el extracto. No prueba no-facturación. |
| `DATA_QUALITY_JOIN_GAP` | DATA_QUALITY | Cuenta facturada sin planta enlazada. |

Las diferencias de hasta S/ 0.01 se consideran redondeo y no generan alerta. Una nota de crédito es un ajuste post-emisión; no prueba una factura errónea.

## Ejecución

Requiere Python 3.11+ y no tiene dependencias externas. Desde la raíz del repositorio:

```powershell
$env:PYTHONPATH = "src"
python -m billing_agent.cli --dataset "C:\ruta\DATASET" health
python -m billing_agent.cli --dataset "C:\ruta\DATASET" customer CLIENT_00434
python -m billing_agent.cli --dataset "C:\ruta\DATASET" invoice S300-0256413
python -m billing_agent.cli --dataset "C:\ruta\DATASET" gaps --customer CLIENT_00434 --account 993722637
python -m billing_agent.cli --dataset "C:\ruta\DATASET" credit-notes --invoice S1AA-0052649961
```

Para ejecutar pruebas con los CSV oficiales:

```powershell
$env:PYTHONPATH = "src"
$env:SONIA_DATASET = "C:\ruta\DATASET"
python -m unittest discover -s tests -v
```

## Tools y contrato

Las tools son `billing_health_snapshot`, `customer_billing_check`, `invoice_quality_check`, `billing_cycle_gaps` y `credit_note_review`.

Todas devuelven JSON con `contract_version: "1.0"`, `agent: "billing"`, fechas de corte, evidencia fuente, calidad de datos, metodología y alcance. El contrato contiene: `entity`, `status`, `metrics`, `findings`, `alerts`, `recommended_actions`, `evidence`, `data_quality`, `visualization_hints`, `analysis_scope`, `methodology` y `upstream_inputs`.

Arquitectura visual:

```text
CSV oficiales → BillingService → 5 tools determinísticas → AgentResponse → presentation.py → web_app.py
```

## Casos demo

- `S300-0256413`: diferencia aritmética superior a S/ 0.01.
- `FOBF-00121753`: moneda ausente.
- `S7AA-0067926518`: total cero.
- `S1AA-0052649961` / `SJFE-0031656645`: NC material, aproximadamente 73.8%.
- `CLIENT_00434` / `993722637`: abril y mayo de 2026, ausencia en junio y factura en julio; candidato de quiebre documental.

## Limitaciones

El extracto no contiene tarifario/PxQ contractual, motivo de NC, cobertura histórica completa, identificadores individuales de línea móvil ni una prueba del importe esperado. Por ello el agente recomienda validaciones humanas y nunca convierte una anomalía documental en pérdida o error confirmado.

No hay integración activa con Supervisor/BI/Cobranzas, pagos, ML ni acciones automáticas. El LLM es opcional y nunca calcula ni sustituye las reglas determinísticas. La integración multi-agente sigue fuera de este MVP.
