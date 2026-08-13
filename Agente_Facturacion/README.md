# SON-IA Billing Assurance Agent — Core v0.1

Agente determinístico y auditable para responder: **¿la facturación disponible presenta excepciones documentales que requieren revisión?**

No emite facturas, no calcula PxQ ni tarifas contractuales, no usa pagos, no calcula deuda/mora, no hace conciliación bancaria y no declara fugas o errores financieros confirmados.

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

## Casos demo

- `S300-0256413`: diferencia aritmética superior a S/ 0.01.
- `FOBF-00121753`: moneda ausente.
- `S7AA-0067926518`: total cero.
- `S1AA-0052649961` / `SJFE-0031656645`: NC material, aproximadamente 73.8%.
- `CLIENT_00434` / `993722637`: abril y mayo de 2026, ausencia en junio y factura en julio; candidato de quiebre documental.

## Limitaciones

El extracto no contiene tarifario/PxQ contractual, motivo de NC, cobertura histórica completa, identificadores individuales de línea móvil ni una prueba del importe esperado. Por ello el agente recomienda validaciones humanas y nunca convierte una anomalía documental en pérdida o error confirmado.
