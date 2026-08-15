# Agente BI integrado

El Agente BI es un módulo interno del backend común SON-IA. No posee servidor,
frontend, puerto ni Deployment propios.

```text
Usuario
  ↓
Pod front: Nginx + SPA estática
  ↓ /api/bi/*
Pod back: FastAPI
  ↓
BIBackend → ask/dispatch → BIService → modelo canónico
                         ↓
              AgentResponse + evidencia
                         ↓
           presentation + dashboard declarativo
```

La decisión de despliegue está documentada en
`docs/arquitectura/decisiones/ADR-002-client-server-two-pods.md`: un pod
`front` y un pod `back` para toda SON-IA. Facturación, Cobranzas y BI son
módulos del mismo backend; BI no crea pods ni servicios adicionales.

## Boundary pública

El backend compartido monta:

- `GET /api/bi/status`: disponibilidad del dataset, modo LLM y tools.
- `POST /api/bi/query`: pregunta natural, fecha de corte y respuesta completa.
- `POST /api/bi/tools/{operation}`: invocación determinística de una tool.

`BIBackend` también puede ser importado por el Supervisor sin depender de HTTP
ni del frontend. El resultado conserva `AgentResponse`, evidencia, dashboard
declarativo y presentación humanizada.

Las cinco operaciones autorizadas son:

- `data_quality_report`
- `executive_snapshot`
- `risk_concentration`
- `recovery_intelligence`
- `management_insights`

## Dataset y configuración

El dataset oficial no se incorpora a Git ni a las imágenes. En ejecución se
monta como volumen de solo lectura y se configura mediante:

```text
SONIA_BI_DATASET_PATH=/ruta/montada/DATASET
```

Puede ser un directorio con los seis CSV o un ZIP oficial. La carga es lazy:
el backend y `/health` funcionan aunque BI todavía no tenga dataset; sus
endpoints de cálculo responden `503` hasta que se configure.

`OPENAI_API_KEY` y `SONIA_BI_MODEL` habilitan opcionalmente selección de tool y
redacción asistida. Sin API key, el router determinístico y las cinco tools
siguen funcionando. Los CSV y el modelo canónico nunca se envían al LLM.

## CLI de backend

La CLI continúa siendo útil para pruebas operativas sin frontend:

```bash
cd back
python -m sonia.agents.bi.cli --dataset /ruta/DATASET --as-of-date 2026-07-31 executive
python -m sonia.agents.bi.cli --dataset /ruta/DATASET --as-of-date 2026-07-31 recovery
python -m sonia.agents.bi.cli --dataset /ruta/DATASET --as-of-date 2026-07-31 insights
```

## Responsabilidades y límites

- Python ejecuta joins, saldos, ageing, Pareto, concentraciones y reglas.
- La IA solo selecciona una tool cerrada e interpreta su resultado.
- `presentation.py` humaniza sin mutar el contrato técnico.
- `visuals.py` acepta un catálogo cerrado de componentes.
- `integration.py` mantiene el boundary JSON futuro con Cobranzas.
- Solo PEN entra en KPIs monetarios del MVP; USD no se mezcla.
- `RAZON_SOCIAL` es la clave temporal de cliente y
  `NRO_DOC_FISCAL → FACTURA_AFECTADA` la llave documental.
- Una nota de crédito aporta contexto de revisión, no prueba un error.
- El análisis describe la muestra anonimizada del hackathon, no toda Integratel.

No se implementan aquí Supervisor, ML, forecast, conciliación bancaria ni un
ranking de cobranza alternativo.
