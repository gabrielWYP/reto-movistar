# Backend SON-IA

API FastAPI que actúa como única frontera para los tres agentes especialistas.
Facturación, Cobranzas y BI son módulos del mismo proceso backend; ninguno
publica un servidor o puerto propio.

## Ejecutar

Desde esta carpeta:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Contratos principales:

- `GET /health`: salud del pod backend.
- `GET /api/agents`: registro de Facturación, Cobranzas y BI.
- `GET /api/demo/scenario`: escenario ficticio inicial.
- `POST /api/demo/transition`: transición controlada del journey.
- `GET /api/bi/status`: disponibilidad y tools del Agente BI.
- `POST /api/bi/query`: consulta natural al Agente BI integrado.
- `POST /api/bi/tools/{operation}`: ejecución determinística de una tool BI.

Los módulos especialistas viven en `src/sonia/agents/`. BI recibe su dataset
mediante `SONIA_BI_DATASET_PATH`; el directorio o ZIP debe montarse en el pod
`back` como volumen de solo lectura. El dataset no se versiona ni se incorpora
a las imágenes.

El frontend está separado y consume estos contratos a través de Nginx. La
decisión operativa de dos pods se encuentra en
`docs/arquitectura/decisiones/ADR-002-client-server-two-pods.md`.
