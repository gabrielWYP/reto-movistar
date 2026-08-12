# Agente BI - BI Intelligence v0.2

Agente determinístico y evidence-first para entender qué significa la exposición del ciclo de ingresos B2B del dataset SON-IA. El servicio devuelve JSON compatible con `AgentResponse`, explícitamente referido a un `as_of_date` y a la muestra del hackathon.

## Capacidades

BI Core v0.1 conserva:

- adapters para los seis CSV oficiales y modelo canónico de ingresos;
- reglas de calidad, separación PEN/USD, joins trazables y resumen seguro de planta por `COD_CUENTA`;
- `data_quality_report`, `executive_snapshot` y `risk_concentration`.

BI Intelligence v0.2 añade:

- `recovery_intelligence`: oportunidades por impacto, Pareto y concentración; no crea un score alternativo de Cobranzas;
- `management_insights`: hallazgos ejecutivos ordenados, impacto, evidencia y acciones determinísticas;
- boundary JSON opcional para registrar la procedencia futura de un `AgentResponse` de Cobranzas, sin importar sus clases internas ni recalcular `priority_score`.

## Operaciones

| Operación | Propósito |
|---|---|
| `data_quality_report` | Expone fuentes, joins, monedas, corte y limitaciones. |
| `executive_snapshot` | Resume facturación, pagos aplicados, saldo, vencimiento y ageing. |
| `risk_concentration` | Mide concentración/Pareto por dimensión cerrada. |
| `recovery_intelligence` | Identifica concentración de recupero, seguimiento preventivo y casos con contexto documental. |
| `management_insights` | Compone hechos ejecutivos y acciones sugeridas, separando alertas de calidad. |

Las dimensiones permitidas son: `SEGMENTO_PAIS`, `SUNAT_DEPARTAMENTO`, `SISTEMA`, `FUENTE` y `SERVICE_PROFILE`. No se acepta SQL, expresiones ni código de usuario.

## CLI

```powershell
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' data-quality
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 executive
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 risk-concentration --dimension SEGMENTO_PAIS --metric overdue_balance
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 recovery --dimension SEGMENTO_PAIS --top-n 10
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 insights --dimension SEGMENTO_PAIS --top-n 10
```

`--collections-response respuesta.json` acepta un `AgentResponse` público con `agent: "collections"` y registra su procedencia en `upstream_inputs`. En v0.2 es solo evidencia de integración: BI sigue calculando autónomamente desde CSV y no consume ni reproduce el ranking de Cobranzas.

## Metodología y límites

- Los importes monetarios MVP se calculan solo en PEN. USD, moneda faltante e incompatibilidades documentales no se mezclan con los KPIs.
- `RAZON_SOCIAL` es la clave temporal de cliente; `NRO_DOC_FISCAL → FACTURA_AFECTADA` es la clave documental. Los RUC no se usan para join.
- Recupero se ordena por exposición documentada y cobertura acumulada, no por un `priority_score` alternativo.
- Las notas de crédito activan contexto de revisión documental; no se interpretan como evidencia de error de facturación.
- Los warnings de calidad aparecen en `alerts`, separados de los business findings. No hay conciliación bancaria, causalidad, provisión contable ni forecast.

## Fuera de alcance

Todavía no hay LLM/tool calling conversacional, Adaptive Dashboard, HTML/frontend, ML, forecast, predicción de mora ni integración final con Supervisor. La integración operativa definitiva con Facturación y Cobranzas se definirá cuando su contrato compartido se congele.
