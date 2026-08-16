# Backend SON-IA

API FastAPI que actúa como única frontera para los tres agentes especialistas.
El paquete independiente `bi_agent` se instala en la misma imagen y su router se
monta en este proceso; no existe un servicio BI adicional en producción.

## Ejecutar

Desde esta carpeta:

```bash
python -m venv .venv
.venv/bin/pip install -e '../Agente BI/BACK[dev]'
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Contratos principales:

- `GET /health`: salud del pod backend.
- `GET /api/agents`: registro de Facturación, Cobranzas y BI.
- `GET /api/demo/scenario`: escenario ficticio inicial.
- `POST /api/demo/transition`: transición controlada del journey.
- `GET /api/bi/status`: disponibilidad del dataset y las tools BI.
- `POST /api/bi/query`: consulta al agente BI.

`POST /api/bi/query` usa OpenCode Go con `deepseek-v4-flash` cuando el proceso
recibe `OPENCODE_KEY`. `GET /api/bi/status` expone proveedor, modelo y
disponibilidad sin revelar credenciales. Si el proveedor no está configurado o
falla, las tools determinísticas permanecen operativas y la respuesta indica el
modo de fallback.

Los módulos integrados viven en `src/sonia/agents/` o en el paquete hermano
`Agente BI/BACK/src/bi_agent`. Para ejecutar
las pruebas que usan el dataset oficial se debe definir `SONIA_DATASET`; el
dataset no se versiona ni se incorpora a las imágenes.
