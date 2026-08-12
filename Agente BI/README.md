# Agente BI - BI Core v0.1

Núcleo determinístico y evidence-first para SON-IA. Implementa adapters de los seis CSV oficiales, modelo canónico de ingresos, controles de calidad y tres operaciones JSON: `data_quality_report`, `executive_snapshot` y `risk_concentration`.

No incluye LLM, dashboard adaptativo, predicción ni estrategias de recupero. Los importes monetarios del Core se calculan solo en PEN; pagos USD o sin factura/documento compatible no se mezclan en los KPIs.

Ejemplos:

```powershell
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' data-quality
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 executive
python -m bi_agent.cli --dataset 'C:\ruta\DATASET' --as-of-date 2026-07-31 risk-concentration --dimension SEGMENTO_PAIS --metric overdue_balance
```
