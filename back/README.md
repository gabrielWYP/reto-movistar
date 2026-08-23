# Backend SON-IA

API FastAPI que actúa como única frontera para los tres agentes especialistas.
Los paquetes independientes `bi_agent` y `collections_agent` se instalan en la
misma imagen y sus routers se montan en este proceso; no crean pods adicionales
en el despliegue integrado.

## Ejecutar

Desde esta carpeta:

```bash
python -m venv .venv
.venv/bin/pip install -e '../Agente BI/BACK[dev]'
.venv/bin/pip install -e '../Agente Cobranzas/BACK[dev]'
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Contratos principales:

- `GET /health`: salud del pod backend.
- `GET /api/agents`: registro de Facturación, Cobranzas y BI.
- `GET /api/supervisor/dataset`: estado de la fuente compartida.
- `POST /api/supervisor/dataset`: validación y publicación atómica para los tres agentes.
- `GET /api/demo/scenario`: escenario ficticio inicial.
- `POST /api/demo/transition`: transición controlada del journey.
- `GET /api/bi/status`: disponibilidad del dataset y las tools BI.
- `POST /api/bi/query`: consulta al agente BI.
- `GET /api/collections/status`: estado de Cobranzas y su dataset.
- `POST /api/collections/query`: consulta conversacional con tools determinísticas.

En el backend compartido, las rutas de carga específicas de BI, Facturación y
Cobranzas responden `403`. La carga manual se realiza únicamente desde
Supervisor; las implementaciones standalone conservan sus adaptadores HTTP para
pruebas y desarrollo aislado.

`POST /api/bi/query` usa OpenCode Go con `deepseek-v4-flash` cuando el proceso
recibe `OPENCODE_KEY`. `GET /api/bi/status` expone proveedor, modelo y
disponibilidad sin revelar credenciales. Si el proveedor no está configurado o
falla, las tools determinísticas permanecen operativas y la respuesta indica el
modo de fallback.

`POST /api/collections/query` usa OpenCode Go con `deepseek-v4-flash` cuando el
proceso recibe `OPENCODE_KEY`. Sin esa clave, las rutas
determinísticas de Cobranzas siguen operativas y la consulta en lenguaje natural
devuelve una indicación de configuración, sin simular IA mediante palabras clave.

Los módulos integrados viven en `src/sonia/agents/` o en los paquetes hermanos
`Agente BI/BACK/src/bi_agent` y
`Agente Cobranzas/BACK/src/collections_agent`. Para ejecutar
las pruebas que usan el dataset oficial se debe definir `SONIA_DATASET`; el
dataset no se versiona ni se incorpora a las imágenes.
