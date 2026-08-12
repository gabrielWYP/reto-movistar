# SON-IA Business Intelligence Agent v1.0

Agente BI para la demo SON-IA: convierte el ciclo de ingresos B2B del dataset del hackathon en decisiones explicables. Los cálculos financieros son determinísticos; la IA opcional solo selecciona una herramienta cerrada e interpreta el resultado respaldado por evidencia.

## Arquitectura

```text
Consulta en navegador / Supervisor futuro
              ↓
Agent runtime (router determinístico o LLM opcional)
              ↓
Una de las 5 tools cerradas
              ↓
BIService → canonical revenue model → CSV oficiales
              ↓
AgentResponse + evidence + visualization_hints
              ↓
Adaptive Dashboard declarativo
```

El frontend no calcula importes. El catálogo visual es cerrado: KPI cards, barras, Pareto, ageing, tablas de ranking/oportunidades/evidencia, insight cards y alert cards. Los hints desconocidos se ignoran explícitamente; nunca se ejecuta código generado por un modelo.

## Tools disponibles

| Tool | Responde |
|---|---|
| `executive_snapshot` | Estado general del ciclo de ingresos, saldo, vencimiento y ageing. |
| `risk_concentration` | Dónde se concentra la exposición por dimensión permitida. |
| `recovery_intelligence` | Oportunidad de recupero, Pareto, seguimiento preventivo y contexto documental. |
| `management_insights` | Qué debería conocer y priorizar la gerencia. |
| `data_quality_report` | Fuentes, joins, moneda, exclusiones y limitaciones. |

Las dimensiones permitidas son `SEGMENTO_PAIS`, `SUNAT_DEPARTAMENTO`, `SISTEMA`, `FUENTE` y `SERVICE_PROFILE`.

## BI frente a Cobranzas

Cobranzas responde qué se pagó, qué documentos están pendientes y qué casos deben gestionar los gestores. BI responde qué significa la exposición a nivel de negocio: concentración, cobertura Pareto, oportunidades y estrategia. BI no genera un `priority_score` alternativo.

`integration.py` conserva un boundary JSON público para recibir en el futuro un `AgentResponse` de Cobranzas. No importa sus clases privadas, no requiere que el agente esté activo y en v1.0 solo registra procedencia.

## Abrir la demo local

Desde la raíz del repositorio:

```powershell
$env:PYTHONPATH = "src"
python -m bi_agent.web_app --dataset "C:\Disco D\Universidad\Hackathon MOVISTAR BOOTCAMP\SONIA_DESAFIO_03\DATASET" --port 8502 --open
```

O abre `Iniciar Agente BI.cmd`. La interfaz escucha solo en `127.0.0.1:8502`, distinto del puerto 8501 utilizado por la interfaz de Cobranzas actual.

No se requiere API key: las sugerencias, las cinco tools, los gráficos, las tablas y la trazabilidad funcionan en modo determinístico.

## Modo IA opcional

Para permitir que un modelo OpenAI elija la tool e interprete el JSON compacto:

```powershell
$env:OPENAI_API_KEY = "..."
# Opcional: $env:SONIA_BI_MODEL = "gpt-5.6-terra"
python -m bi_agent.web_app --dataset "RUTA_DATASET" --port 8502 --open
```

La key no se guarda en Git. Solo se envían la pregunta, schemas de las cinco tools y el resultado compacto de la tool ya ejecutada; nunca los CSV ni el canonical model. Si falla la API, el endpoint vuelve a modo determinístico sin afectar los cálculos.

## Preguntas demo

1. `¿Cómo está el ciclo de ingresos al 31 de julio?` → `executive_snapshot`
2. `¿Dónde está concentrado el saldo vencido?` → `risk_concentration`
3. `¿Qué oportunidades de recupero tenemos?` → `recovery_intelligence`
4. `¿Qué debería priorizar la gerencia?` → `management_insights`
5. `¿Qué limitaciones tiene la información?` → `data_quality_report`

La fecha de corte siempre es visible, se propaga a la tool y queda en el `AgentResponse`.

## Trazabilidad y límites

La sección **Ver evidencia y trazabilidad** expone la tool, parámetros, metodología, upstream inputs y el JSON completo. Todos los findings, alertas y recomendaciones relevantes usan `evidence_refs`.

- Solo PEN entra a los KPIs monetarios; USD, moneda ausente e incompatibilidades no se mezclan.
- `RAZON_SOCIAL` es la clave temporal de cliente; `NRO_DOC_FISCAL → FACTURA_AFECTADA` es la llave documental; planta se resume primero por `COD_CUENTA`.
- Una nota de crédito implica contexto de revisión documental, no prueba de error de facturación.
- No hay causalidad, conciliación bancaria, provisión contable, forecast, ML ni predicción.
- El resultado describe el dataset anonimizado del hackathon, no toda Integratel.

## CLI determinística

```powershell
python -m bi_agent.cli --dataset "RUTA_DATASET" --as-of-date 2026-07-31 executive
python -m bi_agent.cli --dataset "RUTA_DATASET" --as-of-date 2026-07-31 recovery
python -m bi_agent.cli --dataset "RUTA_DATASET" --as-of-date 2026-07-31 insights
```

## Futuro

Quedan fuera de v1.0: integración final con Supervisor, consumo operativo del output de Facturación/Cobranzas, LLM obligatorio, Adaptive Dashboard generado libremente, HTML externo, ML, forecast y predicción de mora.
