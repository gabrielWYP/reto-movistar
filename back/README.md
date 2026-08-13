# Backend SON-IA

API FastAPI que actúa como única frontera para los tres agentes especialistas.

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

Los módulos heredados de cada rama viven en `src/sonia/agents/`. Para ejecutar
las pruebas que usan el dataset oficial se debe definir `SONIA_DATASET`; el
dataset no se versiona ni se incorpora a las imágenes.
